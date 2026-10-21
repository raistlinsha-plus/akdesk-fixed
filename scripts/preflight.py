#!/usr/bin/env python3
"""Offline, standard-library-only checks before installing or starting AKDesk."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import sys
from pathlib import Path


def _writable_parent(path: Path) -> Path:
    parent = path
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent


def inspect_environment(root: Path) -> dict[str, object]:
    checks: list[dict[str, str]] = []

    def add(code: str, status: str, message: str, recovery: str = "") -> None:
        checks.append(
            {"code": code, "status": status, "message": message, "recovery": recovery}
        )

    if (3, 11) <= sys.version_info < (3, 14):
        add("python", "ok", "Python 版本受支持")
    else:
        add(
            "python",
            "error",
            "需要 Python 3.11–3.13",
            "安装 Python 3.13，或用 AKDESK_PYTHON 指定该版本的解释器后重试。",
        )
    if (root / "backend/requirements.lock").is_file():
        add("release_files", "ok", "已找到锁定依赖清单")
    else:
        add(
            "release_files",
            "error",
            "缺少锁定依赖清单",
            "从 GitHub Releases 重新下载完整 ZIP 并解压，不要只复制启动脚本。",
        )
    parent = _writable_parent(root)
    if os.access(parent, os.W_OK | os.X_OK):
        add("project_writable", "ok", "项目目录可写")
    else:
        add(
            "project_writable",
            "error",
            "项目目录不可写",
            "将完整项目移动到当前用户可写的文件夹，勿直接在压缩包或只读磁盘中启动。",
        )
    configured = os.getenv("AKDESK_DATA_DIR")
    legacy = root / "data"
    if configured:
        data_dir = Path(configured).expanduser()
        # The launcher starts the backend from root; use the same anchor even
        # when Finder or another terminal invoked this preflight elsewhere.
        if not data_dir.is_absolute():
            data_dir = root / data_dir
    elif any(
        (legacy / name).exists()
        for name in ("akdesk-fixed.db", "market-cache.db", "backups")
    ):
        data_dir = legacy
    elif sys.platform == "darwin":
        data_dir = Path.home() / "Library/Application Support/AKDesk Fixed"
    else:
        data_dir = Path.home() / ".local/share/akdesk-fixed"
    data_parent = _writable_parent(data_dir)
    if data_parent.is_dir() and os.access(data_parent, os.W_OK | os.X_OK):
        add("data_writable", "ok", "数据目录可写")
    else:
        add(
            "data_writable",
            "error",
            "数据目录不可写",
            "检查 AKDESK_DATA_DIR 是否指向可写文件夹；不要删除已有数据库来尝试修复。",
        )
    try:
        free = shutil.disk_usage(parent).free
        add(
            "disk_space",
            "ok" if free >= 1024**3 else "warning",
            "可用空间充足" if free >= 1024**3 else "可用空间不足 1 GB",
            "首次安装建议至少保留 1 GB 空间。" if free < 1024**3 else "",
        )
    except OSError:
        add(
            "disk_space",
            "warning",
            "无法检查可用磁盘空间",
            "请手动确认至少有 1 GB 可用空间。",
        )
    defaults = ssl.get_default_verify_paths()
    if defaults.cafile or defaults.capath:
        add("certificates", "ok", "已找到系统证书位置（未发起网络请求）")
    else:
        add(
            "certificates",
            "warning",
            "未找到默认 TLS 证书位置",
            "若安装提示 CERTIFICATE_VERIFY_FAILED，请运行 Python 安装目录中的 Install Certificates.command 后重试；不要关闭证书校验。",
        )
    if (root / "frontend/dist/index.html").is_file():
        add("frontend", "ok", "已找到预构建界面")
    else:
        add(
            "frontend",
            "warning",
            "缺少预构建界面",
            "普通用户请重新下载正式发布 ZIP；开发者可安装 Node.js 后构建。",
        )
    return {
        "schema_version": 1,
        "ok": not any(item["status"] == "error" for item in checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--json", action="store_true", help="输出不含个人路径的 JSON")
    args = parser.parse_args()
    report = inspect_environment(args.root.resolve())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("启动预检（仅本地检查，不连接数据源）")
        for item in report["checks"]:
            symbol = {"ok": "✓", "warning": "!", "error": "×"}[item["status"]]
            print(f"  {symbol} {item['message']}")
            if item["recovery"]:
                print(f"    {item['recovery']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
