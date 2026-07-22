#!/usr/bin/env python
"""จุดเข้าโปรแกรมเดิม — ตัวจริงย้ายไปอยู่ในแพ็กเกจ `amg65/` แล้ว

ไฟล์เดียว 630 บรรทัดเริ่มแน่นเกินไปตอนจะเพิ่ม scene หลายตัว จึงแตกเป็น
    amg65/device.py    หา HID endpoint + ส่ง report แบบทนสะดุด
    amg65/matrix.py    ผืนผ้าใบ 63×5 + โปรโตคอลส่งเฟรม
    amg65/keyboard.py  ไฟใต้ปุ่ม
    amg65/scenes/      ภาพที่วิ่งบนจอ (นาฬิกา, visualizer, เกม, ...)
    amg65/engine.py    วนเฟรมและสลับ scene

คำสั่งแบบเดิม (`amg65_rgb.py static --rgb 255 0 0`) ยังใช้ได้ โดยแปลงให้อัตโนมัติ
คำสั่งเต็มรูปแบบดูที่ `python -m amg65 --help`
"""
from __future__ import annotations

import sys

from amg65.cli import main
from amg65.keyboard import MODES

# ชื่อคำสั่งเดิม → รูปแบบใหม่
_LEGACY_SCENES = {
    "matrix-stream": "rainbow",
    "matrix-clock": "clock",
}


def translate(argv: list[str]) -> list[str]:
    """แปลงคำสั่งรูปแบบเดิมให้เป็น subcommand ใหม่ (คำสั่งใหม่ปล่อยผ่าน)."""
    if not argv:
        return argv
    head = argv[0]
    if head in MODES:
        return ["light", *argv]
    if head in ("per-key", "random"):
        rest = argv[1:]
        return ["keys", *(rest if head == "per-key" else ["--random", *rest])]
    if head in _LEGACY_SCENES:
        return ["show", _LEGACY_SCENES[head], *argv[1:]]
    if head.startswith("matrix-"):
        print(f"คำสั่ง {head} ถูกยกเลิก — ดู scene ที่มีด้วย `python -m amg65 list`")
        raise SystemExit(2)
    return argv


if __name__ == "__main__":
    argv = translate(sys.argv[1:])
    if argv != sys.argv[1:]:
        print(f"[เทียบเท่าคำสั่งใหม่: python -m amg65 {' '.join(argv)}]")
    sys.exit(main(argv))
