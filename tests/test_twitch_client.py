"""Tests for twitch_client.py"""

import pytest
from unittest.mock import MagicMock, patch
from twitch_client import TwitchClient


@pytest.fixture
def client():
    return TwitchClient("my_client_id", "my_token")


def test_oauth_prefix_stripped():
    c = TwitchClient("cid", "oauth:mytoken")
    assert c.oauth_token == "mytoken"


def test_validate_success(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"user_id": "123456"}
    with patch("twitch_client.requests.get", return_value=mock_resp):
        assert client.validate() is True
        assert client._broadcaster_id == "123456"


def test_validate_failure(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "invalid token"
    with patch("twitch_client.requests.get", return_value=mock_resp):
        assert client.validate() is False


def test_validate_network_error(client):
    with patch("twitch_client.requests.get", side_effect=Exception("timeout")):
        assert client.validate() is False


def test_set_game_success(client):
    client._broadcaster_id = "123456"
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch("twitch_client.requests.patch", return_value=mock_resp):
        client.set_game("17074")  # Should not raise


def test_set_game_validates_first(client):
    # No broadcaster_id set - should call validate
    validate_resp = MagicMock()
    validate_resp.status_code = 200
    validate_resp.json.return_value = {"user_id": "99"}
    patch_resp = MagicMock()
    patch_resp.status_code = 204
    with patch("twitch_client.requests.get", return_value=validate_resp):
        with patch("twitch_client.requests.patch", return_value=patch_resp):
            client.set_game("17074")
    assert client._broadcaster_id == "99"


def test_search_game_returns_results(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "17074", "name": "Dead by Daylight"}]}
    with patch("twitch_client.requests.get", return_value=mock_resp):
        results = client.search_game("dead by daylight")
    assert len(results) == 1
    assert results[0]["id"] == "17074"


def test_search_game_empty(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    with patch("twitch_client.requests.get", return_value=mock_resp):
        results = client.search_game("unknown game xyz")
    assert results == []


def test_search_game_network_error(client):
    with patch("twitch_client.requests.get", side_effect=Exception("timeout")):
        results = client.search_game("any game")
    assert results == []


def test_search_game_auth_error_logs_warning_not_silent(client, caplog):
    # A 401 (expired/revoked token) must be distinguishable in the logs from a
    # genuine "no results" - both currently return [], but only this case
    # should warn, so add-game's "not found" message isn't misleading.
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "invalid token"
    with patch("twitch_client.requests.get", return_value=mock_resp):
        with caplog.at_level("WARNING"):
            results = client.search_game("dead by daylight")
    assert results == []
    assert any("401" in r.message for r in caplog.records)


def test_get_current_game_name_success(client):
    client._broadcaster_id = "123456"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"game_name": "Marvel Rivals"}]}
    with patch("twitch_client.requests.get", return_value=mock_resp):
        assert client.get_current_game_name() == "Marvel Rivals"


def test_get_current_game_name_no_broadcaster_id(client):
    assert client.get_current_game_name() is None


def test_get_current_game_name_empty_data(client):
    client._broadcaster_id = "123456"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    with patch("twitch_client.requests.get", return_value=mock_resp):
        assert client.get_current_game_name() is None


def test_get_current_game_name_network_error(client):
    client._broadcaster_id = "123456"
    with patch("twitch_client.requests.get", side_effect=Exception("timeout")):
        assert client.get_current_game_name() is None


# --- search_game_robust ---

def test_search_game_robust_full_name_match(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "532273", "name": "Marvel Rivals"}]}
    with patch("twitch_client.requests.get", return_value=mock_resp) as mock_get:
        results = client.search_game_robust("Marvel Rivals")
    assert len(results) == 1
    assert results[0]["id"] == "532273"
    assert mock_get.call_count == 1


def test_search_game_robust_falls_back_to_first_word(client):
    full_resp = MagicMock()
    full_resp.status_code = 200
    full_resp.json.return_value = {"data": []}
    word_resp = MagicMock()
    word_resp.status_code = 200
    word_resp.json.return_value = {"data": [{"id": "532273", "name": "Marvel Rivals"}]}
    with patch("twitch_client.requests.get", side_effect=[full_resp, word_resp]):
        results = client.search_game_robust("Marvel Rivals")
    assert results[0]["id"] == "532273"


def test_search_game_robust_single_word_no_retry(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    with patch("twitch_client.requests.get", return_value=mock_resp) as mock_get:
        results = client.search_game_robust("Minecraft")
    assert results == []
    assert mock_get.call_count == 1


def test_search_game_robust_both_empty(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    with patch("twitch_client.requests.get", return_value=mock_resp):
        results = client.search_game_robust("Unknown XYZ Game")
    assert results == []


# --- set_channel_info ---

def test_set_channel_info_sends_all_fields_in_one_patch(client):
    client._broadcaster_id = "123456"
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch("twitch_client.requests.patch", return_value=mock_resp) as mock_patch:
        client.set_channel_info(game_id="17074", title="Davo plays Rivals!", tags=["English", "Ranked"])
    _, kwargs = mock_patch.call_args
    assert kwargs["json"] == {
        "game_id": "17074",
        "title": "Davo plays Rivals!",
        "tags": ["English", "Ranked"],
    }
    assert kwargs["params"] == {"broadcaster_id": "123456"}


def test_set_channel_info_omits_none_fields(client):
    client._broadcaster_id = "123456"
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch("twitch_client.requests.patch", return_value=mock_resp) as mock_patch:
        client.set_channel_info(title="Davo plays Rivals!")
    _, kwargs = mock_patch.call_args
    assert kwargs["json"] == {"title": "Davo plays Rivals!"}


def test_set_channel_info_validates_first(client):
    validate_resp = MagicMock()
    validate_resp.status_code = 200
    validate_resp.json.return_value = {"user_id": "99"}
    patch_resp = MagicMock()
    patch_resp.status_code = 204
    with patch("twitch_client.requests.get", return_value=validate_resp):
        with patch("twitch_client.requests.patch", return_value=patch_resp):
            client.set_channel_info(game_id="17074")
    assert client._broadcaster_id == "99"


def test_set_channel_info_logs_warning_on_failure(client, caplog):
    client._broadcaster_id = "123456"
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "bad request"
    with patch("twitch_client.requests.patch", return_value=mock_resp):
        with caplog.at_level("WARNING"):
            client.set_channel_info(title="Davo plays Rivals!")
    assert any("400" in r.message for r in caplog.records)


def test_set_channel_info_network_error_does_not_raise(client):
    client._broadcaster_id = "123456"
    with patch("twitch_client.requests.patch", side_effect=Exception("timeout")):
        client.set_channel_info(title="Davo plays Rivals!")  # Should not raise


def test_set_game_delegates_to_set_channel_info(client):
    client._broadcaster_id = "123456"
    with patch.object(client, "set_channel_info") as mock_sci:
        client.set_game("17074")
    mock_sci.assert_called_once_with(game_id="17074")
