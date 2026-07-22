"""แยกโรค: เฟรมเดียวถูกแต่หลายเฟรมมั่ว — การวางเฟรมต่อกันผิดตรงไหน

ทดสอบด้วย 4 เฟรม เฟรมละหนึ่งตัวเลขใหญ่ คนละสี วางซ้ำกันทั้งจอ
  อ่านเลขออกครบ 1 2 3 4  -> การวางเฟรมถูก ปัญหาอยู่ที่จำนวนเฟรมเยอะเกิน
  เลขเพี้ยน/เลื่อน        -> stride ผิด (เฟิร์มแวร์คาดระยะห่างต่อเฟรมไม่เท่าที่เราวาง)

ลอง stride ได้สองแบบผ่าน --stride
  945 = ชิดกันเป๊ะ (ที่ใช้อยู่)
  960 = เท่ากับ payload ต่อเฟรมของ live stream (945 + padding 15)
"""
import argparse
import sys
import time

sys.path.insert(0, r"D:\hobby\amg65-rgb")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from amg65.device import CMD_APPLY, CMD_BEGIN, CMD_FINALIZE, CMD_UPLOAD, TRAILER, Link
from amg65.matrix import MAX_CHANNEL, RAW_ORDER, WIDTH, Canvas

COLORS = [(254, 0, 0), (0, 254, 0), (60, 120, 254), (254, 254, 0)]


def digit_frames(count: int) -> list[Canvas]:
    """เฟรมที่ n = เลข n ซ้ำทั้งจอ คนละสี — เลื่อนนิดเดียวก็เห็นทันที"""
    frames = []
    for index in range(count):
        canvas = Canvas()
        char = str((index + 1) % 10)
        color = COLORS[index % len(COLORS)]
        for slot in range(0, WIDTH - 3, 6):
            canvas.text(char, slot, color)
        frames.append(canvas)
    return frames


def upload(frames: list[Canvas], stride: int, speed: int) -> None:
    payload = bytearray((len(frames), 0, speed, 0))
    for canvas in frames:
        block = bytearray()
        for x, y in RAW_ORDER:
            r, g, b = canvas.pixels[y * WIDTH + x]
            block.extend((min(r, MAX_CHANNEL), min(g, MAX_CHANNEL), min(b, MAX_CHANNEL)))
        block.extend(bytes(max(0, stride - len(block))))  # เติมให้ครบ stride
        payload.extend(block[:stride])
    payload.extend(b"\x00" + TRAILER if len(frames) == 1 else TRAILER)

    init = bytearray(64)
    init[0:2] = CMD_UPLOAD
    init[8] = (len(payload) + 4095) // 4096

    with Link("control") as control, Link("bulk") as bulk:
        begin = bytearray(64)
        begin[0:2] = CMD_BEGIN
        control.send(begin)
        control.send(init)
        for offset in range(0, len(payload), 4096):
            bulk.send(payload[offset : offset + 4096])
            time.sleep(0.170)
        control.send(CMD_APPLY)
        control.send(CMD_FINALIZE)
    print(
        f"ส่งแล้ว: {len(frames)} เฟรม, stride {stride}, speed 0x{speed:02X}, "
        f"payload {len(payload):,} ไบต์"
    )


parser = argparse.ArgumentParser()
parser.add_argument("--frames", type=int, default=4)
parser.add_argument("--stride", type=int, default=945)
parser.add_argument("--speed", type=lambda s: int(s, 0), default=0x0C)
args = parser.parse_args()
upload(digit_frames(args.frames), args.stride, args.speed)
