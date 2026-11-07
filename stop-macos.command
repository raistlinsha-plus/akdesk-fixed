#!/bin/zsh

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
EXPECTED_VERSION="1.4.1"

fail() {
  echo
  echo "停止失败：$1"
  exit 1
}

echo ""
echo "AKDesk Fixed · macOS 本地停止器"

PYTHON="${AKDESK_PYTHON:-$ROOT/.venv/bin/python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  PYTHON="$(command -v python3 || true)"
fi
[[ -n "$PYTHON" && -f "$ROOT/scripts/launcher.py" ]] || fail "缺少 Python 或启动组件，请在原启动窗口按 Control+C"
exec "$PYTHON" "$ROOT/scripts/launcher.py" stop "$EXPECTED_VERSION"
