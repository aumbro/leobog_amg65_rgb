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


class DeviceNotFound(OSError):
    """ยังหา endpoint ไม่เจอ — สืบทอด OSError เพราะเป็นสภาพชั่วคราวได้

    (ถอดสายอยู่ / กำลังเสียบใหม่) โค้ดที่วนวาดเฟรมจึงจับรวมกับ write ที่พลาดได้เลย
    แล้วปล่อยเฟรมนั้นตกไป ไม่ต้องแยกเคสเอง
    """


class EndpointStalled(OSError):
    """interrupt OUT ของ MI_02 ค้าง — เปิด handle ใหม่ก็ไม่หาย ต้องถอดสายเสียบใหม่

    อาการ: hid_write บล็อกจนครบ timeout ~1 วินาทีแล้วคืน -1 ทุกครั้ง พร้อม
    "Overlapped I/O operation is in progress" ขณะที่ MI_03 ยังเขียนได้ปกติ

    เกิดจากส่งเร็วกว่าที่อุปกรณ์ระบายทัน จน transfer ค้างคาไม่มีวันจบ
    """


# write ที่พลาดแบบ "บล็อกจนครบ timeout" คือ endpoint ค้าง ไม่ใช่แค่ยุ่งชั่วคราว
STALL_SECONDS = 0.9


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


class AlreadyRunning(RuntimeError):
    pass


# ใช้ socket แทนไฟล์ล็อก เพราะระบบปฏิบัติการคืน port ให้เองเมื่อโปรเซสตาย
# ไม่มีปัญหาไฟล์ล็อกค้างตอนโปรแกรมถูกฆ่า
_LOCK_PORT = 47865
_lock_socket = None


def claim_exclusive() -> None:
    """กันไม่ให้มีสองโปรเซสยิงเข้า endpoint เดียวกันพร้อมกัน

    สองโปรเซสที่เขียน MI_02 พร้อมกันคือวิธีทำให้ endpoint ค้างที่ง่ายที่สุด
    และเป็นความผิดพลาดที่เกิดซ้ำได้ง่ายมาก (เปิด tray ทิ้งไว้แล้วลืม แล้วสั่ง show)
    """
    global _lock_socket
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", _LOCK_PORT))
        sock.listen(1)
    except OSError:
        sock.close()
        raise AlreadyRunning(
            "มีโปรแกรม amg65 อีกตัวรันอยู่แล้ว\n"
            "  สองโปรเซสยิงเข้า endpoint เดียวกันจะทำให้ค้างจนต้องถอดสาย\n"
            "  ปิดตัวเดิมก่อน (ถ้าเป็น tray ให้กดเมนู 'ออก')"
        )
    _lock_socket = sock  # ถือไว้ตลอดอายุโปรเซส


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
        """ปิดแล้วเปิด handle ใหม่ วนรอจนกว่าจะเจออุปกรณ์หรือครบ timeout

        จำเป็นเพราะ **HID path เปลี่ยนทุกครั้งที่เสียบสายใหม่** handle เดิมจึงใช้ต่อไม่ได้
        `timeout=0.0` = ลองครั้งเดียวแล้วเลิก (ใช้ในลูปวาดเฟรม ไม่ควรบล็อกนาน)
        """
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
                # เปิดสั้น ๆ พอ — ถ้ายังไม่มีอุปกรณ์ ปล่อยให้เฟรมนี้ตกไปแล้วลองใหม่เฟรมหน้า
                # ดีกว่าบล็อกลูปวาดไว้เป็นสิบวินาที
                self.reopen(timeout=0.0)
            started = time.perf_counter()
            try:
                assert self.dev is not None
                written = self.dev.write(bytes(report))
            except OSError:
                written = -1
            if written == self.report_bytes:
                return
            # write ที่บล็อกจนครบ timeout = endpoint ค้าง; retry/reopen ไม่ช่วย
            # (พิสูจน์แล้วว่าเปิด handle ใหม่ก็ยังค้าง) มีแต่เสีย 1 วินาทีต่อครั้ง
            if time.perf_counter() - started >= STALL_SECONDS:
                # คำแนะนำต่างกันตามช่อง: control หน่วงด้วย --delay, bulk ด้วย --chunk-delay
                hint = (
                    "ส่ง frame ถี่เกินกว่าที่อุปกรณ์ระบายทัน — เพิ่มค่า --delay"
                    if self.channel == "control"
                    else "ส่งก้อนข้อมูลถี่เกินไป — เพิ่มค่า --chunk-delay หรือลดจำนวนเฟรม"
                )
                interface = CONTROL_INTERFACE if self.channel == "control" else BULK_INTERFACE
                raise EndpointStalled(
                    f"endpoint {self.channel} (MI_0{interface}) ค้าง\n"
                    f"  {hint}\n"
                    "  แก้ตอนนี้: ถอดสาย USB เสียบใหม่ แล้วรัน `python -m amg65 doctor`"
                )
            # พลาดแบบทันที = อุปกรณ์หายไปหรือเพิ่งถูกเสียบใหม่ (HID path เปลี่ยนทุกครั้ง
            # ที่เสียบ) handle เดิมใช้ต่อไม่ได้แล้ว ต้องทิ้งแล้วเปิดใหม่ ไม่ใช่ retry เฉย ๆ
            self.close()
            if attempt < retries - 1:
                time.sleep(0.020)
        raise OSError(
            f"ส่ง report ไม่สำเร็จ ({written}/{self.report_bytes} ไบต์) ที่ช่อง {self.channel}"
        )
