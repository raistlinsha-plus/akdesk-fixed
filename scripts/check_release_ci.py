#!/usr/bin/env python3
"""Read-only, fail-closed check of the exact release tag's GitHub CI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess

REPOSITORY = "raistlinsha-plus/akdesk-fixed"
REQUIRED_JOBS = frozenset({
    "Backend / Python 3.11",
    "Backend / Python 3.12",
    "Backend / Python 3.13",
    "Frontend / Node.js 22",
})


def api(endpoint: str) -> dict:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint], capture_output=True, text=True,
            check=True, timeout=40,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise RuntimeError("无法读取 GitHub 检查结果；不应据此公开 Release。") from error
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub 返回格式异常。")
    return payload


def verify_run(commit: str, run: dict, jobs: list[dict]) -> None:
    if run.get("head_sha") != commit:
        raise RuntimeError("CI 不属于待发布标签指向的提交。")
    if (run.get("event") != "push" or run.get("head_branch") != "main"
            or run.get("path") != ".github/workflows/ci.yml"):
        raise RuntimeError("不是 main 推送触发的正式 CI。")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise RuntimeError("CI 尚未完整通过；等待、失败、取消和跳过都不能视为成功。")
    names = [job.get("name") for job in jobs]
    if not REQUIRED_JOBS.issubset(names) or len(names) != len(set(names)):
        raise RuntimeError("CI 缺少要求的 Python／Node.js 检查，或任务名重复。")
    if any(job.get("status") != "completed" or job.get("conclusion") != "success" for job in jobs):
        raise RuntimeError("CI 存在未成功的任务。")


def check(tag: str) -> dict:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", tag):
        raise RuntimeError("请指定完整版本标签，例如 v1.4.2。")
    commit = api(f"repos/{REPOSITORY}/commits/{tag}").get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("无法确认标签提交。")
    payload = api(
        f"repos/{REPOSITORY}/actions/workflows/ci.yml/runs"
        f"?head_sha={commit}&event=push&branch=main&per_page=100"
    )
    runs = payload.get("workflow_runs", [])
    if not runs:
        raise RuntimeError("没有该标签提交的 main 推送 CI。")
    # Never select an older successful run to conceal a more recent failure.
    run = max(runs, key=lambda item: (item.get("run_number", 0), item.get("id", 0)))
    run_id = run.get("id")
    if not isinstance(run_id, int):
        raise RuntimeError("CI 运行标识异常。")
    attempt = run.get("run_attempt")
    if not isinstance(attempt, int) or attempt < 1:
        raise RuntimeError("CI 重试标识异常。")
    jobs = api(
        f"repos/{REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"
    )
    if jobs.get("total_count") != len(jobs.get("jobs", [])):
        raise RuntimeError("未取得完整任务列表。")
    verify_run(commit, run, jobs.get("jobs", []))
    return {"tag": tag, "commit": commit, "run_id": run_id, "attempt": attempt,
            "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.tag), ensure_ascii=False, indent=2))
    except RuntimeError as error:
        print(f"发布检查未通过：{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
