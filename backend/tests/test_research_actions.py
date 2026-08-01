from __future__ import annotations

import sqlite3

import pytest

from app.database import Database
from app.models import ResearchProjectCreate
from app.research_actions import build_research_action_drafts


def test_action_drafts_require_explicit_accept_and_support_undo(tmp_path) -> None:
    database = Database(tmp_path / "actions.db")
    project = database.add_research_project(
        ResearchProjectCreate(title="利率方向研究", question="10Y 是否继续下行？")
    )

    proposals = build_research_action_drafts(database, project.id)
    drafts = database.replace_research_action_drafts(project.id, proposals)

    assert drafts
    assert all(item.status == "proposed" for item in drafts)
    assert database.get_research_project(project.id).entries == []  # type: ignore[union-attr]

    accepted = database.accept_research_action_drafts(project.id, [drafts[0].id])
    accepted_draft = next(item for item in accepted if item.id == drafts[0].id)
    assert accepted_draft.status == "accepted"
    assert accepted_draft.created_entry_id is not None
    assert len(database.get_research_project(project.id).entries) == 1  # type: ignore[union-attr]

    undone = database.undo_research_action_draft(project.id, drafts[0].id)
    assert undone is not None
    assert undone.status == "undone"
    assert database.get_research_project(project.id).entries == []  # type: ignore[union-attr]


def test_action_drafts_cannot_be_accepted_twice(tmp_path) -> None:
    database = Database(tmp_path / "actions.db")
    project = database.add_research_project(ResearchProjectCreate(title="信用跟踪"))
    draft = database.replace_research_action_drafts(
        project.id, build_research_action_drafts(database, project.id)
    )[0]
    database.accept_research_action_drafts(project.id, [draft.id])
    with pytest.raises(ValueError, match="仅可采纳"):
        database.accept_research_action_drafts(project.id, [draft.id])

    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

