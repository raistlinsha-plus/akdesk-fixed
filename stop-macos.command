#!/bin/zsh

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
URL="http://127.0.0.1:8765"
EXPECTED_VERSION="1.0.0"

fail() {
  echo
  echo "停止失败：$1"
  exit 1
}

echo ""
echo "AKDesk Fixed · macOS 本地停止器"

command -v lsof >/dev/null 2>&1 || \
  fail "未找到 lsof，无法安全识别 8765 端口上的服务"

PID="$(lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null | head -n 1)"
if [[ -z "$PID" ]]; then
  echo "AKDesk 服务当前没有运行。"
  exit 0
fi

INFO="$(curl -fsS "$URL/api/v1/info" 2>/dev/null || true)"
if [[ -z "$INFO" ]] || \
  ! print -r -- "$INFO" | grep -q '"name":"AKDesk Fixed"' || \
  ! print -r -- "$INFO" | grep -q "\"version\":\"$EXPECTED_VERSION\""; then
  fail "8765 端口上的进程不是可确认的 AKDesk v$EXPECTED_VERSION，未执行终止"
fi

echo "正在正常停止 AKDesk（PID $PID）……"
kill -TERM "$PID" 2>/dev/null || \
  fail "无法向服务发送终止信号，请在“活动监视器”中结束 PID $PID"

for _ in {1..40}; do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "AKDesk 已停止。"
    exit 0
  fi
  sleep 0.25
done

fail "服务在 10 秒内没有退出，请在“活动监视器”中结束 PID $PID"
