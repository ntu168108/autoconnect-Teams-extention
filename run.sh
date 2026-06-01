#!/usr/bin/env bash
# Chay bot Teams Auto-Joiner tren macOS / Linux

cd "$(dirname "$0")"

# Tim Python (uu tien python3, sau do python)
PY=""
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
fi

if [ -z "$PY" ]; then
    echo ""
    echo "[LOI] Khong tim thay Python tren may."
    echo "Hay cai dat Python tai: https://www.python.org/downloads/"
    echo ""
    exit 1
fi

# Chay bot
"$PY" src/auto_joiner.py "$@"

echo ""
echo "=== Bot da dung. ==="
