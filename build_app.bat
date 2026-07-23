@echo off
REM ── แพ็ก AMG65 เป็นแอป Windows (System Tray) ──
REM ต้องมี: pip install pyinstaller
REM --onedir (โฟลเดอร์) แทน --onefile: เชื่อถือได้กว่า ไม่โดน antivirus ล็อกตอน self-extract
REM ผลลัพธ์: dist\amg65\amg65.exe  (แจกทั้งโฟลเดอร์ dist\amg65\ หรือ zip)

pyinstaller --onedir --noconsole --name amg65 --noconfirm ^
  --collect-all hid ^
  --collect-all pystray ^
  --collect-all PIL ^
  --collect-all psutil ^
  --collect-all numpy ^
  --collect-all soundcard ^
  --collect-all winsdk ^
  amg65_app.py

echo.
echo ===== เสร็จ! รันได้ที่ dist\amg65\amg65.exe =====
echo (ถ้าอยากเห็น log ตอนดีบัก เปลี่ยน --noconsole เป็น --console แล้ว build ใหม่)
pause
