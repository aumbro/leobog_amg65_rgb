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

from amg65.device import DeviceNotFound, EndpointStalled, Link
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


def run_recipe(matrix: Matrix, seconds: float, frames_source) -> tuple[float, int, bool]:
    """คืน (FPS, จำนวนเฟรมหลุด, endpoint ค้างไหม)

    endpoint ค้าง = จบการทดลอง ต้องถอดสายเสียบใหม่ก่อนทดสอบต่อ วนต่อไม่มีประโยชน์
    """
    frames = 0
    drops = 0
    started = time.perf_counter()
    while time.perf_counter() - started < seconds:
        try:
            matrix.show(frames_source(frames))
        except EndpointStalled:
            return frames / max(1e-6, time.perf_counter() - started), drops, True
        except OSError:
            drops += 1
        frames += 1
    return frames / (time.perf_counter() - started), drops, False


def sweep(link: Link, seconds: float) -> None:
    print(f"{'สูตร':<26} {'delay':>7} {'FPS':>7} {'ms/เฟรม':>9} {'เฟรมหลุด':>10}")
    print("-" * 66)
    for name, header, flush in RECIPES:
        for delay_ms in DELAYS_MS:
            matrix = Matrix(
                link,
                packet_delay=delay_ms / 1000.0,
                header_every_frame=header,
                flush_every_frame=flush,
            )
            fps, drops, stalled = run_recipe(matrix, seconds, lambda i: bar_canvas(i * 1.7))
            mark = "  << ค้าง" if stalled else ("  << หลุด" if drops else "")
            print(f"{name:<26} {delay_ms:>5.1f}ms {fps:>7.1f} {1000 / max(fps, 1e-6):>8.1f}ms {drops:>9}{mark}")
            if stalled:
                print("\nendpoint ค้าง — จบการทดลองรอบนี้ ต้องถอดสาย USB เสียบใหม่ก่อนวัดต่อ")
                return
    print("\nรอบนี้ผ่านหมดไม่มีอะไรค้าง — แต่การค้างเป็นแบบสุ่ม ผ่านรอบเดียวยังไม่พอตัดสิน")
    print("ยืนยันค่าที่จะใช้จริงด้วย soak ยาว ๆ: python bench_fps.py --soak 4 --seconds 180")


def soak(link: Link, delay_ms: float, seconds: float, lean: bool) -> None:
    """ทดสอบค่าเดียวยาว ๆ — วิธีเดียวที่เชื่อได้ เพราะการค้างเกิดแบบสุ่ม

    การกวาดสั้น ๆ หลอกได้ง่าย: รอบแรกไล่ถึง delay 0 ได้โดยไม่มีอะไรค้าง
    รอบสองพังตั้งแต่ 1.0 ms ค่าที่จะตั้งเป็น default ต้องผ่านการรันยาวก่อน
    """
    matrix = Matrix(
        link,
        packet_delay=delay_ms / 1000.0,
        header_every_frame=not lean,
        flush_every_frame=not lean,
    )
    print(f"soak: delay {delay_ms} ms, สูตร {'minimal' if lean else 'full'}, นาน {seconds:.0f} วินาที")
    started = time.perf_counter()
    fps, drops, stalled = run_recipe(matrix, seconds, lambda i: bar_canvas(i * 1.7))
    elapsed = time.perf_counter() - started
    if stalled:
        print(f"\n✗ ค้างที่วินาทีที่ {elapsed:.0f} — delay {delay_ms} ms เร็วเกินไป ใช้ไม่ได้")
        print("  ถอดสาย USB เสียบใหม่ แล้วลองค่าที่สูงกว่านี้")
    else:
        print(f"\n✓ ผ่าน {elapsed:.0f} วินาที ที่ {fps:.1f} FPS" + (f" (เฟรมหลุด {drops})" if drops else ""))


def visual(link: Link, seconds: float, recipe: str) -> None:
    """ไล่ delay จากเร็วสุดไปช้าสุดด้วยสูตรเดียว ให้คนดูว่าเริ่มนิ่งที่ค่าไหน

    throughput บอกไม่ได้ว่าภาพกระพริบ เพราะการกระพริบเกิดฝั่งเฟิร์มแวร์
    (เอาเฟรมที่ยังมาไม่ครบไปแสดง) ไม่ใช่ write ที่ล้มเหลว
    """
    header, flush = {"full": (True, True), "minimal": (False, False)}[recipe]
    matrix = Matrix(link, packet_delay=0.0085)
    print(f"สูตร {recipe} — ไล่ delay ช้า→เร็ว อันละ {seconds:.0f} วินาที")
    print("ช่วงแรกคือ 8.5ms ของเดิมที่รู้ว่านิ่ง ใช้เป็นตัวเทียบ")
    print("แล้วดูว่าแถบวิ่งเริ่ม 'ขาด/กระพริบ/สั่น' ตอนช่วงที่เท่าไร\n")
    # ให้เวลาละสายตาจากจอคอมไปมองคีย์บอร์ดก่อน
    for count in (3, 2, 1):
        print(f"  เริ่มใน {count}...", flush=True)
        matrix.show(bar_canvas(count * 9))
        time.sleep(1.0)
    matrix.show(Canvas())

    # ช้าไปเร็ว: เห็นของดีก่อน แล้วค่อยไล่ลงจนพัง หาจุดแตกง่ายกว่าไล่ขึ้น
    for delay_ms in sorted(DELAYS_MS, reverse=True):
        print(f">>> delay {delay_ms:>4.1f} ms ...", end=" ", flush=True)
        matrix = Matrix(
            link,
            packet_delay=delay_ms / 1000.0,
            header_every_frame=header,
            flush_every_frame=flush,
        )
        fps, drops, stalled = run_recipe(matrix, seconds, lambda i: bar_canvas(i * 1.7))
        print(f"{fps:.1f} FPS" + (f", เฟรมหลุด {drops}" if drops else ""))
        if stalled:
            print(f"\nendpoint ค้างที่ delay {delay_ms} ms — จบการทดลอง ต้องถอดสายเสียบใหม่")
            return
        # เว้นจังหวะให้ตาแยกออกว่าจบช่วงหนึ่งแล้ว
        try:
            matrix.show(Canvas())
        except EndpointStalled:
            print(f"\nendpoint ค้างหลังจบช่วง {delay_ms} ms — ต้องถอดสายเสียบใหม่")
            return
        time.sleep(0.6)


def main() -> int:
    parser = argparse.ArgumentParser(description="วัดเพดาน FPS ของ AMG65 matrix stream")
    parser.add_argument("--visual", action="store_true", help="ดูด้วยตาแทนการวัด throughput")
    parser.add_argument("--seconds", type=float, default=2.5, help="เวลาต่อหนึ่งสูตร")
    parser.add_argument(
        "--recipe", choices=("minimal", "full"), default="minimal",
        help="สูตร packet ที่ใช้ตอน --visual",
    )
    parser.add_argument(
        "--soak", type=float, metavar="DELAY_MS",
        help="ทดสอบ delay ค่าเดียวยาว ๆ ว่า endpoint ค้างไหม (วิธีที่เชื่อได้ที่สุด)",
    )
    parser.add_argument("--lean", action="store_true", help="ใช้สูตร minimal 16 reports ตอน --soak")
    args = parser.parse_args()

    try:
        with Link("control") as link:
            if args.soak is not None:
                soak(link, args.soak, max(args.seconds, 30.0), args.lean)
            elif args.visual:
                visual(link, max(args.seconds, 6.0), args.recipe)
            else:
                sweep(link, args.seconds)
    except EndpointStalled as exc:
        print(f"\n{exc}")
        return 1
    except DeviceNotFound as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
