"""ชั้นล่างสุด: หา HID endpoint ของ AMG65 แล้วส่ง report แบบทนสะดุด

AMG65 เปิด vendor HID ไว้สองช่อง (ถอดจาก DeviceDriver.exe 1.0.3.2):

    MI_02 / usage page 0xFF68 / report 65 ไบต์   → คำสั่งไฟ + matrix live stream
    MI_03 / usage page 0xFF67 / report 4097 ไบต์ → อัปโหลด animation ก้อนใหญ่

ไบต์แรกของ report บน Windows คือ Report ID = 0x00 เสมอ payload จึงเริ่มที่ไบต์ 1

เรื่องที่ต้องระวัง: Windows HID endpoint ปฏิเสธ output report เป็นครั้งคราว
(hid_write คืน -1 พร้อม "Overlapped I/O operation is in progress") ถ้าปล่อยให้
exception หลุดขึ้นไป stream จะตายกลางคัน Link จึง retry แล้วเปิด endpoint ใหม่ให้เอง
"""
from __future__ import annotations

import time

import hid

VID = 0x0C45
PID = 0x800A

CONTROL_INTERFACE = 2
CONTROL_USAGE_PAGE = 0xFF68
CONTROL_REPORT_BYTES = 65

BULK_INTERFACE = 3
BULK_USAGE_PAGE = 0xFF67
BULK_REPORT_BYTES = 4097

# คำสั่งระดับ transaction ที่เห็นซ้ำ ๆ ใน capture
CMD_BEGIN = b"\x04\x18"
CMD_APPLY = b"\x04\x02"
CMD_FINALIZE = b"\x04\xF0"
CMD_EFFECT = b"\x04\x13"
CMD_PER_KEY = b"\x04\x20"
CMD_UPLOAD = b"\x04\x33"
CMD_STREAM = b"\x04\x35"

TRAILER = b"\xAA\x55"


class DeviceNotFound(RuntimeError):
    pass


def find_path(channel: str = "control") -> bytes:
    """คืน HID path ของช่องที่ต้องการ ('control' = MI_02, 'bulk' = MI_03)."""
    interface = CONTROL_INTERFACE if channel == "control" else BULK_INTERFACE
    usage_page = CONTROL_USAGE_PAGE if channel == "control" else BULK_USAGE_PAGE
    for item in hid.enumerate(VID, PID):
        if item.get("interface_number") == interface and item.get("usage_page") == usage_page:
            return item["path"]
    raise DeviceNotFound(
        f"ไม่พบ LEOBOG AMG65 ที่ MI_0{interface} / usage page 0x{usage_page:04X}\n"
        "  - ต่อสาย USB และสลับสวิตช์คีย์บอร์ดมาโหมดมีสาย (BT/2.4G ไม่เปิดช่องนี้)\n"
        "  - ปิดโปรแกรม LEOBOG ทางการจาก system tray"
    )


class Link:
    """ถือ HID handle หนึ่งช่อง พร้อม retry และเปิดใหม่อัตโนมัติ."""

    def __init__(self, channel: str = "control", dry_run: bool = False) -> None:
        self.channel = channel
        self.dry_run = dry_run
        self.report_bytes = CONTROL_REPORT_BYTES if channel == "control" else BULK_REPORT_BYTES
        self.dev: hid.device | None = None
        self.reconnects = 0

    def __enter__(self) -> "Link":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def open(self) -> None:
        if self.dry_run:
            return
        dev = hid.device()
        dev.open_path(find_path(self.channel))
        self.dev = dev

    def close(self) -> None:
        if self.dev is not None:
            try:
                self.dev.close()
            except OSError:
                pass
            self.dev = None

    def reopen(self, timeout: float = 10.0) -> None:
        """ปิดแล้วเปิดใหม่ ใช้ตอน endpoint ค้าง; วนรอถ้าคีย์บอร์ดถูกถอดสาย."""
        if self.dry_run:
            return
        self.close()
        self.reconnects += 1
        deadline = time.perf_counter() + timeout
        while True:
            try:
                self.open()
                return
            except (OSError, DeviceNotFound):
                if time.perf_counter() > deadline:
                    raise
                time.sleep(0.250)

    def send(self, payload: bytes | bytearray, retries: int = 3) -> None:
        """ส่ง payload หนึ่ง report; retry แล้วเปิด endpoint ใหม่ถ้าจำเป็น."""
        if len(payload) > self.report_bytes - 1:
            raise ValueError(f"payload ยาวเกิน {self.report_bytes - 1} ไบต์")
        report = bytearray(self.report_bytes)
        report[1 : 1 + len(payload)] = payload
        if self.dry_run:
            return
        written = -1
        for attempt in range(retries):
            if self.dev is None:
                self.reopen()
            try:
                assert self.dev is not None
                written = self.dev.write(bytes(report))
            except OSError:
                written = -1
            if written == self.report_bytes:
                return
            if attempt < retries - 1:
                # ครั้งแรกแค่พัก; ครั้งต่อไปถือว่า endpoint ค้าง ต้องเปิดใหม่
                if attempt == 0:
                    time.sleep(0.020)
                else:
                    self.reopen()
        raise OSError(
            f"ส่ง report ไม่สำเร็จ ({written}/{self.report_bytes} ไบต์) ที่ช่อง {self.channel}"
        )
