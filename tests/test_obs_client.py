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


# --- Audio privacy guard methods ---

def test_get_audio_capture_settings_returns_settings(client):
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [], "mode": 0}
    client._client = MagicMock()
    client._client.get_input_settings.return_value = mock_resp
    assert client.get_audio_capture_settings() == {"executable_list": [], "mode": 0}
    client._client.get_input_settings.assert_called_once_with(name="Application Audio Output Capture")


def test_get_audio_capture_settings_no_client_returns_none(client):
    assert client.get_audio_capture_settings() is None


def test_get_audio_capture_settings_exception_returns_none(client):
    client._client = MagicMock()
    client._client.get_input_settings.side_effect = Exception("unreachable")
    assert client.get_audio_capture_settings() is None


def test_get_audio_capture_settings_uses_configured_source_name():
    c = OBSClient("localhost", 4455, "pw", "Game Capture", audio_source_name="My Audio Source")
    c._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {}
    c._client.get_input_settings.return_value = mock_resp
    c.get_audio_capture_settings()
    c._client.get_input_settings.assert_called_once_with(name="My Audio Source")


def test_set_audio_capture_exes_adds_new_entry(client):
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": []}
    client._client.get_input_settings.return_value = mock_resp

    result = client.set_audio_capture_exes(["game.exe"])

    assert result is True
    _, kwargs = client._client.set_input_settings.call_args
    assert kwargs["name"] == "Application Audio Output Capture"
    assert kwargs["overlay"] is True
    new_list = kwargs["settings"]["executable_list"]
    assert len(new_list) == 1
    assert new_list[0]["value"] == "game.exe"
    assert new_list[0]["hidden"] is False
    assert new_list[0]["selected"] is False
    assert new_list[0]["uuid"]  # a uuid4 string was generated


def test_set_audio_capture_exes_preserves_existing_entries(client):
    existing_entry = {"hidden": True, "selected": True, "uuid": "existing-uuid", "value": "old.exe"}
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [existing_entry]}
    client._client.get_input_settings.return_value = mock_resp

    client.set_audio_capture_exes(["new.exe"])

    _, kwargs = client._client.set_input_settings.call_args
    new_list = kwargs["settings"]["executable_list"]
    assert existing_entry in new_list
    assert any(e["value"] == "new.exe" for e in new_list)


def test_set_audio_capture_exes_skips_already_present_exe(client):
    existing_entry = {"hidden": False, "selected": False, "uuid": "existing-uuid", "value": "game.exe"}
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [existing_entry]}
    client._client.get_input_settings.return_value = mock_resp

    client.set_audio_capture_exes(["game.exe"])

    _, kwargs = client._client.set_input_settings.call_args
    new_list = kwargs["settings"]["executable_list"]
    assert len(new_list) == 1
    assert new_list[0]["uuid"] == "existing-uuid"


def test_set_audio_capture_exes_no_client_returns_false(client):
    assert client.set_audio_capture_exes(["game.exe"]) is False


def test_set_audio_capture_exes_exception_returns_false(client):
    client._client = MagicMock()
    client._client.get_input_settings.side_effect = Exception("unreachable")
    assert client.set_audio_capture_exes(["game.exe"]) is False


# --- exact=True (exclusive-mode convergence) ---

def test_set_audio_capture_exes_exact_removes_entries_not_in_target(client):
    """exact=True is the one sanctioned removal path - anything already in
    the list that isn't in exe_values gets dropped."""
    stale_entry = {"hidden": False, "selected": False, "uuid": "stale-uuid", "value": "old_game.exe"}
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [stale_entry]}
    client._client.get_input_settings.return_value = mock_resp

    result = client.set_audio_capture_exes(["new_game.exe"], exact=True)

    assert result is True
    _, kwargs = client._client.set_input_settings.call_args
    new_list = kwargs["settings"]["executable_list"]
    assert [e["value"] for e in new_list] == ["new_game.exe"]


def test_set_audio_capture_exes_exact_preserves_uuid_for_retained_entries(client):
    existing_entry = {"hidden": True, "selected": True, "uuid": "keep-me", "value": "game.exe"}
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [existing_entry]}
    client._client.get_input_settings.return_value = mock_resp

    client.set_audio_capture_exes(["game.exe", "extra.exe"], exact=True)

    _, kwargs = client._client.set_input_settings.call_args
    new_list = kwargs["settings"]["executable_list"]
    kept = next(e for e in new_list if e["value"] == "game.exe")
    assert kept["uuid"] == "keep-me"
    assert kept["hidden"] is True
    added = next(e for e in new_list if e["value"] == "extra.exe")
    assert added["uuid"] and added["uuid"] != "keep-me"


def test_set_audio_capture_exes_exact_clears_to_empty(client):
    existing_entry = {"hidden": False, "selected": False, "uuid": "u1", "value": "game.exe"}
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [existing_entry]}
    client._client.get_input_settings.return_value = mock_resp

    result = client.set_audio_capture_exes([], exact=True)

    assert result is True
    _, kwargs = client._client.set_input_settings.call_args
    assert kwargs["settings"]["executable_list"] == []


def test_set_audio_capture_exes_exact_skips_write_when_already_converged(client):
    """No redundant SetInputSettings calls when the list already matches
    the target - avoids hammering OBS every 2s heartbeat cycle."""
    existing_entry = {"hidden": False, "selected": False, "uuid": "u1", "value": "game.exe"}
    client._client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.input_settings = {"executable_list": [existing_entry]}
    client._client.get_input_settings.return_value = mock_resp

    result = client.set_audio_capture_exes(["game.exe"], exact=True)

    assert result is True
    client._client.set_input_settings.assert_not_called()


def test_set_audio_capture_exes_exact_no_client_returns_false(client):
    assert client.set_audio_capture_exes(["game.exe"], exact=True) is False


def test_set_audio_capture_exes_exact_exception_returns_false(client):
    client._client = MagicMock()
    client._client.get_input_settings.side_effect = Exception("unreachable")
    assert client.set_audio_capture_exes(["game.exe"], exact=True) is False


def test_get_input_mute_returns_true_when_muted(client):
    mock_resp = MagicMock()
    mock_resp.input_muted = True
    client._client = MagicMock()
    client._client.get_input_mute.return_value = mock_resp
    assert client.get_input_mute("Desktop Audio") is True
    client._client.get_input_mute.assert_called_once_with(name="Desktop Audio")


def test_get_input_mute_returns_false_when_not_muted(client):
    mock_resp = MagicMock()
    mock_resp.input_muted = False
    client._client = MagicMock()
    client._client.get_input_mute.return_value = mock_resp
    assert client.get_input_mute("Desktop Audio") is False


def test_get_input_mute_fails_closed_on_no_client(client):
    """Privacy guard: unreachable must be treated as a potential leak, not safe."""
    assert client.get_input_mute("Desktop Audio") is False


def test_get_input_mute_fails_closed_on_exception(client):
    client._client = MagicMock()
    client._client.get_input_mute.side_effect = Exception("unreachable")
    assert client.get_input_mute("Desktop Audio") is False


def test_get_input_volume_db_returns_value(client):
    mock_resp = MagicMock()
    mock_resp.input_volume_db = -65.0
    client._client = MagicMock()
    client._client.get_input_volume.return_value = mock_resp
    assert client.get_input_volume_db("Desktop Audio") == -65.0
    client._client.get_input_volume.assert_called_once_with(name="Desktop Audio")


def test_get_input_volume_db_fails_closed_on_no_client(client):
    """Privacy guard: unreachable must be treated as full volume (leak), not safe."""
    assert client.get_input_volume_db("Desktop Audio") == 0.0


def test_get_input_volume_db_fails_closed_on_exception(client):
    client._client = MagicMock()
    client._client.get_input_volume.side_effect = Exception("unreachable")
    assert client.get_input_volume_db("Desktop Audio") == 0.0


def test_list_inputs_by_kind_filters_correctly(client):
    mock_resp = MagicMock()
    mock_resp.inputs = [
        {"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"},
        {"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"},
        {"inputName": "Game Capture", "inputKind": "game_capture"},
    ]
    client._client = MagicMock()
    client._client.get_input_list.return_value = mock_resp
    assert client.list_inputs_by_kind("wasapi_output_capture") == ["Desktop Audio"]
    assert client.list_inputs_by_kind("wasapi_input_capture") == ["Mic/Aux"]


def test_list_inputs_by_kind_no_client_returns_empty(client):
    assert client.list_inputs_by_kind("wasapi_output_capture") == []


def test_list_inputs_by_kind_exception_returns_empty(client):
    client._client = MagicMock()
    client._client.get_input_list.side_effect = Exception("unreachable")
    assert client.list_inputs_by_kind("wasapi_output_capture") == []
