"""สัญญาของ scene: วาดลง canvas ตามเวลาที่ให้ แค่นั้น

scene ห้ามยุ่งกับ HID เอง และห้าม sleep เอง — engine เป็นคนคุมจังหวะและอุปกรณ์
ข้อบังคับนี้ทำให้ scene ทุกตัวรันบน preview ในเทอร์มินัลได้โดยไม่ต้องมีคีย์บอร์ดต่ออยู่
"""
from __future__ import annotations

from ..matrix import Canvas


class Scene:
    #: ชื่อที่ใช้เรียกจาก CLI
    name = "scene"
    #: คำอธิบายสั้นสำหรับ --list
    description = ""
    #: FPS ที่อยากได้ (engine อาจให้ไม่ถึงถ้าฮาร์ดแวร์ไม่ไหว)
    fps = 15.0

    def start(self) -> None:
        """เรียกครั้งเดียวก่อนเฟรมแรก — เปิด thread เก็บเสียง/อ่านเซนเซอร์ที่นี่."""

    def stop(self) -> None:
        """เรียกตอนสลับ scene หรือปิดโปรแกรม — เก็บกวาดให้เรียบร้อย."""

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        """วาดหนึ่งเฟรม

        `elapsed` = วินาทีนับจาก start() (float), `frame` = ลำดับเฟรมนับจาก 0
        canvas ถูกล้างเป็นสีดำมาให้แล้วทุกเฟรม
        """
        raise NotImplementedError

    def on_key(self, key: str) -> None:
        """ปุ่มที่ผู้ใช้กดตอนหน้าต่างคอนโซลโฟกัสอยู่ (เกมใช้; scene อื่นไม่ต้องสน)."""
