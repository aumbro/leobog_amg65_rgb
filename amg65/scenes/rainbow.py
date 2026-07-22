"""ไล่สีรุ้งทั้งจอ — ใช้เช็คว่าจอ/ท่อส่งภาพยังดีอยู่"""
from __future__ import annotations

import colorsys

from ..matrix import HEIGHT, WIDTH, Canvas
from .base import Scene


class RainbowScene(Scene):
    name = "rainbow"
    description = "ไล่สีรุ้งไหลทั้งจอ"
    fps = 20.0
    # phase เลื่อนไป 1.0 = สีวนกลับมาที่เดิมพอดี ลูปจึงยาว 1/speed วินาที
    # ต้องประกาศระดับคลาสด้วย เพราะตัวคำนวณจำนวนเฟรมอ่านค่าก่อนสร้าง instance
    DEFAULT_SPEED = 0.35
    loop_seconds = 1.0 / DEFAULT_SPEED

    def __init__(self, speed: float = DEFAULT_SPEED) -> None:
        self.speed = speed
        self.loop_seconds = 1.0 / speed
        # ตาราง hsv→rgb แพงพอตัวเมื่อคูณ 315 พิกเซล × ทุกเฟรม จึงคิดล่วงหน้าไว้รอบเดียว
        self._wheel = [
            tuple(int(c * 254) for c in colorsys.hsv_to_rgb(i / 256.0, 1.0, 1.0))
            for i in range(256)
        ]

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        phase = elapsed * self.speed
        for y in range(HEIGHT):
            for x in range(WIDTH):
                index = int((x / WIDTH + y * 0.06 + phase) * 256) & 0xFF
                canvas.set(x, y, self._wheel[index])  # type: ignore[arg-type]
