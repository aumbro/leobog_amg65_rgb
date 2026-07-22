"""หาเพดาน FPS จริงของ AMG65 matrix live stream

โจทย์: ลำดับเดิมส่ง 19 reports/เฟรม (04 18 → 04 35 → RGB×15 → flush → 04 02)
คูณ delay 8.5ms = ~160ms/เฟรม → เพดาน ~7 FPS ซึ่งหน่วงเกินไปสำหรับ visualizer และเกม

สมมติฐานที่ต้องพิสูจน์:
  1. 04 18 (begin) กับ 04 35 (เข้าโหมด music) เป็นการ "เข้าโหมด" ครั้งเดียว
     ไม่ใช่ handshake ต่อเฟรม → ถ้าจริง ตัดออกได้ 2 reports
  2. zero flush report ต่อเฟรมอาจไม่จำเป็น → ตัดได้อีก 1
  3. delay 8.5ms เผื่อไว้กว้างเกินจริง

วัด throughput ได้เอง แต่ **ภาพกระพริบวัดด้วยโปรแกรมไม่ได้** ต้องใช้ตาดูโหมด --visual
(สูตรที่ throughput ผ่านแต่ภาพขาด = ใช้ไม่ได้)

    python bench_fps.py            # กวาดทุกสูตร × ทุก delay
    python bench_fps.py --visual   # โชว์แถบวิ่งทีละสูตรให้ดูด้วยตา
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

from amg65.device import DeviceNotFound, Link
from amg65.matrix import HEIGHT, WIDTH, Canvas, Matrix

# (ชื่อ, ส่ง header ต่อเฟรม, ส่ง flush ต่อเฟรม)
RECIPES = (
    ("full     ของเดิม 19 rpt", True, True),
    ("no-flush          18 rpt", True, False),
    ("no-hdr            17 rpt", False, True),
    ("minimal           16 rpt", False, False),
)

DELAYS_MS = (8.5, 6.0, 4.0, 2.0, 1.0, 0.0)


def bar_canvas(phase: float) -> Canvas:
    """แถบวิ่ง — ภาพขาด/กระพริบเห็นชัดกว่าไล่สีรุ้ง."""
    canvas = Canvas()
    head = int(phase) % WIDTH
    for x in range(WIDTH):
        distance = min(abs(x - head), WIDTH - abs(x - head))
        value = max(0, 254 - distance * 90)
        if value:
            for y in range(HEIGHT):
                canvas.set(x, y, (value, value // 3, 254 - value // 2))
    return canvas


def run_recipe(matrix: Matrix, seconds: float, frames_source) -> tuple[float, int]:
    frames = 0
    drops = 0
    started = time.perf_counter()
    while time.perf_counter() - started < seconds:
        try:
            matrix.show(frames_source(frames))
        except OSError:
            drops += 1
        frames += 1
    return frames / (time.perf_counter() - started), drops


def sweep(link: Link, seconds: float) -> None:
    print(f"{'สูตร':<26} {'delay':>7} {'FPS':>7} {'ms/เฟรม':>9} {'เฟรมหลุด':>10}")
    print("-" * 66)
    best = (0.0, "", 0.0)
    for name, header, flush in RECIPES:
        for delay_ms in DELAYS_MS:
            matrix = Matrix(
                link,
                packet_delay=delay_ms / 1000.0,
                header_every_frame=header,
                flush_every_frame=flush,
            )
            fps, drops = run_recipe(matrix, seconds, lambda i: bar_canvas(i * 1.7))
            mark = "  << หลุด" if drops else ""
            print(f"{name:<26} {delay_ms:>5.1f}ms {fps:>7.1f} {1000 / fps:>8.1f}ms {drops:>9}{mark}")
            if not drops and fps > best[0]:
                best = (fps, name, delay_ms)
    if best[0]:
        print(f"\nเร็วสุดที่ไม่มีเฟรมหลุด: {best[1].strip()} @ {best[2]}ms = {best[0]:.1f} FPS")
        print("→ ต้องดูด้วยตาซ้ำด้วย `python bench_fps.py --visual` ว่าไม่กระพริบ")


def visual(link: Link, seconds: float, recipe: str) -> None:
    """ไล่ delay จากเร็วสุดไปช้าสุดด้วยสูตรเดียว ให้คนดูว่าเริ่มนิ่งที่ค่าไหน

    throughput บอกไม่ได้ว่าภาพกระพริบ เพราะการกระพริบเกิดฝั่งเฟิร์มแวร์
    (เอาเฟรมที่ยังมาไม่ครบไปแสดง) ไม่ใช่ write ที่ล้มเหลว
    """
    header, flush = {"full": (True, True), "minimal": (False, False)}[recipe]
    print(f"สูตร {recipe} — ไล่ delay เร็ว→ช้า อันละ {seconds:.0f} วินาที")
    print("ดูแถบวิ่งบนจอ แล้วจำว่าเริ่ม 'นิ่ง ไม่ขาด ไม่กระพริบ' ที่ค่าไหน\n")
    for delay_ms in sorted(DELAYS_MS):
        print(f">>> delay {delay_ms:>4.1f} ms ...", end=" ", flush=True)
        matrix = Matrix(
            link,
            packet_delay=delay_ms / 1000.0,
            header_every_frame=header,
            flush_every_frame=flush,
        )
        fps, drops = run_recipe(matrix, seconds, lambda i: bar_canvas(i * 1.7))
        print(f"{fps:.1f} FPS" + (f", เฟรมหลุด {drops}" if drops else ""))
        # เว้นจังหวะให้ตาแยกออกว่าจบช่วงหนึ่งแล้ว
        matrix.show(Canvas())
        time.sleep(0.6)


def main() -> int:
    parser = argparse.ArgumentParser(description="วัดเพดาน FPS ของ AMG65 matrix stream")
    parser.add_argument("--visual", action="store_true", help="ดูด้วยตาแทนการวัด throughput")
    parser.add_argument("--seconds", type=float, default=2.5, help="เวลาต่อหนึ่งสูตร")
    parser.add_argument(
        "--recipe", choices=("minimal", "full"), default="minimal",
        help="สูตร packet ที่ใช้ตอน --visual",
    )
    args = parser.parse_args()

    try:
        with Link("control") as link:
            if args.visual:
                visual(link, max(args.seconds, 6.0), args.recipe)
            else:
                sweep(link, args.seconds)
    except DeviceNotFound as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
