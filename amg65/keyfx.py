"""เอฟเฟกต์ไฟใต้ปุ่ม 67 ดวง — ผังปุ่มจริง + เอฟเฟกต์ที่เต้นตามเสียง

ต่างจาก scene ของจอ LED ตรงที่ผลลัพธ์เป็น dict {ชื่อปุ่ม: สี} ไม่ใช่ Canvas
และส่งผ่านคำสั่ง `04 20` (Custom Light) ซึ่งเป็น live preview เหมือนกัน
คือถ้าหยุดส่งไฟจะดับเอง จึงต้องส่งซ้ำเรื่อย ๆ

ผังปุ่มถอดจาก LIGHT_ORDER โดยตรง — ลำดับใน LIGHT_ORDER คือลำดับทางกายภาพ
แถวต่อแถวอยู่แล้ว (ยืนยันจากการที่มันแบ่งกลุ่มตรงกับแถวคีย์บอร์ดพอดี)
"""
from __future__ import annotations

import colorsys
import math

RGB = tuple[int, int, int]

# แถวคีย์บอร์ดตามลำดับกายภาพ (ซ้าย -> ขวา, บน -> ล่าง)
ROWS: tuple[tuple[str, ...], ...] = (
    ("esc", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "minus", "equal",
     "backspace", "home", "volup", "voldown"),
    ("tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p",
     "lbracket", "rbracket", "backslash", "delete"),
    ("capslock", "a", "s", "d", "f", "g", "h", "j", "k", "l",
     "semicolon", "quote", "enter", "pageup"),
    ("lshift", "z", "x", "c", "v", "b", "n", "m", "comma", "dot", "slash",
     "rshift", "up", "pagedown"),
    ("lctrl", "lwin", "lalt", "space", "fn", "rctrl", "left", "down", "right"),
)


def _build_positions() -> dict[str, tuple[float, float]]:
    """ตำแหน่งปุ่มแบบ normalize 0..1 — x ตามลำดับในแถว, y ตามแถว

    ไม่ได้วัดขนาดปุ่มจริง (space กว้างกว่าปุ่มอักษรมาก) แต่สำหรับเอฟเฟกต์ไฟ
    การกระจายเท่า ๆ กันในแถวก็ให้ผลที่ตาดูแล้วถูกต้องพอ
    """
    positions: dict[str, tuple[float, float]] = {}
    for row_index, row in enumerate(ROWS):
        y = row_index / (len(ROWS) - 1)
        for column, key in enumerate(row):
            x = column / (len(row) - 1) if len(row) > 1 else 0.5
            positions[key] = (x, y)
    return positions


POSITIONS = _build_positions()


def _hsv(hue: float, value: float, saturation: float = 1.0) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, saturation, max(0.0, min(1.0, value)))
    return int(r * 255), int(g * 255), int(b * 255)


class KeySpectrum:
    """spectrum เต้นตามเสียง กระจายตามตำแหน่งปุ่มจริง

    ปุ่มซ้าย = เสียงต่ำ, ปุ่มขวา = เสียงสูง (เหมือน vis บนจอ LED)
    ความสว่างของแต่ละปุ่มมาจากระดับของย่านความถี่ที่ตรงกับตำแหน่ง x ของมัน
    แถวล่างสว่างก่อนแถวบน จึงดูเหมือนไฟไต่ขึ้นตามจังหวะ
    """

    name = "spectrum"

    def __init__(self, bands: int = 16, gain: float = 1.0) -> None:
        from .scenes.vis import _Spectrum

        self.bands = bands
        self.gain = gain
        self.spec = _Spectrum(bands)
        self._stop = None
        self._thread = None
        # เตรียมย่านของแต่ละปุ่มไว้ล่วงหน้า ไม่ต้องคิดใหม่ทุกเฟรม
        self._band_of = {
            key: min(bands - 1, int(pos[0] * bands)) for key, pos in POSITIONS.items()
        }

    def start(self) -> None:
        import threading

        from .scenes.vis import _capture

        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=_capture, args=(self.spec, self._stop, self.gain), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()

    def colors(self, elapsed: float) -> dict[str, RGB]:
        levels, active = self.spec.get()
        if not active:
            return self._idle(elapsed)
        result: dict[str, RGB] = {}
        for key, (x, y) in POSITIONS.items():
            level = float(levels[self._band_of[key]])
            # แถวล่าง (y ใกล้ 1) ติดง่ายกว่าแถวบน -> ไฟไต่ขึ้นตามความดัง
            threshold = 1.0 - y
            brightness = (level - threshold * 0.85) / max(0.15, 1.0 - threshold * 0.85)
            if brightness <= 0.02:
                result[key] = (0, 0, 0)
            else:
                result[key] = _hsv(0.62 - x * 0.62, min(1.0, brightness))
        return result

    @staticmethod
    def _idle(elapsed: float) -> dict[str, RGB]:
        """ไม่มีเสียง — คลื่นจาง ๆ ไหลผ่านให้รู้ว่ายังทำงานอยู่."""
        head = (elapsed * 0.35) % 1.6 - 0.3
        result = {}
        for key, (x, _y) in POSITIONS.items():
            distance = abs(x - head)
            value = max(0.0, 0.28 - distance * 1.4)
            result[key] = _hsv(0.55, value) if value > 0 else (0, 0, 0)
        return result


class KeyWave:
    """คลื่นสีรุ้งไหลทแยงข้ามคีย์บอร์ด — ไม่ต้องใช้เสียง ใช้เช็คว่าไฟทำงานครบ"""

    name = "wave"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def colors(self, elapsed: float) -> dict[str, RGB]:
        return {
            key: _hsv(elapsed * 0.25 + x * 0.6 + y * 0.15, 1.0)
            for key, (x, y) in POSITIONS.items()
        }


class KeyRipple:
    """ระลอกวงกลมแผ่จากกลางคีย์บอร์ด"""

    name = "ripple"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def colors(self, elapsed: float) -> dict[str, RGB]:
        result = {}
        for key, (x, y) in POSITIONS.items():
            distance = math.hypot(x - 0.5, (y - 0.5) * 0.4)
            phase = math.sin((distance * 6.0 - elapsed * 2.2) * math.tau / 2.0)
            value = max(0.0, phase)
            result[key] = _hsv(0.75 + distance * 0.5, value ** 2)
        return result


EFFECTS = {
    "spectrum": KeySpectrum,
    "wave": KeyWave,
    "ripple": KeyRipple,
}
