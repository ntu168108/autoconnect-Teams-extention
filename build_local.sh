#!/usr/bin/env bash
# Dong goi bot thanh 1 file chay duy nhat (macOS + Linux).
set -e
cd "$(dirname "$0")"

OS=$(uname -s)
echo "=== Build Teams Auto-Joiner ($OS) ==="

python3 -m pip install --upgrade pyinstaller selenium requests
python3 -m PyInstaller --onefile --console --name TeamsAutoJoiner \
  --collect-submodules selenium \
  --distpath dist --workpath build --specpath build src/main.py

cp config.json.example dist/

if [ "$OS" = "Darwin" ]; then
    LAUNCHER="dist/Chạy bot.command"
else
    LAUNCHER="dist/chay-bot.sh"
fi

cat > "$LAUNCHER" <<'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
./TeamsAutoJoiner
echo ""
echo "=== Bot đã dừng. Nhấn phím bất kỳ để đóng. ==="
read -n 1 -s -r
EOF

chmod +x "$LAUNCHER" dist/TeamsAutoJoiner
echo "Xong! Thư mục: dist/  (chạy: $LAUNCHER)"
