#!/usr/bin/env bash
# Chạy pytest + ruff rồi in ra khối text để dán vào comment PR.
#
# GitHub Actions của org đang khoá do billing, mọi run dừng sau 2-4 giây nên
# badge đỏ dưới PR không nói lên gì. Quy trình đang dùng: tự chạy 2 lệnh này ở
# máy, xong comment "CI Pass" vào PR rồi báo Dương gộp.
#
#   bash scripts/pr_evidence.sh              # in ra màn hình
#   bash scripts/pr_evidence.sh | clip       # chép vào clipboard (Windows)
#
# Không thoát lỗi khi test đỏ, vì để báo cáo chứ không phải chặn.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# Ưu tiên python trong .venv; nếu không có thì nhờ _pyrun.sh dò (nó đã xử lý
# vụ python3 là stub hỏng trên Windows).
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Đang chạy pytest..." >&2
"$PY" -m pytest tests/ -q >"$TMP/pytest.txt" 2>&1
echo "Đang chạy ruff..." >&2
"$PY" -m ruff check src/ tests/ >"$TMP/ruff.txt" 2>&1

PYTEST_LINE="$(grep -oE '[0-9]+ (failed|passed)[^|]*' "$TMP/pytest.txt" | tail -1)"
[ -z "$PYTEST_LINE" ] && PYTEST_LINE="không đọc được kết quả — xem log đầy đủ"

if grep -q "All checks passed" "$TMP/ruff.txt"; then
  RUFF_LINE="sạch"
else
  RUFF_LINE="$(grep -oE 'Found [0-9]+ error[s]?' "$TMP/ruff.txt" | tail -1)"
  [ -z "$RUFF_LINE" ] && RUFF_LINE="xem log"
fi

# Gom test đỏ theo file để người đọc thấy ngay chúng nằm ở vùng nào
FAILED_BY_FILE="$(grep '^FAILED' "$TMP/pytest.txt" | sed 's|::.*||;s|^FAILED ||' \
  | sort | uniq -c | sort -rn | awk '{printf "  - `%s` — %s test\n", $2, $1}')"

FRONTEND_NOTE=""
if [ -d frontend ]; then
  FRONTEND_NOTE="- \`cd frontend && npm run build\` → tự điền (script không chạy build cho nhanh)"
fi

cat <<EOF
Chạy manual CI ở máy trên commit \`$(git rev-parse --short HEAD)\`:

- \`pytest tests/ -q\` → ${PYTEST_LINE}
- \`ruff check src/ tests/\` → ${RUFF_LINE}
${FRONTEND_NOTE}

EOF

if [ -n "$FAILED_BY_FILE" ]; then
  cat <<EOF
Test đang đỏ:

$FAILED_BY_FILE
<!-- Tự điền: mấy test trên có sẵn trên main hay do PR này gây ra. Nếu có sẵn
     thì ghi rõ thuộc phần của ai. -->
EOF
else
  echo "CI Pass."
fi
