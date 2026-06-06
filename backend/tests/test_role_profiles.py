"""Tests for the role-profile system that drives the agent roster.

Covers _load_role_profile() and _build_agent_assignments() in app.routes.swarm,
which are the SAME data swarm.ps1 uses to build prompts. Verifies:
- the "default" profile reproduces the historical software-build roster
- the "data-research" profile yields the 5-role media-gathering team
- assignment merging/duplication matches expectations
"""

import json
import shutil
from pathlib import Path

import pytest

from app.routes.swarm import _load_role_profile, _build_agent_assignments

# Repo root holds the canonical .claude/role-profiles.json
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILES_SRC = _REPO_ROOT / ".claude" / "role-profiles.json"


@pytest.fixture
def project_folder(tmp_path):
    """A project folder scaffolded with the repo's role-profiles.json."""
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    shutil.copy2(_PROFILES_SRC, claude / "role-profiles.json")
    return tmp_path


def test_load_default_profile(project_folder):
    prof = _load_role_profile(project_folder, "default")
    assert prof is not None
    keys = [s["key"] for s in prof["slots"]]
    assert keys[:4] == ["backend", "frontend", "integration", "polish"]
    assert len(prof["slots"]) == 8


def test_load_data_research_profile(project_folder):
    prof = _load_role_profile(project_folder, "data-research")
    assert prof is not None
    keys = [s["key"] for s in prof["slots"]]
    assert keys == ["coordinator", "scout", "harvester", "curator", "validator"]
    # Every slot is part of the sequential signal chain
    assert all(s["signal"] for s in prof["slots"])


def test_missing_profile_returns_none(project_folder):
    assert _load_role_profile(project_folder, "nope") is None


def test_missing_file_returns_none(tmp_path):
    assert _load_role_profile(tmp_path, "default") is None


def test_default_assignments_match_historical_logic(project_folder):
    prof = _load_role_profile(project_folder, "default")

    def historical(count):
        rs = 8
        mp = {1: [[0, 1, 2, 3]], 2: [[0, 2], [1, 3]], 3: [[0], [1], [2, 3]]}
        if count <= 3:
            return mp[count]
        if count <= 8:
            return [[i] for i in range(min(count, rs))]
        a = [[i] for i in range(rs)]
        chain = [0, 1, 2, 0]
        for e in range(count - rs):
            a.append([chain[e % len(chain)]])
        return a

    for c in range(1, 17):
        assert _build_agent_assignments(prof, c) == historical(c), f"count={c}"


def test_data_research_five_agents_is_full_pipeline(project_folder):
    prof = _load_role_profile(project_folder, "data-research")
    assignments = _build_agent_assignments(prof, 5)
    assert assignments == [[0], [1], [2], [3], [4]]
    titles = [prof["slots"][a[0]]["title"] for a in assignments]
    assert titles == [
        "Research Coordinator", "Discovery / Ideation", "Acquisition / Harvester",
        "Curation / Filtering", "Review / Approval",
    ]


def test_data_research_extra_agents_duplicate_scout_and_harvester(project_folder):
    prof = _load_role_profile(project_folder, "data-research")
    # 7 agents = 5 roles + scout(1) + harvester(2) duplicated
    assignments = _build_agent_assignments(prof, 7)
    assert assignments == [[0], [1], [2], [3], [4], [1], [2]]


def test_data_research_three_agents_merges(project_folder):
    prof = _load_role_profile(project_folder, "data-research")
    assert _build_agent_assignments(prof, 3) == [[0, 1], [2, 3], [4]]
