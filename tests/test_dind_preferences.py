import json

from typer.testing import CliRunner

from dincli.dind.main import app
from dincli.dind.paths import StateDirs
from dincli.dind.preferences import (
    Preferences,
    load_preferences,
    save_preferences,
)


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "prefs.json"
    prefs = Preferences(
        domain="defi",
        risk_tolerance="conservative",
        min_expected_reward=100,
        privacy_constraints=["no_gpu"],
    )
    save_preferences(path, prefs)

    loaded = load_preferences(path)
    assert loaded.domain == "defi"
    assert loaded.risk_tolerance == "conservative"
    assert loaded.min_expected_reward == 100
    assert loaded.privacy_constraints == ["no_gpu"]


def test_load_returns_defaults_for_missing_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    result = load_preferences(path)
    assert result.domain is None
    assert result.risk_tolerance == "moderate"
    assert result.min_expected_reward is None
    assert result.privacy_constraints == []


def test_load_returns_defaults_for_empty_file(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("")
    result = load_preferences(path)
    assert result.domain is None
    assert result.risk_tolerance == "moderate"


def test_load_returns_defaults_for_whitespace_file(tmp_path):
    path = tmp_path / "whitespace.json"
    path.write_text("   \n  \n  ")
    result = load_preferences(path)
    assert result.domain is None
    assert result.risk_tolerance == "moderate"


def test_preferences_show_defaults(monkeypatch, tmp_path):
    state_dir = str(tmp_path)
    monkeypatch.setattr(
        "dincli.dind.main.resolve_state_dir", lambda flag=None: tmp_path
    )
    runner = CliRunner()
    result = runner.invoke(app, ["preferences", "show", "--state-dir", state_dir])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["domain"] is None
    assert data["risk_tolerance"] == "moderate"
    assert data["min_expected_reward"] is None
    assert data["privacy_constraints"] == []


def test_preferences_set_partial(monkeypatch, tmp_path):
    state_dir = str(tmp_path)
    monkeypatch.setattr(
        "dincli.dind.main.resolve_state_dir", lambda flag=None: tmp_path
    )
    paths = StateDirs(tmp_path)

    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "preferences", "set",
            "--state-dir", state_dir,
            "--domain", "defi",
            "--risk-tolerance", "aggressive",
            "--min-reward", "500",
        ],
    )
    assert result.exit_code == 0, result.output

    prefs = load_preferences(paths.preferences_path)
    assert prefs.domain == "defi"
    assert prefs.risk_tolerance == "aggressive"
    assert prefs.min_expected_reward == 500
    assert prefs.privacy_constraints == []

    result = runner.invoke(
        app,
        [
            "preferences", "set",
            "--state-dir", state_dir,
            "--min-reward", "999",
        ],
    )
    assert result.exit_code == 0, result.output

    prefs = load_preferences(paths.preferences_path)
    assert prefs.domain == "defi"
    assert prefs.risk_tolerance == "aggressive"
    assert prefs.min_expected_reward == 999
    assert prefs.privacy_constraints == []


def test_preferences_set_privacy(monkeypatch, tmp_path):
    state_dir = str(tmp_path)
    monkeypatch.setattr(
        "dincli.dind.main.resolve_state_dir", lambda flag=None: tmp_path
    )
    paths = StateDirs(tmp_path)

    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "preferences", "set",
            "--state-dir", state_dir,
            "--privacy", "no_gpu",
            "--privacy", "eu_only",
        ],
    )
    assert result.exit_code == 0, result.output

    prefs = load_preferences(paths.preferences_path)
    assert prefs.privacy_constraints == ["no_gpu", "eu_only"]

    result = runner.invoke(
        app,
        [
            "preferences", "set",
            "--state-dir", state_dir,
            "--domain", "medical",
        ],
    )
    assert result.exit_code == 0, result.output

    prefs = load_preferences(paths.preferences_path)
    assert prefs.privacy_constraints == ["no_gpu", "eu_only"]
    assert prefs.domain == "medical"


def test_preferences_set_invalid_risk_tolerance(monkeypatch, tmp_path):
    state_dir = str(tmp_path)
    monkeypatch.setattr(
        "dincli.dind.main.resolve_state_dir", lambda flag=None: tmp_path
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "preferences", "set",
            "--state-dir", state_dir,
            "--risk-tolerance", "reckless",
        ],
    )
    assert result.exit_code != 0, result.output
