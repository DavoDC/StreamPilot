"""Tests for status_file.py - the daemon<->dashboard JSON contract."""

import json
import time

import status_file


def test_write_status_creates_valid_json(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(
        path,
        status="OK",
        game="Marvel Rivals",
        streaming=True,
        category="Marvel Rivals",
        sabnzbd="Paused",
        poll_interval=2,
    )
    data = json.loads(path.read_text())
    assert data["status"] == "OK"
    assert data["game"] == "Marvel Rivals"
    assert data["streaming"] is True
    assert data["sabnzbd"] == "Paused"
    assert data["poll_interval"] == 2
    assert isinstance(data["timestamp"], float)


def test_write_status_is_atomic_no_partial_file_left(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(path, status="OK", game=None, streaming=False, category=None, sabnzbd="Disabled", poll_interval=2)
    # no leftover .tmp file
    assert not (tmp_path / "status.json.tmp").exists()


def test_read_status_roundtrips(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(path, status="ISSUE", game="DBD", streaming=False, category="Dead by Daylight", sabnzbd="RUNNING - should be paused", poll_interval=2)
    data = status_file.read_status(path)
    assert data["status"] == "ISSUE"
    assert data["game"] == "DBD"


def test_read_status_missing_file_returns_none(tmp_path):
    assert status_file.read_status(tmp_path / "nope.json") is None


def test_read_status_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{not valid json")
    assert status_file.read_status(path) is None


def test_is_stale_fresh_status_is_not_stale():
    status = {"timestamp": time.time(), "poll_interval": 2}
    assert status_file.is_stale(status) is False


def test_is_stale_old_status_is_stale():
    status = {"timestamp": time.time() - 60, "poll_interval": 2}
    assert status_file.is_stale(status) is True


def test_is_stale_none_status_is_stale():
    assert status_file.is_stale(None) is True
