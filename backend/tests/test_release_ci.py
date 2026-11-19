from copy import deepcopy

import pytest

from scripts import check_release_ci


COMMIT = "a" * 40


def passing():
    run = {
        "head_sha": COMMIT, "event": "push", "head_branch": "main",
        "path": ".github/workflows/ci.yml", "status": "completed",
        "conclusion": "success", "id": 42, "run_attempt": 2, "run_number": 7,
    }
    jobs = [{"name": name, "status": "completed", "conclusion": "success"}
            for name in sorted(check_release_ci.REQUIRED_JOBS)]
    return run, jobs


def test_release_requires_all_four_successful_jobs():
    run, jobs = passing()
    check_release_ci.verify_run(COMMIT, run, jobs)


@pytest.mark.parametrize("field,value", [
    ("head_sha", "b" * 40), ("event", "pull_request"), ("head_branch", "other"),
    ("path", ".github/workflows/pages.yml"), ("status", "in_progress"),
    ("conclusion", "failure"), ("conclusion", "cancelled"),
])
def test_release_rejects_wrong_or_unfinished_runs(field, value):
    run, jobs = passing()
    run[field] = value
    with pytest.raises(RuntimeError):
        check_release_ci.verify_run(COMMIT, run, jobs)


@pytest.mark.parametrize("change", ["missing", "cancelled", "skipped", "duplicate"])
def test_release_rejects_incomplete_or_ambiguous_job_sets(change):
    run, jobs = passing()
    if change == "missing":
        jobs.pop()
    elif change == "duplicate":
        jobs.append(deepcopy(jobs[0]))
    else:
        jobs[0]["conclusion"] = change
    with pytest.raises(RuntimeError):
        check_release_ci.verify_run(COMMIT, run, jobs)


def test_release_does_not_fall_back_to_older_green_run(monkeypatch):
    run, jobs = passing()
    newer = run | {"id": 43, "run_number": 8, "conclusion": "failure"}
    endpoints = []

    def fake_api(endpoint):
        endpoints.append(endpoint)
        if "/commits/" in endpoint:
            return {"sha": COMMIT}
        if "/workflows/" in endpoint:
            return {"workflow_runs": [run, newer]}
        return {"jobs": jobs, "total_count": len(jobs)}

    monkeypatch.setattr(check_release_ci, "api", fake_api)
    with pytest.raises(RuntimeError, match="尚未完整通过"):
        check_release_ci.check("v1.4.2")
    assert any("/runs/43/attempts/2/jobs" in endpoint for endpoint in endpoints)


def test_release_uses_remote_tag_and_exact_attempt(monkeypatch):
    run, jobs = passing()
    endpoints = []

    def fake_api(endpoint):
        endpoints.append(endpoint)
        if "/commits/" in endpoint:
            return {"sha": COMMIT}
        if "/workflows/" in endpoint:
            return {"workflow_runs": [run]}
        return {"jobs": jobs, "total_count": len(jobs)}

    monkeypatch.setattr(check_release_ci, "api", fake_api)
    assert check_release_ci.check("v1.4.2")["commit"] == COMMIT
    assert any("/runs/42/attempts/2/jobs" in endpoint for endpoint in endpoints)
