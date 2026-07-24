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


def matrix_speed_for(fps: float) -> int:
    from .matrix import speed_for_fps

    return speed_for_fps(fps)


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
    # delay ที่ส่งเข้า Matrix เป็นแค่ตาข่ายกันตกแล้ว — จังหวะจริงมาจากการรอ ACK
    # (~2.8ms/packet) บวกการเว้นเฟรม 111ms ตามที่ถอดจากโปรแกรมทางการ
    def __init__(self, start_scene: str = "clock", delay_ms: float = 12.0) -> None:
        self.delay = delay_ms / 1000.0
        self.current = start_scene
        self.engine: Engine | None = None
        self.link: Link | None = None
        self.sink = None
        self.mode = "stream"          # "stream" = ยิงสด, "stored" = เก็บลงเครื่องแล้ว
        self.stored: str | None = None
        self.status: str | None = None
        self._error: str | None = None
        self._pending_scene = None
        self._closing = False
        self._thread: threading.Thread | None = None

    # ---------- ลูปวาด ----------

    def _worker(self) -> None:
        assert self.engine is not None
        try:
            scene = self._pending_scene or scenes.load(self.current)()
            self._pending_scene = None
            self.engine.run(scene)
        except EndpointStalled as exc:
            self._error = str(exc)
        except Exception as exc:  # scene พังไม่ควรลาก tray ตายไปด้วย
            self._error = f"{type(exc).__name__}: {exc}"

    def _select(self, name: str):
        """เลือก scene สตรีมสด — ถ้าเพิ่งเก็บลงเครื่องไว้ ให้กลับมาสตรีมใหม่."""

        def handler(icon, item) -> None:
            try:
                scene = scenes.load(name)()
            except (KeyError, ImportError) as exc:
                self._error = str(exc)
                return
            self.current = name
            self.mode = "stream"
            if self._thread is not None and self._thread.is_alive():
                assert self.engine is not None
                self.engine.request(scene)
            else:
                self._start_worker(scene)  # เคยหยุดไปตอนอัปโหลด ต้องปลุกใหม่

        return handler

    def _store(self, name: str):
        """เบค scene แล้วเก็บลงเครื่อง — เล่นเองต่อโดยไม่ต้องมีโปรแกรม

        ต้องหยุดสตรีมก่อน ไม่งั้นสองอย่างเขียน endpoint เดียวกันพร้อมกัน = ค้าง
        และหลังอัปโหลดก็ไม่กลับไปสตรีม เพราะจะไปทับภาพที่เพิ่งเก็บไว้
        """

        def handler(icon, item) -> None:
            threading.Thread(target=self._do_store, args=(name,), daemon=True).start()

        return handler

    def _do_store(self, name: str) -> None:
        from . import bake
        from .device import DeviceNotFound, EndpointStalled, Link

        plan = bake.plan_upload(name)
        if plan is None:
            self.status = f"{name} เบคไม่ได้ (ไม่ใช่ภาพวนลูป)"
            return
        frames_count, fps = plan

        self.status = f"กำลังเก็บ {name} ลงเครื่อง..."
        self._stop_worker()
        try:
            frames = bake.frames_from_scene(name, frames_count, fps)
            assert self.sink is not None
            with Link("bulk") as bulk:
                self.sink.matrix.upload_animation(
                    bulk, frames, speed=matrix_speed_for(fps)
                )
            self.mode = "stored"
            self.stored = name
            self.status = f"เก็บ {name} ลงเครื่องแล้ว — เล่นเองไม่ต้องมีโปรแกรม"
        except (EndpointStalled, DeviceNotFound, OSError, ValueError) as exc:
            self.status = f"อัปโหลดไม่สำเร็จ: {exc}"

    def _start_worker(self, scene) -> None:
        from .engine import Engine

        assert self.sink is not None
        self.engine = Engine(self.sink)
        self._pending_scene = scene
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _stop_worker(self) -> None:
        if self.engine is not None:
            self.engine.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

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

        # resilient: endpoint หลุด/ค้าง ไม่ทำให้ tray ตาย เสียบสายกลับแล้วยิงต่อเอง
        sink = MatrixSink(Matrix(self.link, packet_delay=self.delay), resilient=True)
        self.sink = sink
        self.engine = Engine(sink)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        # ถ้า scene แรกโหลดไม่ขึ้น worker จะตายทันทีแล้วไอคอนกลายเป็นสี่เหลี่ยมเปล่า
        # กดอะไรก็ไม่เกิดอะไร — เงียบเกินไปจนหาสาเหตุไม่เจอ (เคยเจอตอนแพ็กเป็น exe
        # แล้ว PyInstaller ไม่ได้แพ็ก scene มาด้วย เพราะทะเบียน import แบบไดนามิก)
        # จึงรอสั้น ๆ แล้วเช็คก่อน ให้ล้มตั้งแต่ต้นพร้อมบอกเหตุผล
        self._thread.join(timeout=1.5)
        if self._error is not None:
            sink.close()
            raise RuntimeError(f"scene แรกเริ่มไม่ได้: {self._error}")

        from . import bake

        stream_items = [
            pystray.MenuItem(
                f"{name} — {description}",
                self._select(name),
                checked=lambda item, n=name: self.mode == "stream" and self.current == n,
                radio=True,
            )
            for name, description, _extras in scenes.describe()
        ]
        # เก็บลงเครื่อง: เล่นเองโดยไม่ต้องมีโปรแกรม และไม่มีทราฟฟิกระหว่างเล่น
        # จึงเสถียรกว่าสตรีมสดมาก แลกกับที่ต้องเป็นภาพวนลูป (ไม่มีข้อมูลสด)
        store_items = []
        for name in bake.loopable_scenes():
            plan = bake.plan_upload(name)
            if plan is None:
                continue
            frames, fps = plan
            store_items.append(
                pystray.MenuItem(
                    f"{name} — {fps:.0f} FPS, ลูป {frames / fps:.1f} วิ",
                    self._store(name),
                    checked=lambda item, n=name: self.mode == "stored" and self.stored == n,
                    radio=True,
                )
            )

        menu_items = [
            pystray.MenuItem("สตรีมสด (ข้อมูลจริง)", pystray.Menu(*stream_items)),
            pystray.MenuItem("เก็บลงเครื่อง (ลื่นกว่า/ไม่หลุด)", pystray.Menu(*store_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("ออก", lambda icon, item: icon.stop()),
        ]

        icon = pystray.Icon(
            "amg65",
            Image.new("RGB", (ICON_SIZE, ICON_SIZE), (20, 20, 24)),
            "AMG65",
            pystray.Menu(*menu_items),
        )

        def refresh() -> None:
            """อัปเดตไอคอนกับ tooltip ตามเฟรมจริงเป็นระยะ

            ห่อทุกอย่างด้วย try/except เพราะถ้า assignment ตัวใดตัวหนึ่งพังในตัว exe
            (เคยเจอ) แล้ว loop ตาย tooltip จะค้างที่ค่าตั้งต้นตลอดไป
            """
            # วนจนกว่าไอคอนจะปิด — ไม่ผูกกับ worker เพราะโหมด 'เก็บลงเครื่อง'
            # ตั้งใจหยุด worker ไว้ (ถ้าผูกไว้ tooltip จะค้างตั้งแต่อัปโหลดเสร็จ)
            while not self._closing:
                try:
                    if not icon.visible:
                        threading.Event().wait(0.5)
                        continue
                    if self.status is not None:
                        icon.title = f"AMG65 — {self.status}"
                        # ข้อความชั่วคราว (กำลังอัปโหลด/ผลลัพธ์) โชว์แล้วเคลียร์
                        if not self.status.startswith("กำลัง"):
                            self.status = None
                    elif self.mode == "stored":
                        icon.title = f"AMG65 — เก็บ {self.stored} ลงเครื่องแล้ว (เล่นเอง)"
                    elif self._error is not None:
                        icon.title = f"AMG65 — หยุด: {self._error.splitlines()[0]}"
                    elif self.sink is not None and not self.sink.connected:
                        # ลูปวาดยังเดินอยู่ พอเสียบสายกลับจะยิงต่อเอง ไม่ต้องปิดแอป
                        icon.title = "AMG65 — รอคีย์บอร์ด (เสียบสาย USB)"
                    else:
                        assert self.engine is not None
                        icon.icon = _icon_image(self.engine.canvas, self.current)
                        icon.title = f"AMG65 — {self.current} @ {self.engine.actual_fps:.0f} FPS"
                except Exception:
                    pass  # อัปเดตรอบนี้พลาดไม่เป็นไร รอบหน้าลองใหม่
                threading.Event().wait(1.0)

        # `amg65 stop` จากอีกโปรเซสจะสั่งปิด icon อย่างสะอาด (ปิด HID ก่อนตาย)
        from .device import listen_for_stop

        listen_for_stop(icon.stop)

        threading.Thread(target=refresh, daemon=True).start()
        icon.run()

        self._closing = True
        if self.engine is not None:
            self.engine.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        sink.close()
        if self._error:
            print(f"\n{self._error}")
            return 1
        return 0
