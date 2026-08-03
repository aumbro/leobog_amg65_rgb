"""เล่นจอ matrix + ไฟใต้ปุ่มพร้อมกัน

ฮาร์ดแวร์แยกกัน (จอ LCD กับ LED 67 ดวง) และเฟิร์มแวร์ยอมเปิดสองโหมดพร้อมกัน
ยืนยันด้วยตา: จอเล่น scene หนึ่ง ไฟปุ่มเล่นอีกเอฟเฟกต์ คนละลาย ไม่แย่งกัน

ทั้งคู่ใช้ MI_02 ช่องเดียว จึงต้องสลับส่ง: เฟรมจอ -> รอบไฟปุ่ม -> จอ -> ปุ่ม ...
โดยรอ ACK ทุก packet เหมือนเดิม (ทดสอบแล้ว ACK ครบทั้งสองฝั่ง ไม่ค้าง)
ได้ ~13 รอบคู่/วินาที ซึ่งพอสำหรับทั้งสองอย่าง
"""
from __future__ import annotations

import time

from .device import CMD_PER_KEY, Link
from .keyboard import KeyboardLight
from .matrix import Canvas, Matrix


class ComboPlayer:
    """สลับส่งเฟรมจอ scene กับรอบไฟใต้ปุ่มบน MI_02 ช่องเดียว"""

    def __init__(self, link: Link, scene, effect) -> None:
        self.link = link
        self.scene = scene
        self.effect = effect
        self.matrix = Matrix(link)
        self.keyboard = KeyboardLight(link)
        self._table = bytearray(0x200)
        self._kinit = bytearray(64)
        self._kinit[0:2] = CMD_PER_KEY
        self._kinit[8] = 0x08

    def run(self, fps: float = 13.0, should_stop=None) -> None:
        interval = 1.0 / max(fps, 0.5)
        self.scene.start()
        self.effect.start()
        self.link.drain()  # ล้าง ACK เก่าก่อนเริ่ม ไม่งั้นจังหวะเพี้ยน
        started = time.perf_counter()
        try:
            while should_stop is None or not should_stop():
                loop_start = time.perf_counter()
                elapsed = loop_start - started

                # เฟรมจอ
                canvas = Canvas()
                self.scene.render(canvas, elapsed, int(elapsed * fps))
                self.matrix.show(canvas)

                # รอบไฟใต้ปุ่ม
                self.keyboard._fill_table(self._table, self.effect.colors(elapsed))
                self.keyboard._write_table(self._table, self._kinit, 0.025)

                remaining = interval - (time.perf_counter() - loop_start)
                if remaining > 0:
                    time.sleep(remaining)
        finally:
            self.scene.stop()
            self.effect.stop()

    @property
    def acks_missed(self) -> int:
        return self.matrix.acks_missed + self.keyboard.acks_missed
