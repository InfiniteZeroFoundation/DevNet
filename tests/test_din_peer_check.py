"""Tests for the peer-rule check behind the din-* skills (.claude/scripts/).

The check is the only thing stopping a maintainer from approving, merging or
closing their own work, so a gap in who counts as "involved" is a policy hole.
GitHub is faked at the gh_json/gh_list boundary.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".claude" / "scripts" / "din_peer_check.py"


def _load():
    spec = spec_from_file_location("din_peer_check", SCRIPT)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


peer = _load()

ISSUE = 900
PR = 901


def _commit(sha, author, message):
    return {
        "sha": sha,
        "author": {"login": author},
        "committer": {"login": "web-flow"},
        "commit": {"author": {"name": author}, "message": message},
    }


COMMITS = [
    _commit(
        "a" * 40,
        "pr-owner",
        "fix: the thing\n\n"
        "Co-Authored-By: Helper <123+co-dev@users.noreply.github.com>\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n",
    ),
    _commit("b" * 40, "second-committer", "fix: follow-up"),
]


@pytest.fixture
def fake_github(monkeypatch):
    def gh_json(*args):
        endpoint = args[1]
        if endpoint.endswith(f"/issues/{ISSUE}"):
            return {"user": {"login": "issue-opener"}, "assignees": []}
        if endpoint.endswith(f"/pulls/{PR}"):
            return {"user": {"login": "pr-owner"}}
        raise AssertionError(f"unexpected gh_json {args}")

    def gh_list(endpoint):
        if endpoint.endswith(f"/issues/{ISSUE}/timeline"):
            return [
                {
                    "event": "cross-referenced",
                    "source": {
                        "issue": {
                            "number": PR,
                            "user": {"login": "pr-owner"},
                            "pull_request": {"merged_at": "2026-10-01T00:00:00Z"},
                        }
                    },
                },
                # An unmerged PR's people don't count as implementers.
                {
                    "event": "cross-referenced",
                    "source": {
                        "issue": {
                            "number": 902,
                            "user": {"login": "unmerged-author"},
                            "pull_request": {"merged_at": None},
                        }
                    },
                },
            ]
        if endpoint.endswith(f"/pulls/{PR}/commits"):
            return COMMITS
        raise AssertionError(f"unexpected gh_list {endpoint}")

    monkeypatch.setattr(peer, "gh_json", gh_json)
    monkeypatch.setattr(peer, "gh_list", gh_list)


def _as(monkeypatch, login):
    monkeypatch.setattr(peer, "me", lambda: login)


@pytest.mark.parametrize("login", ["pr-owner", "co-dev", "second-committer"])
def test_issue_close_refuses_everyone_on_a_merged_pr(fake_github, monkeypatch, capsys, login):
    _as(monkeypatch, login)
    assert peer.check_issue(ISSUE, closing=True) == 1
    assert "REFUSE" in capsys.readouterr().out


@pytest.mark.parametrize("login", ["bystander", "unmerged-author"])
def test_issue_close_allows_uninvolved(fake_github, monkeypatch, capsys, login):
    _as(monkeypatch, login)
    assert peer.check_issue(ISSUE, closing=True) == 0
    assert capsys.readouterr().out.startswith("OK")


def test_issue_close_names_the_merged_pr_in_the_reason(fake_github, monkeypatch, capsys):
    _as(monkeypatch, "co-dev")
    peer.check_issue(ISSUE, closing=True)
    assert f"of merged PR No. {PR}" in capsys.readouterr().out


def test_ai_trailer_is_not_a_person(fake_github):
    involved = peer.issue_people(ISSUE, closing=True)
    assert "Claude" not in involved
    assert "web-flow" not in involved


def test_pr_check_still_counts_co_authors(fake_github, monkeypatch):
    _as(monkeypatch, "co-dev")
    assert peer.check_pr(PR) == 1


def test_path_b_refuses_non_umer_admin(monkeypatch, capsys):
    _as(monkeypatch, "Santiagocetran")
    monkeypatch.setattr(peer, "gh", lambda *a: "admin\n")
    assert peer.check_path_b() == 1
    assert "REFUSE" in capsys.readouterr().out


@pytest.mark.parametrize("login", ["umeradl", "umermjd11"])
def test_path_b_allows_umer_with_admin_role(monkeypatch, login):
    _as(monkeypatch, login)
    monkeypatch.setattr(peer, "gh", lambda *a: "admin\n")
    assert peer.check_path_b() == 0


def test_path_b_still_needs_the_admin_role(monkeypatch):
    _as(monkeypatch, "umermjd11")
    monkeypatch.setattr(peer, "gh", lambda *a: "write\n")
    assert peer.check_path_b() == 1
