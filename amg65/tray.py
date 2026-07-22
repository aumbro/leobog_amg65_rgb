"""ไอคอนบนถาดระบบ — สลับ scene ได้โดยไม่ต้องเปิดหน้าต่างคอนโซลค้างไว้

ทำไมต้องมี: engine สลับ scene ในโปรเซสเดิมได้อยู่แล้ว แต่เดิมสั่งได้จากคีย์บอร์ด
ในคอนโซลเท่านั้น ซึ่งแปลว่าต้องมีหน้าต่างเปิดค้างและต้องโฟกัสอยู่ที่หน้าต่างนั้น
tray แก้ทั้งสองข้อ

โครง thread:
    main thread   pystray ต้องอยู่ที่นี่ (Windows ต้องการ message loop ของ thread หลัก)
    worker thread ลูปวาดเฟรมของ engine

การสลับ scene ข้าม thread ต้องผ่าน `Engine.request()` เท่านั้น สั่ง `switch()` ตรง ๆ
จะไป start/stop scene ระหว่างที่ลูปกำลังวาดเฟรมนั้นอยู่พอดี
"""
from __future__ import annotations

import threading

from . import scenes
from .device import DeviceNotFound, EndpointStalled, Link
from .engine import Engine, MatrixSink
from .matrix import HEIGHT, WIDTH, Matrix

ICON_SIZE = 64


def _icon_image(canvas, active: str):
    """วาดไอคอนจากเฟรมล่าสุดจริง ๆ — มองแวบเดียวรู้ว่า scene ไหนกำลังเล่น."""
    from PIL import Image

    # จอกว้าง 63 สูง 5 ย่อลงไอคอนสี่เหลี่ยมตรง ๆ จะแบนจนดูไม่ออก
    # จึงตัดเอาเฉพาะช่วงกลางแล้วขยายให้เต็ม
    crop = 16
    start = (WIDTH - crop) // 2
    image = Image.new("RGB", (crop, HEIGHT), (0, 0, 0))
    image.putdata([canvas.get(start + x, y) for y in range(HEIGHT) for x in range(crop)])
    return image.resize((ICON_SIZE, ICON_SIZE), Image.NEAREST)


class Tray:
    def __init__(self, start_scene: str = "clock", delay_ms: float = 8.5) -> None:
        self.delay = delay_ms / 1000.0
        self.current = start_scene
        self.engine: Engine | None = None
        self.link: Link | None = None
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    # ---------- ลูปวาด ----------

    def _worker(self) -> None:
        assert self.engine is not None
        try:
            self.engine.run(scenes.load(self.current)())
        except EndpointStalled as exc:
            self._error = str(exc)
        except Exception as exc:  # scene พังไม่ควรลาก tray ตายไปด้วย
            self._error = f"{type(exc).__name__}: {exc}"

    def _select(self, name: str):
        def handler(icon, item) -> None:
            try:
                scene = scenes.load(name)()
            except (KeyError, ImportError) as exc:
                self._error = str(exc)
                return
            self.current = name
            assert self.engine is not None
            self.engine.request(scene)

        return handler

    # ---------- tray ----------

    def run(self) -> int:
        import pystray
        from PIL import Image

        try:
            self.link = Link("control")
            self.link.open()
        except (OSError, DeviceNotFound) as exc:
            print(f"เปิดคีย์บอร์ดไม่ได้: {exc}")
            return 1

        sink = MatrixSink(Matrix(self.link, packet_delay=self.delay))
        self.engine = Engine(sink)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        menu_items = [
            pystray.MenuItem(
                f"{name} — {description}",
                self._select(name),
                checked=lambda item, n=name: self.current == n,
                radio=True,
            )
            for name, description, _extras in scenes.describe()
        ]
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("ออก", lambda icon, item: icon.stop()))

        icon = pystray.Icon(
            "amg65",
            Image.new("RGB", (ICON_SIZE, ICON_SIZE), (20, 20, 24)),
            "AMG65",
            pystray.Menu(*menu_items),
        )

        def refresh() -> None:
            """อัปเดตไอคอนกับ tooltip ตามเฟรมจริงเป็นระยะ."""
            last_drops = 0
            while icon.visible and self._thread is not None and self._thread.is_alive():
                assert self.engine is not None
                icon.icon = _icon_image(self.engine.canvas, self.current)
                drops = getattr(sink, "drops", 0)
                if self._error is not None:
                    icon.title = f"AMG65 — หยุดแล้ว: {self._error.splitlines()[0]}"
                    return
                if drops > last_drops:
                    # เฟรมตกต่อเนื่อง = คีย์บอร์ดไม่อยู่ (ถอดสาย/กำลังเสียบใหม่)
                    # ลูปวาดยังเดินอยู่และจะเปิด handle ใหม่ให้เองเมื่อเสียบกลับ
                    icon.title = f"AMG65 — รอคีย์บอร์ด ({drops} เฟรมตก)"
                else:
                    icon.title = f"AMG65 — {self.current} @ {self.engine.actual_fps:.1f} FPS"
                last_drops = drops
                threading.Event().wait(1.0)

        threading.Thread(target=refresh, daemon=True).start()
        icon.run()

        if self.engine is not None:
            self.engine.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        sink.close()
        if self._error:
            print(f"\n{self._error}")
            return 1
        return 0
