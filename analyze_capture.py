"""ถอดรหัส USB capture ของโปรแกรม LEOBOG ทางการ เทียบกับโปรโตคอลที่เรารู้

เป้าหมายหลักคือหาคำตอบว่า **ทางการทำอะไรที่เราไม่ได้ทำ** จนสตรีมได้ไม่ค้าง
สิ่งที่มองหา:
  - จังหวะเวลาจริงระหว่าง packet (เราเดา 8.5ms มาตลอด ทางการใช้เท่าไร?)
  - มี keepalive / คำสั่งที่เราไม่รู้จักไหม
  - ลำดับ packet ต่อเฟรมต่างจากเราไหม
  - มีการอ่านกลับ (IN transfer) ระหว่างสตรีมไหม — ถ้ามี แปลว่าทางการ
    *รอให้เครื่องตอบก่อนส่งต่อ* ซึ่งอธิบายได้ว่าทำไมมันไม่ค้าง (flow control)

    python analyze_capture.py capture_bus1.pcap
"""
from __future__ import annotations

import argparse
import collections
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

TSHARK = r"C:\Program Files\Wireshark\tshark.exe"

# คำสั่งที่เรารู้จักแล้ว (จาก AMG65_REVERSE_ENGINEERING.md)
KNOWN = {
    "0418": "BEGIN เริ่ม transaction",
    "0402": "APPLY",
    "04f0": "FINALIZE",
    "0413": "เตรียมข้อมูลเอฟเฟกต์",
    "0420": "ไฟรายปุ่ม (live preview)",
    "0433": "อัปโหลด animation",
    "0435": "เข้าโหมด music stream",
}


def run_tshark(path: str) -> list[tuple[float, str, str, str]]:
    """ดึง (เวลา, ทิศทาง, endpoint, ข้อมูล hex) ของทุก USB transfer ของ VID 0C45."""
    result = subprocess.run(
        [
            TSHARK, "-r", path,
            "-Y", "usb.idVendor == 0x0c45 || usb.src contains \"0c45\" || usb",
            "-T", "fields",
            "-e", "frame.time_relative",
            "-e", "usb.endpoint_address.direction",
            "-e", "usb.endpoint_address",
            "-e", "usb.capdata",
            "-e", "usbhid.data",
            "-E", "separator=|",
        ],
        capture_output=True, text=True, errors="replace",
    )
    if result.returncode != 0:
        print(f"tshark ผิดพลาด: {result.stderr[:300]}")
        return []

    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        stamp, direction, endpoint, capdata, hiddata = parts[:5]
        payload = (capdata or hiddata or "").replace(":", "").strip()
        if not payload or not stamp:
            continue
        try:
            rows.append((float(stamp), direction or "?", endpoint or "?", payload))
        except ValueError:
            continue
    return rows


def classify(payload: str) -> str:
    head = payload[:4].lower()
    if head in KNOWN:
        return KNOWN[head]
    if payload.strip("0") == "":
        return "ศูนย์ล้วน (flush)"
    return "ข้อมูล RGB / อื่น ๆ"


def main() -> int:
    parser = argparse.ArgumentParser(description="ถอดรหัส USB capture ของ AMG65")
    parser.add_argument("pcap")
    parser.add_argument("--max-rows", type=int, default=60, help="แสดงกี่บรรทัดแรก")
    args = parser.parse_args()

    rows = run_tshark(args.pcap)
    if not rows:
        print("ไม่เจอ transfer เลย — อาจจับผิด bus หรือโปรแกรมทางการไม่ได้ส่งอะไร")
        return 1

    print(f"เจอ {len(rows)} transfers\n")

    # 1) มี IN transfer ระหว่างสตรีมไหม = ทางการรอเครื่องตอบก่อนส่งต่อหรือเปล่า
    directions = collections.Counter(r[1] for r in rows)
    print("ทิศทาง (0 = OUT ส่งออก, 1 = IN อ่านกลับ):")
    for key, count in directions.most_common():
        print(f"  {key}: {count}")
    if directions.get("1", 0) > 10:
        print("  ** มี IN เยอะ = ทางการอาจอ่านกลับ/รอ ACK ระหว่างสตรีม (flow control) **")
    print()

    # 2) ชนิดคำสั่งที่เจอ — คำสั่งที่เราไม่รู้จักคือของใหม่ที่ต้องไปแกะ
    kinds = collections.Counter(classify(r[3]) for r in rows)
    print("ชนิด packet:")
    for kind, count in kinds.most_common():
        print(f"  {count:6}  {kind}")
    print()

    # 3) คำสั่งขึ้นต้น 04 ที่ยังไม่รู้จัก
    unknown = collections.Counter(
        r[3][:4].lower() for r in rows
        if r[3][:2].lower() == "04" and r[3][:4].lower() not in KNOWN
    )
    if unknown:
        print("** คำสั่ง 04 xx ที่ยังไม่รู้จัก (ของใหม่!) **")
        for code, count in unknown.most_common(10):
            print(f"  {code}: {count} ครั้ง")
        print()

    # 4) จังหวะเวลาจริงระหว่าง OUT — ตัวเลขที่เราเดามาตลอดว่า 8.5ms
    outs = [r for r in rows if r[1] == "0"]
    gaps = [
        (outs[i][0] - outs[i - 1][0]) * 1000.0
        for i in range(1, len(outs))
    ]
    if gaps:
        gaps_sorted = sorted(gaps)
        print("ช่วงเวลาระหว่าง OUT transfer (ms):")
        print(f"  น้อยสุด {gaps_sorted[0]:.2f}")
        print(f"  ค่ากลาง {gaps_sorted[len(gaps_sorted) // 2]:.2f}")
        print(f"  90%     {gaps_sorted[int(len(gaps_sorted) * 0.9)]:.2f}")
        print(f"  มากสุด  {gaps_sorted[-1]:.2f}")
        print(f"  (เราใช้ 8.5-12 ms มาตลอดโดยเดาเอา)")
        print()

    # 5) ลำดับจริง 40 packet แรก — ดูโครงหนึ่งเฟรมว่าต่างจากเราไหม
    print(f"ลำดับ {min(args.max_rows, len(rows))} packet แรก:")
    print(f"{'เวลา(ms)':>9} {'ห่าง':>7} {'ทิศ':>4} {'ep':>4}  ชนิด / ต้นข้อมูล")
    previous = rows[0][0]
    for stamp, direction, endpoint, payload in rows[: args.max_rows]:
        gap = (stamp - previous) * 1000.0
        previous = stamp
        label = classify(payload)
        print(
            f"{stamp * 1000:9.1f} {gap:7.2f} {direction:>4} {endpoint:>4}  "
            f"{label:<28} {payload[:24]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
