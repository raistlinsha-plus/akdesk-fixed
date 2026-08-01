#!/usr/bin/env python3
"""Generate a small CycloneDX SBOM and human-readable third-party notices."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_LOCK = ROOT / "backend" / "requirements.lock"
NPM_LOCK = ROOT / "frontend" / "package-lock.json"
SBOM_PATH = ROOT / "SBOM.cdx.json"
NOTICES_PATH = ROOT / "THIRD_PARTY_NOTICES.md"


def locked_python_components() -> list[dict[str, str]]:
    components: list[dict[str, str]] = []
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
    for line in PYTHON_LOCK.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        name, version = match.groups()
        components.append(
            {
                "type": "library",
                "ecosystem": "PyPI",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
                "license": python_license(name, version),
            }
        )
    return components


def python_license(name: str, expected_version: str) -> str:
    try:
        metadata = importlib.metadata.metadata(name)
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN"
    if importlib.metadata.version(name) != expected_version:
        return "UNKNOWN"
    expression = str(metadata.get("License-Expression") or "").strip()
    if expression:
        return expression
    license_value = str(metadata.get("License") or "").strip()
    if license_value and "\n" not in license_value and len(license_value) <= 80:
        return license_value
    classifiers = metadata.get_all("Classifier") or []
    licenses = [
        item.removeprefix("License :: ").replace(" :: ", " / ")
        for item in classifiers
        if item.startswith("License :: ")
    ]
    return ", ".join(licenses) if licenses else "UNKNOWN"


def locked_npm_components() -> list[dict[str, str]]:
    payload = json.loads(NPM_LOCK.read_text(encoding="utf-8"))
    found: dict[tuple[str, str], dict[str, str]] = {}
    for package_path, item in payload.get("packages", {}).items():
        if not package_path or "node_modules/" not in package_path:
            continue
        if item.get("dev") is True:
            continue
        name = package_path.rsplit("node_modules/", 1)[-1]
        version = str(item.get("version") or "")
        if not version:
            continue
        found[(name, version)] = {
            "type": "library",
            "ecosystem": "npm",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{name.replace('@', '%40')}@{version}",
            "license": str(item.get("license") or "UNKNOWN"),
        }
    return [found[key] for key in sorted(found, key=lambda value: value[0].lower())]


def generated_at() -> datetime:
    epoch = os.getenv("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    return datetime.now(timezone.utc)


def cyclonedx_component(item: dict[str, str]) -> dict[str, Any]:
    component: dict[str, Any] = {
        "type": item["type"],
        "bom-ref": item["purl"],
        "name": item["name"],
        "version": item["version"],
        "purl": item["purl"],
        "properties": [
            {"name": "akdesk:ecosystem", "value": item["ecosystem"]}
        ],
    }
    if item["license"] != "UNKNOWN":
        component["licenses"] = [{"license": {"name": item["license"]}}]
    return component


def generate_metadata(version: str) -> tuple[Path, Path]:
    components = locked_python_components() + locked_npm_components()
    lock_digest = hashlib.sha256(
        PYTHON_LOCK.read_bytes() + NPM_LOCK.read_bytes()
    ).hexdigest()
    timestamp = generated_at()
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL, f"https://akdesk.local/{version}/{lock_digest}"
    )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "component": {
                "type": "application",
                "bom-ref": f"pkg:generic/akdesk-fixed@{version}",
                "name": "AKDesk Fixed",
                "version": version,
                "licenses": [{"license": {"id": "MIT"}}],
            },
            "properties": [
                {"name": "akdesk:python-lock-sha256", "value": lock_digest}
            ],
        },
        "components": [cyclonedx_component(item) for item in components],
    }
    SBOM_PATH.write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = [
        "# AKDesk Fixed 第三方组件声明",
        "",
        f"> 对应版本：v{version}  ",
        f"> 生成时间：{timestamp.isoformat()}  ",
        "> 本文件用于帮助识别随产品交付或构建的第三方组件；实际授权以各组件许可证原文为准。",
        "",
        "AKDesk Fixed 自身采用 MIT License。运行时依赖及前端生产依赖如下，"
        "机器可读清单见 `SBOM.cdx.json`。",
        "",
        "| 生态 | 组件 | 版本 | 声明许可证 |",
        "| --- | --- | --- | --- |",
    ]
    for item in components:
        license_name = item["license"].replace("|", "\\|").replace("\n", " ")
        rows.append(
            f"| {item['ecosystem']} | `{item['name']}` | "
            f"`{item['version']}` | {license_name} |"
        )
    rows.extend(
        [
            "",
            "## 数据和外部服务",
            "",
            "本声明不授予第三方数据的再分发权。AKShare / AKTools 访问的公开页面、"
            "FRED、World Bank、GDELT、AIHubMix 以及用户自行配置的数据或模型服务，"
            "分别受其自身条款约束。",
            "",
            "## 无担保声明",
            "",
            "第三方组件按其许可证提供。AKDesk Fixed 的 MIT License 不改变第三方"
            "组件的许可证，也不对外部接口的持续可用性作出承诺。",
            "",
        ]
    )
    NOTICES_PATH.write_text("\n".join(rows), encoding="utf-8")
    return SBOM_PATH, NOTICES_PATH


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    sbom, notices = generate_metadata(args.version)
    print(f"generated {sbom.relative_to(ROOT)}")
    print(f"generated {notices.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
