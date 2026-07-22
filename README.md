# AMG65 RGB Controller

โปรแกรม Python สำหรับควบคุมไฟหลักของ **LEOBOG AMG65** ผ่าน USB HID Output Report
`MI_02 / Usage Page 0xFF68` บน Windows
โปรโตคอลได้รับการตรวจจากแพ็กเก็ตของ `DeviceDriver.exe` รุ่น 1.0.3.2 โดยตรง
โดยไม่แฟลชหรือแก้เฟิร์มแวร์

## ติดตั้ง

ต่อคีย์บอร์ดด้วยสาย USB แล้วเปิด PowerShell ในโฟลเดอร์นี้:

```powershell
py -m pip install -r requirements.txt
```

ถ้าโปรแกรมทางการ LEOBOG เปิดอยู่แล้วเกิดข้อผิดพลาด ให้ปิดโปรแกรมนั้นจาก System Tray ก่อน

## ตัวอย่าง

ไฟนิ่งสีแดง ความสว่างสูงสุด:

```powershell
py .\amg65_rgb.py static --rgb 255 0 0 --brightness 5
```

ไฟหายใจสีม่วง:

```powershell
py .\amg65_rgb.py breath --rgb 180 0 255 --brightness 4 --speed 3
```

ไฟ Spectrum:

```powershell
py .\amg65_rgb.py spectrum --colorful --brightness 5 --speed 3
```

ปิดไฟ:

```powershell
py .\amg65_rgb.py off
```

กำหนดไฟรายปุ่ม (ปุ่มที่ไม่ได้ระบุจะดับ):

```powershell
py .\amg65_rgb.py per-key --key w 255 0 0 --key a 0 255 0 --key s 0 0 255 --key d 255 255 0 --brightness 5
```

ดู packet โดยไม่ส่งจริง:

```powershell
py .\amg65_rgb.py static --rgb 0 255 255 --dry-run
```

ชื่อปุ่มที่รองรับดูได้จากตัวแปร `KEY_INDEX` ใน `amg65_rgb.py`
