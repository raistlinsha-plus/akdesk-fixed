from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import yaml

from app.credit import evaluate_credit_observation
from app.credit_import import parse_credit_file
from app.models import CreditObservationCreate


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "frontend/src/scenarios/creditFixture.json"


def test_casebook_fixed_credit_outcomes_match_real_backend_gates() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["sampleDate"] == "2026-08-03"
    assert len(fixture["items"]) == 3
    outcomes = []
    for item in fixture["items"]:
        observation = CreditObservationCreate(**item["observation"])
        result = evaluate_credit_observation(observation)
        assert result["eligible"] is item["expected"]["eligible"]
        assert result["spread_bp"] == item["expected"]["spreadBp"]
        assert "合成样例" in observation.source_note
        assert observation.bond_code.startswith("DEMO-")
        outcomes.append(result)
    assert "rating" in outcomes[1]["missing_fields"]
    assert "债券收益率与基准曲线不是同一观察日" in outcomes[2]["gate_reasons"]


def test_casebook_csv_is_importable_and_matches_the_browser_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = [item["observation"] for item in fixture["items"]]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    preview = parse_credit_file(stream.getvalue().encode("utf-8-sig"), "synthetic.csv")
    assert preview["valid_rows"] == 3
    assert preview["invalid_rows"] == 0
    assert [item.bond_code for item in preview["items"]] == [row["bond_code"] for row in rows]
    expected = [item["expected"]["eligible"] for item in fixture["items"]]
    assert [row["eligible"] for row in preview["preview_rows"]] == expected
    published = (ROOT / "examples/scenarios/credit-review-synthetic.csv").read_bytes()
    imported = parse_credit_file(published, "credit-review-synthetic.csv")
    assert [item.model_dump() for item in imported["items"]] == [item.model_dump() for item in preview["items"]]


def test_casebook_feedback_prefill_fields_match_the_github_template() -> None:
    template = yaml.safe_load(
        (ROOT / ".github/ISSUE_TEMPLATE/scenario_feedback.yml").read_text(encoding="utf-8")
    )
    fields = {field["id"]: field for field in template["body"]}
    # GitHub documents URL-prefilled custom text fields. Keep metadata in
    # text inputs rather than relying on undocumented dropdown preselection.
    for name in ("version", "scenario", "result", "reuse", "surface", "mode"):
        assert fields[name]["type"] == "input"
        assert "value" not in fields[name]["attributes"]
    assert fields["privacy"]["type"] == "checkboxes"
    assert fields["privacy"]["attributes"]["options"][0]["required"] is True
    assert "default" not in fields["privacy"]["attributes"]
