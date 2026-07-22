"""ควบคุมไฟและจอ LED ของคีย์บอร์ด LEOBOG AMG65 ผ่าน USB HID

    from amg65 import Canvas, Link, Matrix
    with Link("control") as link:
        matrix = Matrix(link)
        canvas = Canvas()
        canvas.text("HELLO", 0, (254, 0, 0))
        matrix.show(canvas)
"""
from .device import Link, DeviceNotFound
from .matrix import Canvas, Matrix, WIDTH, HEIGHT
from .keyboard import KeyboardLight, KEY_INDEX, MODES

__all__ = [
    "Link", "DeviceNotFound", "Canvas", "Matrix", "WIDTH", "HEIGHT",
    "KeyboardLight", "KEY_INDEX", "MODES",
]
