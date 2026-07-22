# AMG65 RGB Controller

ควบคุมไฟและจอ LED ของคีย์บอร์ด **LEOBOG AMG65** ผ่าน USB HID บน Windows
โปรโตคอลถอดจากแพ็กเก็ตของ `DeviceDriver.exe` 1.0.3.2 โดยตรง **ไม่แฟลชและไม่แก้เฟิร์มแวร์**

ทำอะไรได้:

- เอฟเฟกต์ไฟใต้ปุ่ม 20 โหมดของเฟิร์มแวร์ + กำหนดสีรายปุ่มเอง
- ยิงภาพขึ้นจอ LED 63×5 แบบสด — นาฬิกา, spectrum ตามเสียง, ชื่อเพลง, มอนิเตอร์เครื่อง, เกม
- พัฒนา scene ใหม่โดยดูผลในเทอร์มินัลได้ ไม่ต้องต่อคีย์บอร์ด

## ติดตั้ง

```powershell
py -m pip install -r requirements.txt
```

ต่อคีย์บอร์ดด้วย **สาย USB** และสลับสวิตช์มาโหมดมีสาย (BT/2.4G ไม่เปิด vendor interface ที่ใช้)
ถ้าโปรแกรม LEOBOG ทางการเปิดอยู่ ให้ปิดจาก system tray ก่อน — ไม่งั้นแย่งโหมดไฟกัน

## เช็คว่าพร้อมใช้ไหม

```bash
python -m amg65 doctor
```

อาการที่เจอบ่อยที่สุดคือ **MI_02 ค้าง** (เขียนแล้ว timeout 1 วินาที ขึ้น
`Overlapped I/O operation is in progress`) มักเกิดตอน stream ถูกฆ่ากลางเฟรม
แก้ด้วยการถอดสาย USB เสียบใหม่ แล้วรัน `doctor` ซ้ำ

## จอ LED

```bash
python -m amg65 list                 # ดู scene ทั้งหมด
python -m amg65 show clock           # นาฬิกา + Space Invader
python -m amg65 show vis             # spectrum ตามเสียงที่ลำโพงเล่นอยู่
python -m amg65 show nowplaying      # ชื่อเพลงวิ่ง (ดึงจาก SMTC)
python -m amg65 show sysmon          # CPU / RAM / เน็ต
python -m amg65 show dino            # เกมไดโน — กด space กระโดด, r เริ่มใหม่
python -m amg65 show pong            # ปิงปองเล่นเอง
python -m amg65 show marquee --text "SAWATDEE"
```

ธงที่ใช้ร่วมกันได้:

| ธง | ความหมาย |
|---|---|
| `--delay N` | หน่วงระหว่าง HID packet เป็น ms — **ตัวกำหนด FPS ตัวจริง** |
| `--lean` | ตัด header/flush ต่อเฟรม (19 → 16 reports) |
| `--fps N` | บังคับ FPS (ปกติ scene กำหนดเอง) |
| `--preview` | วาดลงเทอร์มินัลด้วย |
| `--no-device` | ไม่ต้องต่อคีย์บอร์ด — preview อย่างเดียว |
| `--seconds N` | เล่นกี่วินาทีแล้วออก |

ออกจากโปรแกรมด้วย `Ctrl+C` หรือกด `q`

### เรื่อง FPS — อย่าลด delay ต่ำกว่า 8.5 ms

เพดาน live stream ของฮาร์ดแวร์นี้คือ **ราว 5-6 FPS** และ **8.5 ms คือค่าเดียวที่ภาพสะอาด**
วัดมาครบทุกค่าแล้ว (ดู §9 ใน `AMG65_REVERSE_ENGINEERING.md`)

| delay | FPS | ผล |
|---:|---:|---|
| 8.5 ms | 5.3 | สะอาด — ใช้ค่านี้ |
| 6.0 | 6.5 | มีดอตโผล่ผิดตำแหน่ง |
| 4.0 | 8.3 | มีดอตโผล่ผิดตำแหน่ง |
| 2.0 | 10.8 | ดอตหลง + endpoint ค้างใน 12 วินาที |
| 0.0 | 18.3 | ค้างทุกครั้ง |

ส่งเร็วเกินไปเครื่องจะ **ทิ้ง report เงียบ ๆ** โดย `hid_write` ยังคืน 65 ปกติไม่มี error
ข้อมูลที่เหลือเลื่อนไป 64 ไบต์ = 21.3 พิกเซล พิกเซลจึงไปโผล่ผิดตำแหน่ง
ถ้าหนักกว่านั้นคิวล้นจน endpoint ค้างถาวร ต้องถอดสาย USB เสียบใหม่
**ดอตหลงคือสัญญาณเตือนว่ากำลังจะค้าง**

⚠️ ถ้าจะทดลองเอง อย่าเชื่อการกวาดสั้น ๆ — มันให้ผลลวงมาแล้วสองครั้ง
ต้อง soak ยาวและดูด้วยตา เพราะโปรแกรมตรวจดอตหลงไม่ได้

```bash
python bench_fps.py --soak 8.5 --delay-data 6 --seconds 180
```

หมายเหตุ: `time.sleep(1ms)` บน Windows จริง ๆ กินราว 2.8ms เพราะ timer resolution หยาบ
ค่า delay ต่ำ ๆ จึงไม่ได้ผลเป็นเส้นตรงตามที่ตั้ง

## ไฟใต้ปุ่ม

```bash
python -m amg65 light static --rgb 255 0 0 --brightness 5
python -m amg65 light breath --rgb 180 0 255 --brightness 4 --speed 3
python -m amg65 light spectrum --colorful --brightness 5 --speed 3
python -m amg65 light off
python -m amg65 keys --key w 255 0 0 --key a 0 255 0 --key s 0 0 255 --hold
python -m amg65 keys --random
```

ชื่อปุ่มที่รองรับดูจาก `KEY_INDEX` ใน `amg65/keyboard.py`

⚠️ ไฟรายปุ่ม (`keys`) เป็น live preview — เฟิร์มแวร์ดับไฟเองเมื่อข้อมูลหยุดส่ง
ต้องใช้ `--hold` ถ้าอยากให้ค้าง

คำสั่งรูปแบบเดิม (`python amg65_rgb.py static --rgb 255 0 0`) ยังใช้ได้ โปรแกรมแปลงให้อัตโนมัติ

## เขียน scene เอง

scene มีหน้าที่เดียวคือวาดลง canvas — ห้ามยุ่งกับ HID และห้าม sleep เอง
(engine เป็นคนคุมอุปกรณ์กับจังหวะ) ข้อบังคับนี้ทำให้ทุก scene รันบน preview ได้

```python
from amg65.matrix import Canvas
from amg65.scenes.base import Scene

class HelloScene(Scene):
    name = "hello"
    fps = 20.0

    def render(self, canvas: Canvas, elapsed: float, frame: int) -> None:
        canvas.text("HI", 0, (254, 0, 0))
```

ลงทะเบียนใน `amg65/scenes/__init__.py` แล้วเรียกด้วย `python -m amg65 show hello --no-device`

## โครงไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `amg65/device.py` | หา HID endpoint + ส่ง report แบบ retry/reopen เอง |
| `amg65/matrix.py` | Canvas 63×5 + โปรโตคอลส่งเฟรม (จัด raw order ให้ตอนส่ง) |
| `amg65/keyboard.py` | ไฟใต้ปุ่ม + `KEY_INDEX` / `LIGHT_ORDER` |
| `amg65/font.py` | ฟอนต์ 5 แถว ความกว้างไม่คงที่ |
| `amg65/engine.py` | วนเฟรม สลับ scene รับปุ่ม |
| `amg65/preview.py` | วาด canvas ลงเทอร์มินัล |
| `amg65/scenes/` | scene ทั้งหมด |
| `bench_fps.py` | วัดเพดาน FPS |
| `AMG65_REVERSE_ENGINEERING.md` | รายงานถอดโปรโตคอลฉบับเต็ม |
