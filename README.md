# AMG65 RGB Controller

> **English summary** — Open-source driver for the **LEOBOG AMG65** keyboard on Windows.
> Controls the per-key RGB and the 63×5 LED matrix over USB HID, with no firmware flashing.
> The protocol was reverse-engineered from `DeviceDriver.exe` 1.0.3.2 packet captures.
>
> **What it does:** 20 built-in firmware lighting effects, per-key colours, and live or
> stored animations on the LED matrix — a clock, an audio spectrum analyser driven by
> WASAPI loopback, Windows now-playing text, a system monitor, and playable games.
> Scenes render to a plain canvas and can be previewed in the terminal, so you can
> develop without the keyboard attached.
>
> **Key findings from the reverse engineering** (details in `AMG65_REVERSE_ENGINEERING.md`,
> written in Thai):
> - The matrix is **63×5 = 315 pixels**, but device memory order is *not* left-to-right.
>   It is four row-major 14×5 blocks followed by a separate 7×5 right panel.
> - **Live streaming tops out at ~5-6 FPS.** Sending faster makes the device *silently
>   drop reports* — `hid_write` still returns success — which shifts the remaining data by
>   64 bytes (21.3 pixels) and scatters pixels to wrong positions. Push harder and the
>   HID output endpoint wedges permanently until you unplug and replug the cable.
>   Both vendor endpoints (`MI_02` and `MI_03`) can wedge this way.
> - **Byte 2 of the upload header (`0x0C`) is a per-frame delay, 10 ms per unit.**
>   The official software hardcodes it to 8.3 FPS — but the panel runs at up to **83 FPS**.
>   Uploading an animation into the device is therefore ~15× smoother than streaming,
>   and it keeps playing with no host process running at all.
>
> Quick start: `pip install -r requirements.txt`, then `python -m amg65 doctor`,
> `python -m amg65 list`, `python -m amg65 show clock`.
> Full documentation below is in Thai. MIT licensed.

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

## ทำเป็นแอป (.exe ดับเบิลคลิกเปิด)

ไม่อยากพิมพ์คำสั่งทุกครั้ง แพ็กเป็นแอป Windows ที่เปิด tray ให้เลย:

```powershell
pip install pyinstaller
.\build_app.bat
```

ได้ `dist\amg65\amg65.exe` — ดับเบิลคลิกเปิด ไอคอนขึ้นถาดระบบ คลิกขวาสลับ scene
แจกทั้งโฟลเดอร์ `dist\amg65\` ได้เลย (ไม่ต้องมี Python บนเครื่องปลายทาง)

ปิดแอปจากเมนู "ออก" ของไอคอน หรือสั่ง `python -m amg65 stop` จากที่ไหนก็ได้
(ถ้าลง exe ไว้จะสั่งจาก exe ก็ได้: `amg65.exe` ไม่มี subcommand = เปิด tray;
คำสั่งอื่นยังต้องใช้ `python -m amg65`)

อยากให้เปิดเองตอน Windows บูต: วางช็อตคัตของ `amg65.exe` ใน
`shell:startup` (กด Win+R พิมพ์ `shell:startup` แล้ววางไฟล์)

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

## เก็บแอนิเมชันลงเครื่อง (ลื่นกว่า stream มาก)

live stream ตันที่ 5-6 FPS แต่ถ้าอัปโหลดเก็บลงเครื่อง เฟิร์มแวร์จะเล่นวนเอง
**ปิดโปรแกรมได้ ปิดคอมได้ ภาพยังวิ่งอยู่** และระหว่างเล่นไม่มีทราฟฟิก USB เลย
จึงไม่มีโอกาสที่ endpoint จะค้าง

```bash
python -m amg65 upload some.gif                        # GIF หรือภาพนิ่ง
python -m amg65 upload --scene rainbow --frames 60     # เบคจาก scene ที่มีอยู่
python -m amg65 upload --scene marquee --text "SAWATDEE AUM" --frames 83
python -m amg65 upload some.gif --preview --no-upload  # ดูในเทอร์มินัลก่อน
```

| ธง | ความหมาย |
|---|---|
| `--frames N` | จำนวนเฟรม สูงสุด 255 (ไฟล์ที่ยาวกว่าจะถูกสุ่มเก็บให้กระจายทั้งคลิป) |
| `--fit cover\|fit\|stretch` | วิธีย่อภาพลงจอ 63×5 ซึ่งอัตราส่วน 12.6:1 |
| `--brightness 0-1` | หรี่ความสว่าง |
| `--play-fps N` | **ความเร็วเล่นบนเครื่อง 2-83 FPS** (ใช้เป็น FPS ตอนเรนเดอร์ด้วย) |
| `--scroll-speed N` | ความเร็วเลื่อนข้อความ px/วินาที (ไม่ระบุ = คำนวณให้ลูปต่อเนียนพอดี) |
| `--chunk-delay 170` | หน่วงระหว่างก้อน 4KB (ms) เพิ่มถ้าอัปโหลดค้างบ่อย |
| `--preview` / `--no-upload` | ดูก่อน / ไม่ต้องส่งเข้าเครื่อง |

### ความเร็วเล่น — จอนี้ทำได้ถึง 83 FPS

ไบต์ `0x0C` ที่โปรแกรมทางการใส่มาตลอดคือ **ค่าหน่วงต่อเฟรม หน่วยละ 10 ms**
ทางการตั้งไว้ = 8.3 FPS ซึ่งเป็นแค่ 1/10 ของที่ฮาร์ดแวร์ทำได้

```text
เวลาต่อเฟรม = min(10 × speed, 500) + 2 ms      → เร็วสุด ~83 FPS, ช้าสุด 2 FPS
```

เทียบ live stream ที่ตันอยู่ 5.3 FPS แล้ว ทางนี้เร็วกว่า **15.7 เท่า**

⚠️ **สามค่านี้ผูกกันเป็นสมการเดียว เลือกได้แค่สองค่า:**

```text
จำนวนเฟรม = ระยะทางที่ต้องเลื่อน ÷ ความเร็วเลื่อน × FPS ที่เล่น    (ต้อง ≤ 255)
```

เร่ง `--play-fps` โดยไม่เพิ่มเฟรม = บังคับให้ภาพวิ่งเร็วขึ้นตามไปด้วย
ถ้าอยากลื่นแต่ไม่อยากให้เร็ว ต้องเพิ่มเฟรมด้วย และถ้าชนเพดาน 255 แล้วก็ต้องยอมลด FPS ลง

### ขนาดที่เชื่อถือได้

| ขนาด | ผล |
|---|---|
| 35 ก้อน (150 เฟรม) | ผ่าน |
| 47 ก้อน (200 เฟรม) | ผ่าน |
| **58 ก้อน (250 เฟรม)** | **พัง 3 ครั้งติด** — ค้าง 1 ภาพเพี้ยน 2 |
| 59 ก้อน (255 เฟรม) | ผ่านครั้งเดียว ยังเชื่อไม่ได้ |

โปรแกรมจะเตือนเมื่อเกิน 47 ก้อน แต่ไม่ห้าม **ถ้าภาพเพี้ยนให้ลด `--frames` แล้วลด
`--play-fps` ตามลงไปด้วย** จะได้ความเร็วภาพเท่าเดิมโดยข้อมูลเล็กลง

⚠️ ถ้าอัปโหลดแล้วภาพมั่วเป็นบางครั้ง **ลองอัปโหลดซ้ำ** — เคยเจอครั้งหนึ่งตอนอัปโหลด
แอนิเมชันหลายเฟรมต่อจากภาพนิ่งเฟรมเดียว ยิงซ้ำแล้วหาย

ใช้กับ scene ที่ต้องการข้อมูลสด (`clock` `vis` `sysmon` `nowplaying`) ไม่ได้ — ต้องเป็นลูปที่วนซ้ำได้

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
