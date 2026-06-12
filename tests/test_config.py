import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config as config_mod


def test_root_is_repo_root_when_not_frozen():
    root = config_mod.get_root()
    assert os.path.isfile(os.path.join(root, "requirements.txt"))


def test_root_is_exe_dir_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\apps\bot\TeamsAutoJoiner.exe")
    assert config_mod.get_root() == os.path.abspath(r"C:\apps\bot")


def test_load_merges_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"email": "a@b.c", "blacklist": [{"team_name": "X"}]}),
        encoding="utf-8")
    cfg = config_mod.load()
    assert cfg["email"] == "a@b.c"
    assert cfg["meeting_mode"] == 1          # default filled in
    assert cfg["blacklist"] == [{"team_name": "X"}]  # untouched keys preserved


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    config_mod.save({"email": "x@y.z", "password": "s3cret"})
    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["email"] == "x@y.z"
