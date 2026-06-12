#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== Build Teams Auto-Joiner (macOS) ==="
python3 -m pip install --upgrade pyinstaller selenium requests
python3 -m PyInstaller --onefile --console --name TeamsAutoJoiner \
  --collect-submodules selenium \
  --distpath dist --workpath build --specpath build src/main.py
cp config.json.example dist/
cat > "dist/Chạy bot.command" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")"
./TeamsAutoJoiner
echo ""
echo "=== Bot đã dừng. Nhấn phím bất kỳ để đóng. ==="
read -n 1 -s -r
EOF
chmod +x "dist/Chạy bot.command" dist/TeamsAutoJoiner
echo "Xong! Thư mục: dist/"
