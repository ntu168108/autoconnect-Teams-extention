import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config as config_mod


def test_root_is_repo_root_when_not_frozen():
    root = config_mod.get_root()
    assert os.path.isfile(os.path.join(root, "requirements.txt"))


def test_root_is_exe_dir_when_frozen(monkeypatch, tmp_path):
    # config.json must sit next to the executable in a PyInstaller build: the
    # bundle's own directory is a temp one that is deleted on exit.
    # Build the path with the running OS's separator — a hardcoded Windows
    # path makes this fail on macOS/Linux for reasons that have nothing to do
    # with what is being tested.
    exe_dir = tmp_path / "apps" / "bot"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "TeamsAutoJoiner"))

    assert config_mod.get_root() == str(exe_dir)


def test_load_merges_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"email": "a@b.c", "blacklist": [{"team_name": "X"}]}),
        encoding="utf-8")
    cfg = config_mod.load()
    assert cfg["email"] == "a@b.c"
    assert cfg["meeting_mode"] == 3          # default filled in
    assert cfg["blacklist"] == [{"team_name": "X"}]  # untouched keys preserved


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    config_mod.save({"email": "x@y.z", "password": "s3cret"})
    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["email"] == "x@y.z"


def test_save_reports_a_readable_error_when_the_folder_is_not_writable(tmp_path, monkeypatch):
    # Otherwise the raw OSError surfaces as a stack trace in the terminal
    # while the browser just shows "connection reset" — see webui.py's
    # POST handler, which relies on this exception type to show something
    # the person filling in the form can actually act on.
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    tmp_path.chmod(0o555)
    try:
        with pytest.raises(config_mod.SaveError, match="Không ghi được"):
            config_mod.save({"email": "x@y.z"})
    finally:
        tmp_path.chmod(0o755)
