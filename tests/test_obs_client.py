"""Tests for obs_client.py"""

import pytest
from unittest.mock import MagicMock, patch
from obs_client import OBSClient


@pytest.fixture
def client():
    return OBSClient("localhost", 4455, "password", "Game Capture")


def test_connect_success(client):
    mock_req = MagicMock()
    with patch("obs_client.obs") as mock_obs:
        mock_obs.ReqClient.return_value = mock_req
        assert client.connect() is True
        assert client._client is mock_req


def test_connect_failure(client):
    with patch("obs_client.obs") as mock_obs:
        mock_obs.ReqClient.side_effect = Exception("connection refused")
        assert client.connect() is False
        assert client._client is None


def test_connect_no_obsws(client):
    with patch("obs_client.obs", None):
        assert client.connect() is False


def test_is_streaming_true(client):
    mock_resp = MagicMock()
    mock_resp.output_active = True
    client._client = MagicMock()
    client._client.get_stream_status.return_value = mock_resp
    assert client.is_streaming() is True


def test_is_streaming_false(client):
    mock_resp = MagicMock()
    mock_resp.output_active = False
    client._client = MagicMock()
    client._client.get_stream_status.return_value = mock_resp
    assert client.is_streaming() is False


def test_is_streaming_no_client(client):
    assert client.is_streaming() is False


def test_set_game_capture_window(client):
    client._client = MagicMock()
    client.set_game_capture_window("Title:Class:game.exe")
    client._client.set_input_settings.assert_called_once_with(
        name="Game Capture",
        settings={"window": "Title:Class:game.exe"},
        overlay=True,
    )


def test_set_game_capture_window_no_client(client):
    # Should not raise
    client.set_game_capture_window("Title:Class:game.exe")


def test_get_game_capture_window_returns_window(client):
    mock_resp = MagicMock()
    mock_resp.input_settings = {"window": "Title:Class:game.exe"}
    client._client = MagicMock()
    client._client.get_input_settings.return_value = mock_resp
    assert client.get_game_capture_window() == "Title:Class:game.exe"
    client._client.get_input_settings.assert_called_once_with(name="Game Capture")


def test_get_game_capture_window_no_client(client):
    assert client.get_game_capture_window() is None


def test_get_game_capture_window_exception(client):
    client._client = MagicMock()
    client._client.get_input_settings.side_effect = Exception("failed")
    assert client.get_game_capture_window() is None


def test_is_connected_true(client):
    client._client = MagicMock()
    assert client.is_connected() is True
    client._client.get_version.assert_called_once()


def test_is_connected_no_client(client):
    assert client.is_connected() is False


def test_is_connected_exception(client):
    client._client = MagicMock()
    client._client.get_version.side_effect = Exception("disconnected")
    assert client.is_connected() is False


def test_start_stream(client):
    client._client = MagicMock()
    client.start_stream()
    client._client.start_stream.assert_called_once()


def test_stop_stream(client):
    client._client = MagicMock()
    client.stop_stream()
    client._client.stop_stream.assert_called_once()


def test_disconnect(client):
    mock_client = MagicMock()
    client._client = mock_client
    client.disconnect()
    mock_client.disconnect.assert_called_once()
    assert client._client is None
