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
    """ส่งเฟรมเข้าจอจริง

    `resilient=True` (สำหรับ tray ที่เปิดทั้งวัน): ถ้า endpoint ค้าง ไม่ตาย แต่พักการส่ง
    ชั่วคราวแล้วลองเปิดใหม่เป็นระยะ พอถอดสายเสียบกลับก็ยิงต่อเองโดยไม่ต้องปิดแอป
    การเปิด handle ใหม่ไม่ปลดล็อก endpoint ที่ค้าง (พิสูจน์แล้ว) แต่พอเสียบสายใหม่
    HID path เปลี่ยน handle ใหม่จึงเป็นคนละอันที่ไม่ค้าง

    `resilient=False` (ค่าเริ่มต้น สำหรับคำสั่ง show ที่รันครั้งเดียว): ค้าง = เลิก
    แล้วแจ้งให้ถอดสาย เพราะวนต่อมีแต่บล็อกทีละ 1 วินาที
    """

    def __init__(self, matrix: Matrix, resilient: bool = False) -> None:
        self.matrix = matrix
        self.resilient = resilient
        self.drops = 0
        self.connected = True
        self.sent = 0
        self.skipped = 0
        self._cooldown_until = 0.0
        self._backoff = 0.5
        self._last_sent: list | None = None

    def show(self, canvas: Canvas) -> None:
        if self.resilient and time.perf_counter() < self._cooldown_until:
            return  # อยู่ในช่วงพักหลังค้าง ไม่ยิงเพื่อไม่ให้บล็อกทีละวินาที
        # เฟรมเหมือนเดิมเป๊ะไม่ต้องส่งซ้ำ เฟิร์มแวร์ค้างภาพสุดท้ายไว้เองอยู่แล้ว
        # นาฬิกา/sysmon เปลี่ยนภาพไม่กี่ครั้งต่อวินาที ตัดทราฟฟิกที่ไม่จำเป็นออก
        # = ลดโอกาส endpoint ค้างโดยไม่เสียอะไรเลย
        if self.connected and canvas.pixels == self._last_sent:
            self.skipped += 1
            return
        try:
            self.matrix.show(canvas)
            self._last_sent = list(canvas.pixels)
            self.sent += 1
            self.connected = True
            self._backoff = 0.5
        except EndpointStalled:
            if not self.resilient:
                raise
            # ค้าง: ปิด handle แล้วพักก่อนลองใหม่ ยิ่งค้างซ้ำยิ่งพักนานขึ้น (สูงสุด 5 วิ)
            self.matrix.link.close()
            self._on_lost()
            self._cooldown_until = time.perf_counter() + self._backoff
            self._backoff = min(self._backoff * 1.6, 5.0)
        except OSError:
            # หลุด/ถอดสาย: เฟรมเดียวหายดีกว่าตาย เฟรมหน้าเปิด handle ใหม่ให้เอง
            self._on_lost()

    def _on_lost(self) -> None:
        self.drops += 1
        # ลืมเฟรมล่าสุด เพื่อบังคับส่งใหม่ตอนกลับมา — พอหลุดแล้วเฟิร์มแวร์อาจกลับไป
        # เอฟเฟกต์เดิมของมัน ถ้าไม่ส่งใหม่เพราะ "เฟรมเหมือนเดิม" จอจะไม่กลับมาเป็นของเรา
        self._last_sent = None
        if self.resilient:
            self.connected = False

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
