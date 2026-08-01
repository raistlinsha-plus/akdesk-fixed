#!/usr/bin/env python3
"""Build and verify a clean, self-describing AKDesk Fixed release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

try:
    from .generate_release_metadata import generate_metadata
except ImportError:
    from generate_release_metadata import generate_metadata

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLES = {
    Path("start-macos.command"),
    Path("start-macos-demo.command"),
    Path("stop-macos.command"),
}
FORBIDDEN_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    ".npm-cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data",
    "backups",
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-wal",
    ".db-shm",
    ".pyc",
}
SECRET_PATTERNS = {
    "OpenAI-compatible key": re.compile(
        rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"
    ),
    "FRED environment key": re.compile(
        rb"(?:AKDESK_FRED_API_KEY|FRED_API_KEY)[\"'\s:=]+[0-9a-fA-F]{32}"
    ),
    "generic API key assignment": re.compile(
        rb"(?:api[_-]?key|token|secret)[\"'\s:=]+[\"']?[A-Za-z0-9_-]{24,}",
        re.IGNORECASE,
    ),
}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_version() -> str:
    source = (ROOT / "backend" / "app" / "__init__.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'__version__\s*=\s*"([^"]+)"', source)
    if not match:
        raise RuntimeError("无法读取 backend/app/__init__.py 版本")
    return match.group(1)


def verify_version_consistency(version: str) -> None:
    package = json.loads(
        (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    package_lock = json.loads(
        (ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    observed = {
        "backend": current_version(),
        "frontend/package.json": package.get("version"),
        "frontend/package-lock.json": package_lock.get("version"),
        "frontend lock root": package_lock.get("packages", {})
        .get("", {})
        .get("version"),
    }
    for launcher in EXECUTABLES - {Path("start-macos-demo.command")}:
        text = (ROOT / launcher).read_text(encoding="utf-8")
        match = re.search(r'EXPECTED_VERSION="([^"]+)"', text)
        observed[str(launcher)] = match.group(1) if match else None
    wrong = {key: value for key, value in observed.items() if value != version}
    if wrong:
        raise RuntimeError(f"版本不一致：预期 {version}，实际 {wrong}")
    app_source = (ROOT / "frontend" / "src" / "App.tsx").read_text(
        encoding="utf-8"
    )
    if f"V{version.upper()}" not in app_source:
        raise RuntimeError("前端版本标识没有同步")


def run_frontend_build() -> None:
    subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)


def documentation_files() -> set[Path]:
    files = {
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        *ROOT.joinpath("docs").rglob("*.md"),
    }
    queue = list(files)
    while queue:
        source = queue.pop()
        text = source.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target_text = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if (
                not target_text
                or target_text.startswith(("#", "http://", "https://", "mailto:"))
            ):
                continue
            target_text = unquote(target_text.split("#", 1)[0].split("?", 1)[0])
            target = (source.parent / target_text).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError as error:
                raise RuntimeError(f"{source}: 链接越出项目目录：{raw_target}") from error
            if not target.exists():
                raise RuntimeError(f"{source}: 本地链接不存在：{raw_target}")
            if target.is_file() and target not in files:
                files.add(target)
                if target.suffix.lower() == ".md":
                    queue.append(target)
    return files


def source_files() -> set[Path]:
    files = {
        ROOT / "LICENSE",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "SBOM.cdx.json",
        ROOT / "backend" / "requirements.txt",
        ROOT / "backend" / "requirements.lock",
        *(ROOT / item for item in EXECUTABLES),
        *(ROOT / "backend" / "app").rglob("*.py"),
        *(ROOT / "frontend" / "dist").rglob("*"),
        *documentation_files(),
    }
    return {path for path in files if path.is_file()}


def forbidden(path: Path) -> str | None:
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        return "禁止目录"
    name = path.name.lower()
    if name == ".ds_store":
        return "系统文件"
    if any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return "用户数据或缓存"
    return None


def copy_to_stage(stage: Path) -> None:
    for source in sorted(source_files()):
        relative = source.relative_to(ROOT)
        reason = forbidden(relative)
        if reason:
            raise RuntimeError(f"{relative}: {reason}")
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if relative in EXECUTABLES:
            destination.chmod(0o755)


def scan_secrets(root: Path) -> None:
    failures: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            continue
        content = path.read_bytes()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                failures.append(f"{path.relative_to(root)}: {label}")
    if failures:
        raise RuntimeError("发布包疑似包含凭据：" + "; ".join(failures))


def build_manifest(stage: Path, version: str) -> None:
    files = []
    for path in sorted(stage.rglob("*")):
        if path.is_file() and path.name != "RELEASE_MANIFEST.json":
            files.append(
                {
                    "path": path.relative_to(stage).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                    "executable": bool(path.stat().st_mode & stat.S_IXUSR),
                }
            )
    manifest = {
        "product": "AKDesk Fixed",
        "version": version,
        "built_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "file_count": len(files),
        "files": files,
    }
    (stage / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_tree(stage: Path, version: str) -> dict[str, object]:
    required = {
        Path("backend/app/main.py"),
        Path("backend/requirements.lock"),
        Path("frontend/dist/index.html"),
        Path("LICENSE"),
        Path("THIRD_PARTY_NOTICES.md"),
        Path("SBOM.cdx.json"),
        Path("README.md"),
        Path("RELEASE_MANIFEST.json"),
        *EXECUTABLES,
    }
    missing = sorted(str(path) for path in required if not (stage / path).is_file())
    if missing:
        raise RuntimeError(f"发布包缺少文件：{missing}")
    violations = [
        f"{path.relative_to(stage)}: {forbidden(path.relative_to(stage))}"
        for path in stage.rglob("*")
        if forbidden(path.relative_to(stage))
    ]
    if violations:
        raise RuntimeError("发布包包含禁止内容：" + "; ".join(violations))
    for executable in EXECUTABLES:
        if not os.access(stage / executable, os.X_OK):
            raise RuntimeError(f"{executable} 不可执行")
    scan_secrets(stage)
    manifest = json.loads(
        (stage / "RELEASE_MANIFEST.json").read_text(encoding="utf-8")
    )
    if manifest.get("version") != version:
        raise RuntimeError("发布清单版本不一致")
    for item in manifest.get("files", []):
        path = stage / str(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"发布清单校验失败：{item['path']}")
    sbom = json.loads((stage / "SBOM.cdx.json").read_text(encoding="utf-8"))
    if sbom.get("metadata", {}).get("component", {}).get("version") != version:
        raise RuntimeError("SBOM 版本不一致")
    return {
        "version": version,
        "file_count": manifest["file_count"],
        "uncompressed_bytes": sum(
            path.stat().st_size for path in stage.rglob("*") if path.is_file()
        ),
        "secrets": "none",
        "user_data": "none",
        "manifest": "ok",
    }


def zip_stage(stage: Path, archive: Path, top_level: str) -> None:
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as handle:
        for path in sorted(stage.rglob("*")):
            if not path.is_file():
                continue
            relative = Path(top_level) / path.relative_to(stage)
            info = zipfile.ZipInfo.from_file(path, arcname=relative.as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            if path.relative_to(stage) in EXECUTABLES:
                info.external_attr = (stat.S_IFREG | 0o755) << 16
            with path.open("rb") as source:
                handle.writestr(info, source.read(), compress_type=zipfile.ZIP_DEFLATED)


def verify_archive(archive: Path, version: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="akdesk-release-verify-") as directory:
        target = Path(directory)
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(target)
        roots = [path for path in target.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("发布包必须只有一个顶层目录")
        for executable in EXECUTABLES:
            (roots[0] / executable).chmod(0o755)
        return verify_tree(roots[0], version)


def write_checksums(output_dir: Path) -> None:
    archives = sorted(output_dir.glob("AKDesk-Fixed-v*.zip"))
    lines = [f"{sha256(path)}  {path.name}" for path in archives]
    (output_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_release(version: str, output_dir: Path, skip_build: bool) -> Path:
    verify_version_consistency(version)
    if not skip_build:
        run_frontend_build()
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise RuntimeError("前端生产资源不存在")
    generate_metadata(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    top_level = f"AKDesk-Fixed-v{version}"
    archive = output_dir / f"{top_level}.zip"
    with tempfile.TemporaryDirectory(prefix="akdesk-release-stage-") as directory:
        stage = Path(directory) / top_level
        stage.mkdir()
        copy_to_stage(stage)
        build_manifest(stage, version)
        verify_tree(stage, version)
        zip_stage(stage, archive, top_level)
    if archive.stat().st_size > 25 * 1024 * 1024:
        raise RuntimeError(
            f"压缩包 {archive.stat().st_size / 1024 / 1024:.1f} MB，超过 25 MB"
        )
    verify_archive(archive, version)
    write_checksums(output_dir)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=current_version())
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--verify-archive", type=Path)
    args = parser.parse_args()
    if args.verify_archive:
        report = verify_archive(args.verify_archive.resolve(), args.version)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    archive = build_release(
        args.version, args.output_dir.resolve(), args.skip_build
    )
    report = verify_archive(archive, args.version)
    report.update(
        {
            "archive": str(archive),
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": sha256(archive),
        }
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
