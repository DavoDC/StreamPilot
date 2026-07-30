"""Tests for sabnzbd_client.py"""

import pytest
from unittest.mock import MagicMock, patch
from sabnzbd_client import SABnzbdClient


@pytest.fixture
def client():
    return SABnzbdClient("localhost", 8080, "myapikey")


def test_pause_success(client, capsys):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": True}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        client.pause()  # Should not raise


def test_pause_failure_warns(client, caplog):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": False}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        import logging
        with caplog.at_level(logging.WARNING):
            client.pause()
    assert "pause manually" in caplog.text


def test_resume_success(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": True}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        client.resume()  # Should not raise


def test_is_paused_true(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"paused": True}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_paused() is True


def test_is_paused_false(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"paused": False}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_paused() is False


def test_is_paused_unreachable(client):
    with patch("sabnzbd_client.requests.get", side_effect=Exception("connection refused")):
        assert client.is_paused() is None


def test_is_downloading_true(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"status": "Downloading"}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_downloading() is True


@pytest.mark.parametrize("status", ["Propagating", "Fetching", "Checking", "Queued"])
def test_is_downloading_true_for_other_busy_statuses(client, status):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"status": status}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_downloading() is True


def test_is_downloading_false_when_idle(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"status": "Idle"}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_downloading() is False


def test_is_downloading_false_when_paused(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"status": "Paused"}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_downloading() is False


def test_is_downloading_unreachable(client):
    with patch("sabnzbd_client.requests.get", side_effect=Exception("connection refused")):
        assert client.is_downloading() is None


def test_is_downloading_missing_status_field(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.is_downloading() is None
