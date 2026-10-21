#!/usr/bin/env python3
"""A reproducible, key-free example: three data sources to one Markdown brief."""

from __future__ import annotations

import argparse
import copy
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable


SOURCES = (
    (
        "money_rates",
        "资金面",
        "money_rates",
        "AKShare / Shibor",
        "https://akshare.akfamily.xyz/data/interest_rate/interest_rate.html",
    ),
    (
        "yield_curves",
        "国债曲线",
        "yield_curves",
        "AKShare / ChinaBond",
        "https://akshare.akfamily.xyz/data/bond/bond.html",
    ),
    (
        "treasury_futures",
        "国债期货",
        "treasury_futures",
        "AKShare / Sina Futures",
        "https://akshare.akfamily.xyz/data/futures/futures.html",
    ),
)
FIXTURE_TIME = "2026-07-27T16:00:00+08:00"
_FIXTURE_DATA = {
    "money_rates": [
        {"name": "Shibor O/N", "value": 1.41, "change_bp": -1.2},
        {"name": "Shibor 1W", "value": 1.58, "change_bp": None},
    ],
    "yield_curves": {
        "tenors": ["1Y", "5Y", "10Y", "30Y"],
        "series": [{"name": "中债国债·最新", "values": [1.40, 1.65, 1.81, 2.03]}],
        "changes": [-0.5, None, -1.0, 0.0],
    },
    "treasury_futures": [
        {"product": "T", "contract": "T合成示例", "price": 108.125, "change_pct": 0.12},
        {"product": "TL", "contract": "TL合成示例", "price": None, "change_pct": None},
    ],
}


def synthetic_brief() -> dict[str, Any]:
    """All numbers and timestamps are fixed, hand-authored demonstration data."""
    return {
        "schema_version": 1,
        "mode": "synthetic",
        "generated_at": FIXTURE_TIME,
        "sources": [
            {
                "adapter": adapter,
                "label": label,
                "status": "synthetic",
                "source": "手工合成示例（未调用 AKShare）",
                "source_url": url,
                "observation_time": "2026-07-27（合成示例日期）",
                "fetched_at": f"{FIXTURE_TIME}（固定示例时点，未实际抓取）",
                "error_category": "none",
                "data": copy.deepcopy(_FIXTURE_DATA[adapter]),
            }
            for adapter, label, _method, _source, url in SOURCES
        ],
    }


def _error_category(message: str) -> str:
    text = message.lower()
    for category, markers in (
        ("timeout", ("timeout", "timed out", "超时", "超过")),
        ("certificate", ("certificate", "ssl", "证书")),
        ("rate_limit", ("429", "rate limit", "限流")),
        ("network", ("network", "connection", "网络", "连接")),
    ):
        if any(marker in text for marker in markers):
            return category
    return "upstream_unavailable"


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        return datetime.fromisoformat(text).isoformat()
    except (TypeError, ValueError):
        return None


def _create_live_service():
    # The default example stays standard-library-only, including under -S.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.provider import DataService

    return DataService(cache_path=None, on_dataset=None)


def live_brief(
    timeout: float, service_factory: Callable | None = None
) -> dict[str, Any]:
    """Sequential isolated workers; memory cache only, no app.main or database."""
    service = (service_factory or _create_live_service)()
    service.demo_only = False
    service.is_source_worker = False
    service.retry_attempts = 1
    service.timeout_seconds = timeout
    service.queue_timeout_seconds = timeout
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "live",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [],
    }
    for adapter, label, method, source, url in SOURCES:
        entry: dict[str, Any] = {
            "adapter": adapter,
            "label": label,
            "source": source,
            "source_url": url,
            "status": "unavailable",
            "data": None,
            "observation_time": None,
            "fetched_at": None,
            "error_category": "upstream_unavailable",
        }
        try:
            dataset = getattr(service, method)(force=True)
            meta = dataset.meta
            # DataService can fall back to internal demo rows after a failure.
            # Discard those rows rather than mix them into the live result.
            if (
                meta.demo
                or meta.stale
                or meta.trust_level in {"suspicious", "unavailable"}
            ):
                health = service.health.get(adapter)
                entry["error_category"] = _error_category(
                    getattr(health, "message", "") or ""
                )
            else:
                entry.update(
                    {
                        "status": "partial"
                        if meta.trust_level == "partial"
                        else "available",
                        "data": dataset.data,
                        "observation_time": _timestamp(meta.observation_time),
                        "fetched_at": _timestamp(meta.fetched_at),
                        "error_category": "none",
                    }
                )
        except Exception as exc:
            # Raw upstream errors may contain URLs, local paths or proxy details.
            entry["error_category"] = _error_category(f"{type(exc).__name__}: {exc}")
        result["sources"].append(entry)
    return result


def _number(value: Any) -> float | None:
    try:
        number = (
            float(value) if value is not None and not isinstance(value, bool) else None
        )
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None


def _format(value: Any, places: int = 2, signed: bool = False) -> str:
    number = _number(value)
    if number is None:
        return "—（缺失）"
    return format(number, f"+.{places}f" if signed else f".{places}f")


def _cell(value: Any) -> str:
    return (
        str(value if value is not None else "未提供")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def render_markdown(brief: dict[str, Any]) -> str:
    synthetic = brief["mode"] == "synthetic"
    title = (
        "固定合成示例 · 非真实市场"
        if synthetic
        else "本次公开数据请求 · 请核验来源时点"
    )
    lines = [
        "# AKDesk 一页固收简报",
        "",
        f"> {title}",
        "",
        f"生成/示例时点：{brief['generated_at']}",
        "",
    ]
    sources = {item["adapter"]: item for item in brief["sources"]}
    lines += [
        "## 资金面",
        "",
        "| 指标 | 利率（%） | 较前值变化（BP） |",
        "| --- | ---: | ---: |",
    ]
    funding = sources["money_rates"]["data"] or []
    for item in funding:
        lines.append(
            f"| {_cell(item.get('name'))} | {_format(item.get('value'), 3)} | {_format(item.get('change_bp'), signed=True)} |"
        )
    if not funding:
        lines.append("| 本次数据不可用 | —（缺失） | —（缺失） |")
    lines += [
        "",
        "## 国债曲线",
        "",
        "| 期限 | 收益率（%） | 较前值变化（BP） |",
        "| --- | ---: | ---: |",
    ]
    curve = sources["yield_curves"]["data"] or {}
    tenors = curve.get("tenors", [])
    latest = next(
        (
            item
            for item in curve.get("series", [])
            if "国债" in item.get("name", "") and "最新" in item.get("name", "")
        ),
        {},
    )
    values, changes = latest.get("values", []), curve.get("changes", [])
    for tenor in ("1Y", "5Y", "10Y", "30Y"):
        index = tenors.index(tenor) if tenor in tenors else -1
        value = values[index] if 0 <= index < len(values) else None
        change = changes[index] if 0 <= index < len(changes) else None
        lines.append(
            f"| {tenor} | {_format(value, 3)} | {_format(change, signed=True)} |"
        )
    lines += [
        "",
        "## 国债期货",
        "",
        "| 产品 / 合约 | 价格 | 涨跌幅（%） |",
        "| --- | ---: | ---: |",
    ]
    futures = sources["treasury_futures"]["data"] or []
    for item in futures[:4]:
        lines.append(
            f"| {_cell(item.get('product'))} / {_cell(item.get('contract'))} | {_format(item.get('price'), 3)} | {_format(item.get('change_pct'), signed=True)} |"
        )
    if not futures:
        lines.append("| 本次数据不可用 | —（缺失） | —（缺失） |")
    lines += [
        "",
        "## 来源与时点",
        "",
        "| 模块 / 出处 | 状态 | 观测时点 | 抓取时点 |",
        "| --- | --- | --- | --- |",
    ]
    labels = {
        "synthetic": "合成示例",
        "available": "已取得真实数据",
        "partial": "真实数据部分可用",
        "unavailable": "不可用",
    }
    for item in brief["sources"]:
        status = labels[item["status"]]
        if item["status"] == "unavailable":
            status += f"（{item['error_category']}）"
        lines.append(
            f"| {_cell(item['label'])} · [{_cell(item['source'])}]({item['source_url']}) | {status} | {_cell(item['observation_time'])} | {_cell(item['fetched_at'])} |"
        )
    lines += [
        "",
        "## 人工核验",
        "",
        "- 核对各源观测日期；同一份简报不代表数据具有同一时点。",
        "- 缺失值保留为空；BP 为利率变化单位，期货涨跌幅为百分比。",
        "- 未加入用户研究内容，也不自动形成投资结论。",
        "",
        "AKShare 是公开数据访问层。仅供个人学习与研究；数据时效、可用性及使用条件以原始来源为准。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="按需请求公开 AKShare 数据；不使用合成值补位",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15,
        help="真实模式每源隔离进程超时秒数（1–60，默认15）",
    )
    parser.add_argument(
        "--output", type=Path, help="写入 Markdown 文件；未指定则输出到终端"
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 60:
        parser.error("--timeout 必须为 1–60 秒")
    try:
        brief = live_brief(args.timeout) if args.live else synthetic_brief()
    except ImportError:
        print(
            "真实模式需要项目后端依赖。请先按 examples/README.md 安装，再使用 .venv/bin/python 运行。",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "真实模式初始化失败，请检查已安装依赖和 AKDESK_SOURCE_* 环境变量；未输出原始错误或个人路径。",
            file=sys.stderr,
        )
        return 1
    markdown = render_markdown(brief)
    if args.output:
        try:
            args.output.write_text(markdown, encoding="utf-8")
        except OSError:
            print(
                "无法写入输出文件，请检查父目录是否存在及其写入权限。", file=sys.stderr
            )
            return 1
        print(f"已写入 Markdown：{args.output.name}")
    else:
        print(markdown, end="")
    return (
        2
        if args.live
        and all(item["status"] == "unavailable" for item in brief["sources"])
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
