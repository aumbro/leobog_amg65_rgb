"""Small command-line RGB controller for the LEOBOG AMG65 on Windows."""

from __future__ import annotations

import argparse
import colorsys
import random
import time

import hid


VID = 0x0C45
PID = 0x800A
OUTPUT_INTERFACE = 2
OUTPUT_USAGE_PAGE = 0xFF68
FEATURE_INTERFACE = 3
FEATURE_USAGE_PAGE = 0xFF67
REPORT_BYTES = 65  # Windows report ID byte + 64-byte feature payload.
MATRIX_REPORT_BYTES = 4097
MATRIX_WIDTH = 63
MATRIX_HEIGHT = 5
COMMAND_DELAY = 0.200

CLOCK_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ":": ("0", "1", "0", "1", "0"),
}

INVADER_FRAMES = (
    ("0010100", "0111110", "1101011", "1111111", "0100010"),
    ("0010100", "0111110", "1101011", "1111111", "1000101"),
    ("0010100", "0111110", "1100011", "1111111", "0101010"),
    ("0010100", "0111110", "1101011", "1111111", "0011100"),
)

MODES = {
    "off": 0,
    "static": 1,
    "single-on": 2,
    "single-off": 3,
    "glittering": 4,
    "falling": 5,
    "colourful": 6,
    "breath": 7,
    "spectrum": 8,
    "outward": 9,
    "scrolling": 10,
    "rolling": 11,
    "rotating": 12,
    "explode": 13,
    "launch": 14,
    "ripples": 15,
    "flowing": 16,
    "pulsating": 17,
    "tilt": 18,
    "shuttle": 19,
}

# Exact light_index values from the AMG65 KeyboardLayout.xml (67-key layout).
KEY_INDEX = {
    "esc": 0,
    "1": 17, "2": 18, "3": 19, "4": 20, "5": 21, "6": 22,
    "7": 23, "8": 24, "9": 25, "0": 26, "minus": 27, "equal": 28,
    "backspace": 92, "home": 104, "volup": 13, "voldown": 14,
    "tab": 32, "q": 33, "w": 34, "e": 35, "r": 36, "t": 37,
    "y": 38, "u": 39, "i": 40, "o": 41, "p": 42,
    "lbracket": 43, "rbracket": 44, "backslash": 60, "delete": 106,
    "capslock": 48, "a": 49, "s": 50, "d": 51, "f": 52, "g": 53,
    "h": 54, "j": 55, "k": 56, "l": 57, "semicolon": 58, "quote": 59,
    "enter": 76, "pageup": 105,
    "lshift": 64, "z": 65, "x": 66, "c": 67, "v": 68, "b": 69,
    "n": 70, "m": 71, "comma": 72, "dot": 73, "slash": 74,
    "rshift": 75, "up": 90, "pagedown": 108,
    "lctrl": 80, "lwin": 81, "lalt": 82, "space": 83, "fn": 85,
    "rctrl": 87, "left": 88, "down": 89, "right": 91,
}

# Tuple order captured from DeviceDriver.exe Custom Light uploads. The tuples
# are sequential; they are not stored at light_index * 4.
LIGHT_ORDER = (
    [0] + list(range(17, 29)) + [92, 104, 13, 14]
    + list(range(32, 45)) + [60, 106]
    + list(range(48, 60)) + [76, 105]
    + list(range(64, 76)) + [90, 108]
    + [80, 81, 82, 83, 85, 87, 88, 89, 91]
)


def find_device_path(transport: str) -> bytes:
    interface = OUTPUT_INTERFACE if transport == "output" else FEATURE_INTERFACE
    usage_page = OUTPUT_USAGE_PAGE if transport == "output" else FEATURE_USAGE_PAGE
    matches = [
        item
        for item in hid.enumerate(VID, PID)
        if item.get("interface_number") == interface
        and item.get("usage_page") == usage_page
    ]
    if not matches:
        raise RuntimeError(
            f"ไม่พบ LEOBOG AMG65 ที่ MI_0{interface} / Usage Page 0x{usage_page:04X}; "
            "ให้ต่อสาย USB และปิดโหมด Bluetooth"
        )
    return matches[0]["path"]


class AMG65:
    def __init__(self, dry_run: bool = False, transport: str = "output") -> None:
        self.dry_run = dry_run
        self.transport = transport
        self.dev: hid.device | None = None

    def __enter__(self) -> "AMG65":
        if not self.dry_run:
            self.dev = hid.device()
            self.dev.open_path(find_device_path(self.transport))
        return self

    def __exit__(self, *_: object) -> None:
        if self.dev is not None:
            self.dev.close()

    def command(
        self,
        payload: bytes | bytearray,
        readback: bool = False,
        command_report: bool = False,
        delay: float = COMMAND_DELAY,
    ) -> None:
        if len(payload) > 64:
            raise ValueError("payload ยาวเกิน 64 ไบต์")
        report = bytearray(REPORT_BYTES)
        # Captured from DeviceDriver.exe: report ID is always 0, with the
        # 64-byte command/data payload beginning at report byte 1.
        report[1 : 1 + len(payload)] = payload
        if self.dry_run:
            print(report.hex(" "))
            return
        assert self.dev is not None
        written = (
            self.dev.write(report)
            if self.transport == "output"
            else self.dev.send_feature_report(report)
        )
        if written != REPORT_BYTES:
            raise OSError(f"ส่งได้ {written}/{REPORT_BYTES} ไบต์")
        time.sleep(delay)
        if readback:
            if self.transport == "output":
                # Some firmware revisions return an ACK; others do not.
                self.dev.read(REPORT_BYTES, 150)
            else:
                self.dev.get_feature_report(0, REPORT_BYTES)
            time.sleep(delay)

    def set_lighting(
        self,
        mode: int,
        red: int,
        green: int,
        blue: int,
        brightness: int,
        speed: int,
        direction: int,
        colorful: bool,
    ) -> None:
        self.command(b"\x04\x18", readback=True, command_report=True)  # Begin.

        init = bytearray(64)
        init[0:2] = b"\x04\x13"
        init[8] = 1
        self.command(init, readback=True, command_report=True)

        data = bytearray(64)
        data[0] = mode
        if mode:
            data[1:4] = bytes((red, green, blue))
            data[8] = int(colorful)
            data[9] = brightness
            data[10] = speed
            data[11] = direction
        # Captured AMG65 trailer order (full report bytes 15-16): AA 55.
        data[14:16] = b"\xAA\x55"
        self.command(data)

        self.command(b"\x04\x02", readback=True, command_report=True)  # Apply.
        self.command(b"\x04\xF0", command_report=True)  # Finalize.

    def set_per_key(
        self,
        colors: dict[str, tuple[int, int, int]],
        brightness: int,
        hold: bool = False,
        randomize: bool = False,
    ) -> None:
        """Set selected keys; every key not supplied is switched off."""
        # Exact AMG65 Custom Light transaction captured from driver 1.0.3.2:
        # 04 20 (mode byte 8 = 08), 512 bytes, then 04 02 apply.
        by_index = {KEY_INDEX[key]: rgb for key, rgb in colors.items()}
        rgb = bytearray(0x200)  # 128 sequential slots; 67 are populated.
        for slot, index in enumerate(LIGHT_ORDER):
            red, green, blue = by_index.get(index, (0, 0, 0))
            offset = slot * 4
            rgb[offset : offset + 4] = bytes((index, red, green, blue))
        custom_init = bytearray(64)
        custom_init[0:2] = b"\x04\x20"
        custom_init[8] = 0x08

        # 04 20 is a live-preview stream. The firmware turns it off shortly
        # after frames stop arriving, so --hold repeats it like the driver.
        stream_delay = 0.025
        while True:
            if randomize:
                for slot, index in enumerate(LIGHT_ORDER):
                    offset = slot * 4
                    rgb[offset : offset + 4] = bytes(
                        (index, *(random.randint(48, 255) for _ in range(3)))
                    )
            self.command(custom_init, delay=stream_delay)
            for offset in range(0, len(rgb), 64):
                self.command(rgb[offset : offset + 64], delay=stream_delay)
            if not hold:
                break


class AMG65Matrix:
    """Direct 63x5 RGB frame streaming through the AMG65 matrix endpoint."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.control: hid.device | None = None
        self.matrix: hid.device | None = None

    def __enter__(self) -> "AMG65Matrix":
        if not self.dry_run:
            self.control = hid.device()
            self.control.open_path(find_device_path("output"))
            self.matrix = hid.device()
            self.matrix.open_path(find_device_path("feature"))
        return self

    def __exit__(self, *_: object) -> None:
        if self.matrix is not None:
            self.matrix.close()
        if self.control is not None:
            self.control.close()

    def _reconnect_control(self) -> None:
        """Reopen the live-stream endpoint after a transient USB/HID failure."""
        if self.dry_run:
            return
        if self.control is not None:
            try:
                self.control.close()
            except OSError:
                pass
        while True:
            try:
                control = hid.device()
                control.open_path(find_device_path("output"))
                self.control = control
                return
            except (OSError, RuntimeError):
                time.sleep(0.250)

    def _control(self, payload: bytes | bytearray) -> None:
        report = bytearray(REPORT_BYTES)
        report[1 : 1 + len(payload)] = payload
        if self.dry_run:
            return
        assert self.control is not None
        last_written = -1
        for attempt in range(3):
            try:
                last_written = self.control.write(report)
            except OSError:
                last_written = -1
            if last_written == REPORT_BYTES:
                return
            if attempt < 2:
                time.sleep(0.020)
        raise OSError(f"ส่งคำสั่ง Matrix ได้ {last_written}/{REPORT_BYTES} ไบต์")

    def send_frame(self, pixels: list[tuple[int, int, int]]) -> None:
        self.send_animation([pixels])

    def send_animation(self, frames: list[list[tuple[int, int, int]]]) -> None:
        if not 1 <= len(frames) <= 255:
            raise ValueError("Animation ต้องมี 1-255 frames")
        for pixels in frames:
            if len(pixels) != MATRIX_WIDTH * MATRIX_HEIGHT:
                raise ValueError("Matrix ทุก frame ต้องมี 315 pixels")

        payload = bytearray((len(frames), 0, 0x0C, 0))
        for pixels in frames:
            for red, green, blue in pixels:
                payload.extend((red, green, blue))
        # The driver uses one padding byte only for a single-frame effect.
        payload.extend(b"\x00\xAA\x55" if len(frames) == 1 else b"\xAA\x55")

        begin = bytearray(64)
        begin[0:2] = b"\x04\x18"
        init = bytearray(64)
        init[0:2] = b"\x04\x33"
        chunk_count = (len(payload) + 4095) // 4096
        init[8] = chunk_count
        self._control(begin)
        self._control(init)
        for offset in range(0, len(payload), 4096):
            report = bytearray(MATRIX_REPORT_BYTES)
            chunk = payload[offset : offset + 4096]
            report[1 : 1 + len(chunk)] = chunk
            if not self.dry_run:
                assert self.matrix is not None
                if self.matrix.write(report) != MATRIX_REPORT_BYTES:
                    raise OSError("ส่ง Animation Matrix ไม่ครบ 4097 ไบต์")
            # Large matrix reports need time to drain through the HID endpoint.
            # The official driver spaces long uploads by about 160-167 ms.
            time.sleep(0.170)
        self._control(b"\x04\x02")
        self._control(b"\x04\xF0")

    def send_stream_frame(self, pixels: list[tuple[int, int, int]]) -> None:
        """Send one live frame with the flicker-free protocol used by Music mode."""
        if len(pixels) != MATRIX_WIDTH * MATRIX_HEIGHT:
            raise ValueError("Matrix ต้องมี 315 pixels")

        # Video calibration of all 315 raw indices shows four 14x5 row-major
        # blocks across the 56x5 main panel, followed by the right 7x5 panel.
        stream_positions = []
        for block in range(4):
            for y in range(MATRIX_HEIGHT):
                for dx in range(14):
                    stream_positions.append((block * 14 + dx, y))
        stream_positions += [
            (x, y) for y in range(MATRIX_HEIGHT) for x in range(56, 63)
        ]
        ordered_pixels = [pixels[y * MATRIX_WIDTH + x] for x, y in stream_positions]
        self.send_raw_stream_frame(ordered_pixels)

    def send_raw_stream_frame(self, ordered_pixels: list[tuple[int, int, int]]) -> None:
        """Send pixels in the device's raw memory order, without coordinate mapping."""
        if len(ordered_pixels) != MATRIX_WIDTH * MATRIX_HEIGHT:
            raise ValueError("Raw Matrix frame ต้องมี 315 pixels")
        raw = bytearray()
        for red, green, blue in ordered_pixels:
            # Music mode reserves 0xFF; the official driver caps channels at FE.
            raw.extend((min(red, 0xFE), min(green, 0xFE), min(blue, 0xFE)))
        raw.extend(b"\xAA\x55")
        raw.extend(bytes(15 * 64 - len(raw)))

        begin = bytearray(64)
        begin[0:2] = b"\x04\x18"
        init = bytearray(64)
        init[0:2] = b"\x04\x35"
        init[8] = 0x0F

        # A busy Windows HID endpoint occasionally rejects one report. Retry
        # the complete frame after reopening it instead of ending the stream.
        while True:
            try:
                self._control(begin)
                time.sleep(0.0085)
                self._control(init)
                time.sleep(0.0085)
                for offset in range(0, len(raw), 64):
                    self._control(raw[offset : offset + 64])
                    time.sleep(0.0085)
                self._control(bytes(64))  # Final zero flush used by Music mode.
                time.sleep(0.0085)
                self._control(b"\x04\x02")
                return
            except OSError:
                self._reconnect_control()
                time.sleep(0.100)

    def _legacy_send_frame(self, pixels: list[tuple[int, int, int]]) -> None:
        if len(pixels) != MATRIX_WIDTH * MATRIX_HEIGHT:
            raise ValueError("Matrix ต้องมี 315 pixels")

        # Captured from DeviceDriver.exe while applying a one-frame 63x5 GIF.
        frame = bytearray(MATRIX_REPORT_BYTES)
        frame[1:5] = b"\x01\x00\x0C\x00"
        offset = 5
        for red, green, blue in pixels:
            frame[offset : offset + 3] = bytes((red, green, blue))
            offset += 3
        frame[950:953] = b"\x00\xAA\x55"

        begin = bytearray(64)
        begin[0:2] = b"\x04\x18"
        init = bytearray(64)
        init[0:2] = b"\x04\x33"
        init[8] = 1
        self._control(begin)
        self._control(init)
        if not self.dry_run:
            assert self.matrix is not None
            if self.matrix.write(frame) != MATRIX_REPORT_BYTES:
                raise OSError("ส่งเฟรม Matrix ไม่ครบ 4097 ไบต์")
        self._control(b"\x04\x02")
        self._control(b"\x04\xF0")

    def stream_rainbow(self, fps: float) -> None:
        interval = 1.0 / fps
        frame_index = 0
        while True:
            started = time.perf_counter()
            phase = (frame_index * 0.025) % 1.0
            pixels = []
            for y in range(MATRIX_HEIGHT):
                for x in range(MATRIX_WIDTH):
                    hue = (x / MATRIX_WIDTH + y * 0.06 + phase) % 1.0
                    red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    pixels.append((int(red * 255), int(green * 255), int(blue * 255)))
            self.send_stream_frame(pixels)
            frame_index += 1
            remaining = interval - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)

    def stream_clock(self, fps: float) -> None:
        interval = 1.0 / fps
        frame_index = 0
        while True:
            started = time.perf_counter()
            timestamp = time.time()
            text = time.strftime("%H:%M:%S")
            pixels = [(0, 0, 0) for _ in range(MATRIX_WIDTH * MATRIX_HEIGHT)]

            # The main panel is eight 7x5 modules, exactly one per HH:MM:SS
            # character. Keeping glyphs inside a module avoids seam distortion.
            for module, char in enumerate(text):
                glyph = CLOCK_FONT[char]
                width = len(glyph[0])
                cursor = module * 7 + (7 - width) // 2
                colon_dim = char == ":" and int(timestamp * 2) % 2 == 0
                for y, row in enumerate(glyph):
                    for dx, bit in enumerate(row):
                        if bit == "1":
                            x = cursor + dx
                            hue = (timestamp * 0.075 + x / 80.0) % 1.0
                            red, green, blue = colorsys.hsv_to_rgb(hue, 0.88, 0.42 if colon_dim else 1.0)
                            pixels[y * MATRIX_WIDTH + x] = (
                                int(red * 254), int(green * 254), int(blue * 254)
                            )

            # The physically separate 7x5 panel gets its own dancing invader.
            invader = INVADER_FRAMES[(frame_index // 3) % len(INVADER_FRAMES)]
            invader_hue = (timestamp * 0.20) % 1.0
            ir, ig, ib = colorsys.hsv_to_rgb(invader_hue, 1.0, 1.0)
            invader_color = (int(ir * 254), int(ig * 254), int(ib * 254))
            for y, row in enumerate(invader):
                for dx, bit in enumerate(row):
                    pixels[y * MATRIX_WIDTH + 56 + dx] = invader_color if bit == "1" else (0, 0, 0)

            self.send_stream_frame(pixels)
            frame_index += 1
            remaining = interval - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)

    def stream_dot_calibration(self, fps: float) -> None:
        interval = 1.0 / fps
        raw_index = 0
        while True:
            started = time.perf_counter()
            pixels = [(0, 0, 0) for _ in range(MATRIX_WIDTH * MATRIX_HEIGHT)]
            if raw_index % 35 == 0:
                color = (0, 254, 0)
            elif raw_index % 7 == 0:
                color = (0, 80, 254)
            else:
                color = (254, 0, 0)
            pixels[raw_index] = color
            self.send_raw_stream_frame(pixels)
            raw_index = (raw_index + 1) % len(pixels)
            remaining = interval - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)

    def stream_block_calibration(self, fps: float) -> None:
        """Test four raw 14x5 blocks and one raw 7x5 block."""
        raw_pixels: list[tuple[int, int, int]] = []
        for block in range(4):
            block_pixels = [(0, 0, 0) for _ in range(14 * 5)]
            glyph = CLOCK_FONT[str(block + 1)]
            start_x = (14 - len(glyph[0])) // 2
            hue = block / 4.0
            red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = (int(red * 254), int(green * 254), int(blue * 254))
            for y, row in enumerate(glyph):
                for dx, bit in enumerate(row):
                    if bit == "1":
                        block_pixels[y * 14 + start_x + dx] = color
            raw_pixels.extend(block_pixels)

        tail = [(0, 0, 0) for _ in range(7 * 5)]
        glyph = CLOCK_FONT["5"]
        start_x = (7 - len(glyph[0])) // 2
        for y, row in enumerate(glyph):
            for dx, bit in enumerate(row):
                if bit == "1":
                    tail[y * 7 + start_x + dx] = (254, 254, 254)
        raw_pixels.extend(tail)

        while True:
            started = time.perf_counter()
            self.send_raw_stream_frame(raw_pixels)
            remaining = 1.0 / fps - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)

    def stream_column_calibration(self, fps: float) -> None:
        """Sweep one physical-looking raw column at a time for map discovery."""
        step = 0
        while True:
            started = time.perf_counter()
            raw_pixels = [(0, 0, 0) for _ in range(MATRIX_WIDTH * MATRIX_HEIGHT)]
            if step < 56:
                block, dx = divmod(step, 8)
                color = (0, 254, 0) if dx == 0 else (0, 120, 254)
                for y in range(5):
                    raw_pixels[block * 40 + y * 8 + dx] = color
            else:
                dx = step - 56
                for y in range(5):
                    raw_pixels[280 + y * 7 + dx] = (254, 0, 180)
            self.send_raw_stream_frame(raw_pixels)
            step = (step + 1) % 63
            remaining = 1.0 / fps - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)


def byte_value(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 255:
        raise argparse.ArgumentTypeError("ต้องอยู่ระหว่าง 0-255")
    return value


def level_value(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 5:
        raise argparse.ArgumentTypeError("ต้องอยู่ระหว่าง 0-5")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="ควบคุมไฟ LEOBOG AMG65 ผ่าน USB HID")
    parser.add_argument("mode", choices=(*MODES, "per-key", "random", "matrix-stream", "matrix-clock", "matrix-calibrate", "matrix-map", "matrix-columns"), help="เอฟเฟกต์ไฟ")
    parser.add_argument("--rgb", nargs=3, type=byte_value, default=(255, 255, 255), metavar=("R", "G", "B"))
    parser.add_argument("--brightness", type=level_value, default=5)
    parser.add_argument("--speed", type=level_value, default=3)
    parser.add_argument("--direction", type=int, choices=(0, 1, 2, 3), default=0)
    parser.add_argument("--colorful", action="store_true", help="ใช้สีรุ้งแทน RGB สีเดียว")
    parser.add_argument(
        "--key", action="append", nargs=4, metavar=("KEY", "R", "G", "B"),
        help="กำหนดสีรายปุ่ม; ระบุซ้ำได้ เช่น --key w 255 0 0",
    )
    parser.add_argument("--dry-run", action="store_true", help="แสดง packet โดยไม่ส่งไปคีย์บอร์ด")
    parser.add_argument(
        "--hold", action="store_true",
        help="ส่งไฟรายปุ่มต่อเนื่องจนกด Ctrl+C (จำเป็นสำหรับ Custom Light)",
    )
    parser.add_argument(
        "--transport", choices=("output", "feature"), default="output",
        help="ช่อง HID; AMG65 ใช้ output เป็นค่าเริ่มต้น",
    )
    parser.add_argument("--fps", type=float, default=8.0, help="เฟรมต่อวินาทีสำหรับ matrix-stream")
    args = parser.parse_args()

    if args.mode in ("matrix-stream", "matrix-clock", "matrix-calibrate", "matrix-map", "matrix-columns"):
        if not 1 <= args.fps <= 30:
            parser.error("--fps ต้องอยู่ระหว่าง 1-30")
        with AMG65Matrix(args.dry_run) as matrix:
            if args.mode == "matrix-clock":
                matrix.stream_clock(args.fps)
            elif args.mode == "matrix-calibrate":
                matrix.stream_dot_calibration(args.fps)
            elif args.mode == "matrix-map":
                matrix.stream_block_calibration(args.fps)
            elif args.mode == "matrix-columns":
                matrix.stream_column_calibration(args.fps)
            else:
                matrix.stream_rainbow(args.fps)
        return

    with AMG65(args.dry_run, args.transport) as keyboard:
        if args.mode in ("per-key", "random"):
            if args.mode == "per-key" and not args.key:
                parser.error("per-key ต้องมี --key อย่างน้อยหนึ่งรายการ")
            if args.mode == "random":
                colors = {
                    key: tuple(random.randint(48, 255) for _ in range(3))
                    for key in KEY_INDEX
                }
            else:
                colors = {}
                for key, red, green, blue in args.key:
                    key = key.lower()
                    if key not in KEY_INDEX:
                        parser.error(f"ไม่รู้จักปุ่ม {key!r}")
                    colors[key] = (byte_value(red), byte_value(green), byte_value(blue))
            keyboard.set_per_key(
                colors,
                args.brightness,
                args.hold or args.mode == "random",
                args.mode == "random",
            )
        else:
            keyboard.set_lighting(
                MODES[args.mode], *args.rgb, args.brightness, args.speed,
                args.direction, args.colorful,
            )
    print("ตั้งค่าไฟ AMG65 สำเร็จ" if not args.dry_run else "dry-run สำเร็จ")


if __name__ == "__main__":
    main()
