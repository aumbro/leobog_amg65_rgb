@echo off
REM ═══════════════════════════════════════════════════════════════════
REM  จับ USB packet ตอนโปรแกรม LEOBOG ทางการสตรีมภาพ
REM  เป้าหมาย: ดูว่าทางการทำอะไรต่างจากเรา จนสตรีมได้ไม่ค้าง
REM
REM  *** ต้องคลิกขวา -> Run as administrator *** (USBPcap ต้องสิทธิ์ admin)
REM
REM  วิธีใช้:
REM    1. ปิดแอป amg65 ให้หมดก่อน (python -m amg65 stop)
REM    2. คลิกขวาไฟล์นี้ -> Run as administrator
REM    3. พอขึ้น "กำลังจับ..." ให้เปิดโปรแกรม LEOBOG แล้วสั่งแสดงภาพบนจอ
REM       *** ต้องเห็นจอบนคีย์บอร์ดเปลี่ยนจริง ๆ *** ไม่งั้นไม่มีอะไรให้จับ
REM       ปล่อยให้มันสตรีมสัก 20-30 วินาที
REM    4. กลับมาที่หน้าต่างนี้ กด Ctrl+C เพื่อหยุด
REM    5. บอก Claude ว่าจับเสร็จแล้ว
REM
REM  หมายเหตุ: รอบก่อนใช้ --devices ไปกรอง ทำให้คีย์บอร์ดหลุดไม่ถูกจับ
REM            รอบนี้ใช้ -A = จับทุกอุปกรณ์บน bus นั้น
REM ═══════════════════════════════════════════════════════════════════

set USBPCAP="C:\Program Files\USBPcap\USBPcapCMD.exe"
set OUT=%~dp0capture

del /q "%OUT%_bus1.pcap" "%OUT%_bus2.pcap" 2>nul

echo.
echo ====================================================
echo  จับ USB ทุกอุปกรณ์ ทั้งสอง bus พร้อมกัน
echo  ไฟล์ผลลัพธ์: capture_bus1.pcap / capture_bus2.pcap
echo ====================================================
echo.
echo  ^>^> เปิดโปรแกรม LEOBOG แล้วสั่งแสดงภาพบนจอคีย์บอร์ด
echo  ^>^> ต้องเห็นจอบนคีย์บอร์ดเปลี่ยนจริง ๆ ระหว่างจับ
echo  ^>^> ปล่อยให้สตรีม 20-30 วินาที แล้วกลับมากด Ctrl+C ที่นี่
echo.

start "USBPcap bus2" %USBPCAP% -d \\.\USBPcap2 -A -o "%OUT%_bus2.pcap"
%USBPCAP% -d \\.\USBPcap1 -A -o "%OUT%_bus1.pcap"

echo.
echo ===== หยุดจับแล้ว =====
dir /b "%~dp0capture_bus*.pcap"
pause
