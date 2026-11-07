#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
EXPECTED_VERSION="1.4.1"
REQUIREMENTS_LOCK="$ROOT/backend/requirements.lock"
REQUIREMENTS_STAMP="$VENV/.akdesk-requirements.sha256"

cleanup_install_log() {
  if [[ -n "${PIP_LOG:-}" ]]; then
    rm -f "$PIP_LOG"
  fi
}
trap cleanup_install_log EXIT

fail() {
  echo
  echo "启动失败：$1"
  echo "尚未安装成功也可先体验固定合成数据：https://raistlinsha-plus.github.io/akdesk-fixed/"
  echo "反馈时只描述故障类别和操作步骤，不粘贴个人路径、密钥或原始安装日志。"
  if [[ "${AKDESK_NONINTERACTIVE:-0}" != "1" ]]; then
    echo "按任意键关闭窗口。"
    read -k 1
    echo
  fi
  exit 1
}

echo ""
echo "AKDesk Fixed · macOS 本地启动器"

PYTHON="${AKDESK_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  for CANDIDATE in \
    "$VENV/bin/python" \
    python3.13 python3.12 python3.11 python3 \
    /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
    /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11; do
    if command -v "$CANDIDATE" >/dev/null 2>&1 && \
      "$CANDIDATE" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))' 2>/dev/null; then
      PYTHON="$(command -v "$CANDIDATE")"
      break
    fi
  done
fi
[[ -n "$PYTHON" ]] || fail "未找到 Python 3。请先执行 brew install python@3.13"

if ! "$PYTHON" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))'; then
  fail "需要 Python 3.11–3.13。推荐执行 brew install python@3.13"
fi

[[ -f "$ROOT/scripts/launcher.py" ]] || fail "发布包缺少启动组件，请重新下载完整 ZIP 并解压"
PORT="$("$PYTHON" "$ROOT/scripts/launcher.py" port)" || fail "请检查端口配置"
URL="http://127.0.0.1:$PORT"
if "$PYTHON" "$ROOT/scripts/launcher.py" probe "$EXPECTED_VERSION"; then
  echo "同一安装、模式与数据目录的服务已运行：$URL"
  if [[ "${AKDESK_NO_BROWSER:-0}" != "1" ]]; then
    open "$URL"
  fi
  exit 0
else
  [[ "$?" == "3" ]] || fail "未复用已有实例，请按上方提示处理"
fi

[[ -f "$ROOT/scripts/preflight.py" ]] || fail "发布包缺少启动预检，请重新下载完整 ZIP 并解压"
"$PYTHON" "$ROOT/scripts/preflight.py" --root "$ROOT" || \
  fail "启动预检未通过，请按上方对应步骤处理后重试"

if [[ -e "$VENV" ]] && ! "$VENV/bin/python" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))' 2>/dev/null; then
  fail "现有 Python 环境已失效或版本不受支持。请停止服务，将项目中的 .venv 文件夹重命名为 .venv-old，再启动以重建环境；data 和用户数据目录无需改动"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "首次运行：正在创建独立 Python 环境……"
  "$PYTHON" -m venv "$VENV" || fail "无法创建 Python 虚拟环境"
fi

[[ -f "$REQUIREMENTS_LOCK" ]] || fail "发布包缺少 backend/requirements.lock，请重新下载完整版本"
REQUIREMENTS_HASH="$(shasum -a 256 "$REQUIREMENTS_LOCK" | awk '{print $1}')"
INSTALLED_HASH="$(cat "$REQUIREMENTS_STAMP" 2>/dev/null || true)"

if [[ "$INSTALLED_HASH" != "$REQUIREMENTS_HASH" ]] || \
  ! "$VENV/bin/python" -c 'from pathlib import Path; import importlib.metadata as m, sys; expected = next(line.partition("==")[2].strip() for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.startswith("akshare==")); assert m.version("akshare") == expected; import fastapi, h2, httpx, openpyxl, pandas, uvicorn' "$REQUIREMENTS_LOCK" 2>/dev/null; then
  echo "首次运行：正在安装行情与本地服务依赖（通常需要 2–5 分钟）……"
  PYTHON_CERT="$("$PYTHON" -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
  if [[ -n "$PYTHON_CERT" && -f "$PYTHON_CERT" ]]; then
    export PIP_CERT="${PIP_CERT:-$PYTHON_CERT}"
  fi
  PIP_LOG="$(mktemp -t akdesk-install)" || fail "无法创建安装临时文件，请检查磁盘空间和临时目录权限"
  if ! PIP_DISABLE_PIP_VERSION_CHECK=1 "$VENV/bin/python" -m pip install \
    -r "$REQUIREMENTS_LOCK" >"$PIP_LOG" 2>&1; then
    if grep -Eqi 'CERTIFICATE_VERIFY_FAILED|SSL:|certificate verify' "$PIP_LOG"; then
      RECOVERY="证书校验失败。请运行 Python 安装目录中的 Install Certificates.command 后重试，不要关闭 TLS 校验"
    elif grep -Eqi 'No space left|Disk quota' "$PIP_LOG"; then
      RECOVERY="磁盘空间不足。请释放至少 1 GB 空间后重新启动"
    elif grep -Eqi 'Permission denied|Read-only file system' "$PIP_LOG"; then
      RECOVERY="安装目录不可写。请把完整项目移到当前用户可写的文件夹后重试"
    elif grep -Eqi 'No matching distribution|not a supported wheel|requires a different Python' "$PIP_LOG"; then
      RECOVERY="当前 Python 或处理器没有匹配的依赖包。请使用 Apple Silicon Mac 与 Python 3.11–3.13，并重新下载正式发布 ZIP"
    else
      RECOVERY="未能完成依赖安装。请检查网络、代理或 Python 软件源的可访问性后重试；重复启动会继续安装，不会清空研究数据"
    fi
    rm -f "$PIP_LOG"
    fail "$RECOVERY"
  fi
  rm -f "$PIP_LOG"
  print -r -- "$REQUIREMENTS_HASH" > "$REQUIREMENTS_STAMP"
fi

if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  command -v npm >/dev/null 2>&1 || \
    fail "前端尚未构建且未找到 Node.js。请执行 brew install node"
  echo "正在构建前端资源……"
  (
    cd "$ROOT/frontend"
    npm install --cache "$ROOT/frontend/.npm-cache"
    npm run build
  ) || fail "前端构建失败"
fi

echo "启动完成后会自动打开浏览器：$URL"
if [[ "$PORT" != "8765" ]]; then
  echo "自定义端口：请在同一端口配置下运行停止器，或在原启动窗口按 Control+C。"
fi
echo "停止服务：在本窗口按 Control+C，或随时双击 stop-macos.command。"
echo "只关闭浏览器页面不会停止服务。"
echo ""

cd "$ROOT"
export PYTHONPATH="$ROOT/backend"
export PYTHONUTF8=1
exec "$VENV/bin/python" -m app.main
