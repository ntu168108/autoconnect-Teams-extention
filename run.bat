@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Teams Auto-Joiner

rem --- Tim Python (uu tien lenh 'python', neu khong co thi dung 'py') ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py"
)

if not defined PY (
    echo.
    echo [LOI] Khong tim thay Python tren may.
    echo Hay cai dat Python tai: https://www.python.org/downloads/
    echo Nho tick "Add Python to PATH" khi cai.
    echo.
    pause
    exit /b 1
)

rem --- Chay bot (mo form cau hinh trong trinh duyet) ---
%PY% src/auto_joiner.py %*

echo.
echo === Bot da dung. Nhan phim bat ky de dong cua so nay. ===
pause >nul
