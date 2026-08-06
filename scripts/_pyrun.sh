#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

# command -v chỉ kiểm tra tồn tại trên PATH — trên Windows, "python3" và đôi
# khi cả "python" có thể là App Execution Alias trỏ tới Microsoft Store
# (không phải Python thật), gọi vào chỉ in ra "Python was not found; run
# without arguments to install..." và thoát lỗi. Phải verify --version chạy
# thật (works()) trước khi chấp nhận ứng viên, không chỉ dựa vào command -v.
works() { "$1" --version >/dev/null 2>&1; }

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && works "$cand"; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ] && command -v py >/dev/null 2>&1 && works "py -3"; then
  PY="py -3"
fi

if [ -z "$PY" ]; then
  # PATH lookup failed hoặc chỉ toàn stub — probe standard Windows install locations.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ] && works "$cand"; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
