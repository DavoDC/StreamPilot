"""Tests for sabnzbd_client.py"""

import pytest
from unittest.mock import MagicMock, patch
from sabnzbd_client import SABnzbdClient


@pytest.fixture
def client():
    return SABnzbdClient("localhost", 8080, "myapikey")


@pytest.fixture(autouse=True)
def _sab_process_running():
    """Default: SABnzbd's process is present. Tests of the absent case override."""
    with patch("sabnzbd_client.psutil.process_iter",
               return_value=[MagicMock(info={"name": "SABnzbd.exe"})]):
        yield


@pytest.mark.parametrize("action", ["pause", "resume"])
def test_preflight_sab_not_running_warns_and_skips(client, caplog, action):
    import logging
    with patch("sabnzbd_client.psutil.process_iter", return_value=[]), \
         patch("sabnzbd_client.requests.get") as get:
        with caplog.at_level(logging.WARNING):
            getattr(client, action)()  # must not raise
    get.assert_not_called()
    assert "SABnzbd not running" in caplog.text


def test_preflight_skipped_for_remote_host():
    remote = SABnzbdClient("192.168.1.50", 8080, "k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": True}
    with patch("sabnzbd_client.psutil.process_iter", return_value=[]), \
         patch("sabnzbd_client.requests.get", return_value=mock_resp) as get:
        remote.pause()
    get.assert_called_once()


def test_process_running_matches_sabnzbd_names():
    fake = [MagicMock(info={"name": "SABnzbd.exe"})]
    with patch("sabnzbd_client.psutil.process_iter", return_value=fake):
        assert SABnzbdClient("localhost", 8080, "k")._process_running() is True
    fake = [MagicMock(info={"name": "notepad.exe"}), MagicMock(info={"name": None})]
    with patch("sabnzbd_client.psutil.process_iter", return_value=fake):
        assert SABnzbdClient("localhost", 8080, "k")._process_running() is False


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


def test_queue_state_makes_one_http_call(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"paused": False, "status": "Downloading"}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp) as get:
        assert client.queue_state() == (False, True)
    assert get.call_count == 1


def test_queue_state_unreachable(client):
    with patch("sabnzbd_client.requests.get", side_effect=Exception("refused")):
        assert client.queue_state() == (None, None)


def test_queue_state_missing_status_keeps_paused(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"queue": {"paused": True}}
    with patch("sabnzbd_client.requests.get", return_value=mock_resp):
        assert client.queue_state() == (True, None)


def test_request_error_log_redacts_apikey(caplog):
    """A request exception whose text carries the query-string key must not
    write the key to the log; the value is replaced, the rest kept."""
    import logging
    key_client = SABnzbdClient("localhost", 8080, "SECRET123")
    err = Exception("HTTPConnectionPool(host='localhost', port=8080): Max retries "
                    "exceeded with url: /api?apikey=SECRET123&output=json&mode=pause")
    with patch("sabnzbd_client.requests.get", side_effect=err):
        with caplog.at_level(logging.WARNING):
            assert key_client.pause() is None
    assert "SECRET123" not in caplog.text
    assert "apikey=***&output=json&mode=pause" in caplog.text
