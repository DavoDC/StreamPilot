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
