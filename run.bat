@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Teams Auto-Joiner
setlocal enabledelayedexpansion

rem Ten bien "ProgramFiles(x86)" co dau ngoac dong, dung thang trong khoi
rem if(...) se lam cmd tuong nham la ket thuc khoi -> gan ra bien rieng truoc.
set "PF=%ProgramFiles%"
set "PF86=%ProgramFiles(x86)%"

rem Dau '!' la ky tu dac biet khi bat delayed expansion -> phai viet '^!'.

echo.
echo ========================================
echo    KIEM TRA YEU CAU HE THONG
echo ========================================
set "FAILED=0"

rem --- 1. Python: uu tien lenh 'python', neu khong co thi dung 'py' ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py"
)

if not defined PY (
    echo   [LOI] Khong tim thay Python tren may.
    echo         -^> Cai dat tai: https://www.python.org/downloads/
    echo         -^> Nho tick "Add Python to PATH" khi cai.
    set "FAILED=1"
) else (
    for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
    echo   [OK]  Python: !PYVER!
)

rem --- 2. Thu vien Python: tu cai neu thieu, roi kiem tra lai ---
if defined PY (
    %PY% -c "import selenium, requests" >nul 2>nul
    if errorlevel 1 (
        echo   [^!]   Thieu thu vien - dang tu cai lan dau, vui long doi...
        %PY% -m pip install -r requirements.txt
        %PY% -c "import selenium, requests" >nul 2>nul
        if errorlevel 1 (
            echo   [LOI] Cai thu vien that bai.
            echo         -^> Thu chay tay: %PY% -m pip install -r requirements.txt
            set "FAILED=1"
        ) else (
            echo   [OK]  Da cai thu vien xong
        )
    ) else (
        echo   [OK]  Thu vien Python: day du
    )
)

rem --- 3. Chrome / Edge: danh sach khop voi webui._find_browser() ---
set "BROWSER="
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>nul && set "BROWSER=Google Chrome"
rem 'if cond cmd && cmd2' co cach phan tich de gay hieu nham -> tach hai dong.
if not defined BROWSER (
    reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>nul
    if not errorlevel 1 set "BROWSER=Google Chrome"
)
if not defined BROWSER if exist "%PF%\Google\Chrome\Application\chrome.exe" set "BROWSER=Google Chrome"
if not defined BROWSER if exist "%PF86%\Google\Chrome\Application\chrome.exe" set "BROWSER=Google Chrome"
if not defined BROWSER if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "BROWSER=Google Chrome"
if not defined BROWSER (
    reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>nul
    if not errorlevel 1 set "BROWSER=Microsoft Edge"
)
if not defined BROWSER if exist "%PF86%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=Microsoft Edge"
if not defined BROWSER if exist "%PF%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=Microsoft Edge"

if defined BROWSER (
    echo   [OK]  Trinh duyet: !BROWSER!
) else (
    echo   [LOI] Khong tim thay Chrome / Edge.
    echo         -^> Cai dat Chrome tai: https://www.google.com/chrome/
    set "FAILED=1"
)

rem --- 4. config.json ---
if exist "config.json" (
    echo   [OK]  config.json ton tai
) else (
    echo   [^!]   config.json chua co - se mo form cau hinh khi chay.
)

echo ========================================

if "%FAILED%"=="1" (
    echo.
    echo Mot so yeu cau chua duoc dap ung. Vui long sua truoc khi chay.
    echo.
    pause
    exit /b 1
)

echo.
echo Tat ca yeu cau da san sang^! Dang khoi dong bot...
echo.

%PY% src/main.py %*

echo.
echo === Bot da dung. Nhan phim bat ky de dong cua so nay. ===
pause >nul
