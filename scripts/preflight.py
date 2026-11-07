#!/usr/bin/env python3
"""Offline, standard-library-only checks before installing or starting AKDesk."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.paths import default_data_dir  # noqa: E402


class FrontendEntry(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.modules: list[str] = []
        self.resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("type") == "module" and values.get("src"):
            self.modules.append(values["src"] or "")
        if tag == "link" and values.get("rel") in {"stylesheet", "modulepreload"}:
            if href := values.get("href"):
                self.resources.append(href)


def frontend_ready(index: Path) -> bool:
    """Validate the locally referenced Vite entry resources without requests."""
    try:
        parser = FrontendEntry()
        parser.feed(index.read_text(encoding="utf-8"))
        parser.close()
        assets = (index.parent / "assets").resolve()
        if not parser.modules or not assets.is_relative_to(index.parent.resolve()):
            return False
        for resource in [*parser.modules, *parser.resources]:
            url = urlsplit(resource)
            if url.scheme or url.netloc or resource.startswith("//"):
                return False
            target = (index.parent / unquote(url.path).lstrip("/")).resolve()
            if not target.is_relative_to(assets) or not target.is_file():
                return False
        return True
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return False


def _writable_parent(path: Path) -> Path:
    parent = path
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent


def packaged_install(root: Path) -> bool:
    return (root / "RELEASE_MANIFEST.json").exists() or (
        (root / "scripts/launcher.py").is_file() and not (root / "frontend/package.json").is_file()
    )


def frontend_bundle_ready(root: Path) -> bool:
    dist = root / "frontend/dist"
    release_manifest = root / "RELEASE_MANIFEST.json"
    vite_manifest = dist / ".vite/manifest.json"
    try:
        if not frontend_ready(dist / "index.html"):
            return False
        packaged = packaged_install(root)
        if vite_manifest.exists() or packaged:
            chunks = json.loads(vite_manifest.read_text(encoding="utf-8"))
            if not any(chunk.get("isEntry") for chunk in chunks.values()):
                return False
            for chunk in chunks.values():
                for resource in [chunk["file"], *chunk.get("css", []), *chunk.get("assets", [])]:
                    path = (dist / resource).resolve()
                    if not path.is_relative_to(dist.resolve()) or not path.is_file():
                        return False
                if any(key not in chunks for key in [*chunk.get("imports", []), *chunk.get("dynamicImports", [])]):
                    return False
        if packaged:
            manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
            files = [item for item in manifest["files"] if item["path"].startswith("frontend/dist/")]
            expected = {item["path"] for item in files}
            if expected != {p.relative_to(root).as_posix() for p in dist.rglob("*") if p.is_file()}:
                return False
            if len(expected) != len(files):
                return False
            for item in files:
                path = root / item["path"]
                if not path.resolve().is_relative_to(dist.resolve()) or path.stat().st_size != item["size"]:
                    return False
                with path.open("rb") as fp:
                    if hashlib.file_digest(fp, "sha256").hexdigest() != item["sha256"]:
                        return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return False


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
    data_dir = default_data_dir(root)
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
    index = root / "frontend/dist/index.html"
    if index.is_file():
        if frontend_bundle_ready(root):
            add("frontend", "ok", "预构建界面资源校验通过")
        else:
            add(
                "frontend",
                "error",
                "预构建界面损坏或缺少引用资源（含按需页面）",
                "正式 ZIP 请完整重新解压到新文件夹；源码用户请重新构建 frontend。无需删除研究数据。",
            )
    else:
        add(
            "frontend",
            "error" if packaged_install(root) else "warning",
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
