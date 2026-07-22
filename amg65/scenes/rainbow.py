"""ไล่สีรุ้งทั้งจอ — ใช้เช็คว่าจอ/ท่อส่งภาพยังดีอยู่"""
from __future__ import annotations

import colorsys

from ..matrix import HEIGHT, WIDTH, Canvas
from .base import Scene


class RainbowScene(Scene):
    name = "rainbow"
    description = "ไล่สีรุ้งไหลทั้งจอ"
    fps = 20.0

    def __init__(self, speed: float = 0.35) -> None:
        self.speed = speed
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
