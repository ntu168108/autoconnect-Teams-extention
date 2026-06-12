@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Build Teams Auto-Joiner (Windows) ===
python -m pip install --upgrade pyinstaller selenium requests || goto :err
python -m PyInstaller --onefile --console --name TeamsAutoJoiner --collect-submodules selenium --distpath dist --workpath build --specpath build src/main.py || goto :err
copy /y config.json.example dist\ >nul
echo.
echo Xong! File: dist\TeamsAutoJoiner.exe
pause
exit /b 0
:err
echo BUILD LOI — xem thong bao phia tren.
pause
exit /b 1
