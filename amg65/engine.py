"""engine: ถือ HID handle ไว้ตัวเดียว แล้ววน scene ให้ตามจังหวะ

โครงเดิมคือ "1 โหมด = 1 process" สลับโหมดต้อง Ctrl+C แล้วรันใหม่ ซึ่งเปิด/ปิด
endpoint ทุกครั้ง (และ endpoint MI_02 ค้างง่ายเวลาโดนฆ่ากลางเฟรม) engine จึงเปิด
ครั้งเดียวแล้วสลับ scene ในโปรเซสเดิม

รับปุ่มจากคอนโซลด้วย msvcrt — ทำงานเฉพาะตอนหน้าต่างคอนโซลโฟกัสอยู่ ตั้งใจเลือกแบบนี้
แทน global keyboard hook เพราะไม่ต้องลง dependency เพิ่ม ไม่ต้องขอสิทธิ์ admin
และไม่ดักคีย์ตอนผู้ใช้พิมพ์งานอื่นอยู่
"""
from __future__ import annotations

import threading
import time

from .device import EndpointStalled
from .matrix import Canvas, Matrix
from .scenes.base import Scene

try:
    import msvcrt
except ImportError:  # ไม่ใช่ Windows — เล่นเกมไม่ได้แต่ scene อื่นรันได้
    msvcrt = None  # type: ignore[assignment]

# รหัสปุ่มพิเศษของ msvcrt (นำหน้าด้วย 0x00 หรือ 0xE0)
_SPECIAL = {
    b"H": "up",
    b"P": "down",
    b"K": "left",
    b"M": "right",
}


def poll_keys() -> list[str]:
    """อ่านปุ่มที่ค้างใน buffer ของคอนโซลแบบไม่บล็อก."""
    if msvcrt is None:
        return []
    keys: list[str] = []
    while True:
        try:
            if not msvcrt.kbhit():
                return keys
            char = msvcrt.getch()
        except OSError:
            # รันแบบไม่มีคอนโซล (เช่น tray) — ไม่มีปุ่มให้อ่าน ไม่ใช่ข้อผิดพลาด
            return keys
        if char in (b"\x00", b"\xe0"):
            keys.append(_SPECIAL.get(msvcrt.getch(), "?"))
        elif char == b" ":
            keys.append("space")
        elif char == b"\r":
            keys.append("enter")
        elif char == b"\x1b":
            keys.append("esc")
        elif char == b"\x03":
            raise KeyboardInterrupt
        else:
            keys.append(char.decode("ascii", "ignore").lower())


class MatrixSink:
    """ส่งเฟรมเข้าจอจริง."""

    def __init__(self, matrix: Matrix) -> None:
        self.matrix = matrix
        self.drops = 0

    def show(self, canvas: Canvas) -> None:
        try:
            self.matrix.show(canvas)
        except EndpointStalled:
            # ค้างแล้วไม่มีทางกลับมาเองจนกว่าจะถอดสาย — วนต่อมีแต่ค้างทีละ 1 วินาที
            raise
        except OSError:
            # เฟรมเดียวหายดีกว่าโปรแกรมตาย — เฟรมถัดไปจะเข้าโหมด stream ใหม่เอง
            self.drops += 1

    def close(self) -> None:
        self.matrix.link.close()


class PreviewSink:
    """วาดลงเทอร์มินัลแทนจอจริง."""

    def __init__(self) -> None:
        from . import preview

        self.preview = preview
        self.drops = 0
        preview.enable_ansi()
        preview.clear_screen()

    def show(self, canvas: Canvas) -> None:
        self.preview.draw(canvas)

    def close(self) -> None:
        pass


class MultiSink:
    def __init__(self, *sinks) -> None:
        self.sinks = sinks
        self.drops = 0

    def show(self, canvas: Canvas) -> None:
        for sink in self.sinks:
            sink.show(canvas)
        self.drops = sum(getattr(s, "drops", 0) for s in self.sinks)

    def close(self) -> None:
        for sink in self.sinks:
            sink.close()


class Engine:
    def __init__(self, sink, fps: float | None = None) -> None:
        self.sink = sink
        self.fps_override = fps
        self.canvas = Canvas()
        self.scene: Scene | None = None
        self.actual_fps = 0.0
        # tray อยู่คนละ thread กับลูปวาด สั่งสลับ scene ตรง ๆ ไม่ได้
        # ต้องฝากไว้ให้ลูปหยิบไปทำเอง ไม่งั้น scene ถูก start/stop ระหว่างกำลังวาดอยู่
        self._pending: Scene | None = None
        self._lock = threading.Lock()
        self._shutdown = threading.Event()

    def switch(self, scene: Scene) -> None:
        if self.scene is not None:
            self.scene.stop()
        self.scene = scene
        scene.start()

    def request(self, scene: Scene) -> None:
        """สั่งสลับ scene จาก thread อื่น (ลูปจะสลับให้ตอนขึ้นเฟรมถัดไป)."""
        with self._lock:
            self._pending = scene

    def shutdown(self) -> None:
        self._shutdown.set()

    def run(self, scene: Scene, duration: float | None = None, on_key=None) -> None:
        """วนจนกว่าจะครบ duration หรือโดน Ctrl+C / ปุ่ม q / shutdown()."""
        self.switch(scene)
        assert self.scene is not None
        started = time.perf_counter()
        frame = 0
        window_start = started
        window_frames = 0
        try:
            while True:
                loop_start = time.perf_counter()
                if self._shutdown.is_set():
                    return

                with self._lock:
                    pending, self._pending = self._pending, None
                if pending is not None:
                    self.switch(pending)
                    # scene ใหม่ต้องเริ่มนับเวลาจากศูนย์ ไม่งั้นแอนิเมชันกระโดดกลางคัน
                    started = loop_start
                    frame = 0

                elapsed = loop_start - started
                if duration is not None and elapsed >= duration:
                    return

                for key in poll_keys():
                    if key in ("q", "esc"):
                        return
                    if on_key is not None and on_key(key):
                        continue
                    assert self.scene is not None
                    self.scene.on_key(key)

                self.canvas.clear()
                assert self.scene is not None
                self.scene.render(self.canvas, elapsed, frame)
                self.sink.show(self.canvas)

                frame += 1
                window_frames += 1
                if loop_start - window_start >= 1.0:
                    self.actual_fps = window_frames / (loop_start - window_start)
                    window_start, window_frames = loop_start, 0

                target = self.fps_override or self.scene.fps
                remaining = 1.0 / target - (time.perf_counter() - loop_start)
                if remaining > 0:
                    time.sleep(remaining)
        finally:
            if self.scene is not None:
                self.scene.stop()
