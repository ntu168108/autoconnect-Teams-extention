#!/bin/bash
cd "$(dirname "$0")"

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GRN}[OK]${NC}  $1"; }
fail() { echo -e "  ${RED}[LOI]${NC} $1"; FAILED=1; }
warn() { echo -e "  ${YLW}[!]${NC}   $1"; }

echo ""
echo "========================================"
echo "   KIEM TRA YEU CAU HE THONG"
echo "========================================"
FAILED=0

# 1. Python
PY=""
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
fi

if [ -z "$PY" ]; then
    fail "Khong tim thay Python."
    echo "       -> Cai dat tai: https://www.python.org/downloads/"
else
    PY_VER=$("$PY" --version 2>&1)
    ok "Python: $PY_VER"
fi

# 2. Thu vien Python — tu cai neu thieu (chi lan dau)
if [ -n "$PY" ]; then
    if "$PY" -c "import selenium, requests" 2>/dev/null; then
        ok "Thu vien Python: day du"
    else
        warn "Thieu thu vien — dang tu cai (lan dau, vui long doi)..."
        "$PY" -m pip install -r requirements.txt
        if "$PY" -c "import selenium, requests" 2>/dev/null; then
            ok "Da cai thu vien xong"
        else
            fail "Cai thu vien that bai. Thu chay tay: $PY -m pip install -r requirements.txt"
        fi
    fi
fi

# 3. Chrome hoac Edge
BROWSER_FOUND=0
for b in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
do
    if [ -x "$b" ]; then
        BNAME=$(basename "$b")
        ok "Trinh duyet: $BNAME"
        BROWSER_FOUND=1
        break
    fi
done
if [ "$BROWSER_FOUND" -eq 0 ]; then
    fail "Khong tim thay Chrome / Edge / Chromium."
    echo "       -> Cai dat Chrome tai: https://www.google.com/chrome/"
fi

# 4. config.json
if [ -f "config.json" ]; then
    ok "config.json ton tai"
else
    warn "config.json chua co — se mo form cau hinh khi chay."
fi

echo "========================================"

if [ "$FAILED" -ne 0 ]; then
    echo -e "\n${RED}Mot so yeu cau chua duoc dap ung. Vui long sua truoc khi chay.${NC}\n"
    read -n 1 -s -r -p "Nhan phim bat ky de dong..."
    exit 1
fi

echo -e "\n${GRN}Tat ca yeu cau da san sang! Dang khoi dong bot...${NC}\n"

# Chay bot
"$PY" src/main.py "$@"

echo ""
echo "=== Bot da dung. Nhan phim bat ky de dong cua so nay. ==="
read -n 1 -s -r
