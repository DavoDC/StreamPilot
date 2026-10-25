"""STP-17: warn (log only) when the Twitch token is close to expiry."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from twitch_client import TwitchClient

DAY = 86400
T0 = 1_800_000_000.0


@pytest.fixture
def client():
    return TwitchClient("cid", "SECRETTOKEN")


def _validate(client, payload, now=T0):
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload
    with patch("twitch_client.requests.get", return_value=resp), patch("twitch_client.time.time", return_value=now):
        assert client.validate() is True


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def test_validate_records_expiry(client):
    _validate(client, {"user_id": "1", "expires_in": 5 * DAY})
    assert client._expires_at == T0 + 5 * DAY


def test_warns_inside_seven_day_threshold(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": 5 * DAY})
    with caplog.at_level(logging.WARNING):
        assert client.warn_if_expiring(now=T0) is True
    assert len(_warnings(caplog)) == 1
    assert "5.0 day" in _warnings(caplog)[0].getMessage()


def test_warns_again_at_one_day_threshold(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": 5 * DAY})
    with caplog.at_level(logging.WARNING):
        client.warn_if_expiring(now=T0)
        assert client.warn_if_expiring(now=T0 + 4.5 * DAY) is True
    assert len(_warnings(caplog)) == 2


def test_once_per_day_per_threshold(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": 5 * DAY})
    with caplog.at_level(logging.WARNING):
        assert client.warn_if_expiring(now=T0) is True
        assert client.warn_if_expiring(now=T0 + 60) is False
        assert client.warn_if_expiring(now=T0 + 120) is False
    assert len(_warnings(caplog)) == 1


def test_repeats_next_day(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": 5 * DAY})
    with caplog.at_level(logging.WARNING):
        client.warn_if_expiring(now=T0)
        assert client.warn_if_expiring(now=T0 + DAY + 3600) is True


def test_no_warning_when_far_from_expiry(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": 30 * DAY})
    with caplog.at_level(logging.WARNING):
        assert client.warn_if_expiring(now=T0) is False
    assert _warnings(caplog) == []


def test_expiry_unknown_is_silent(client, caplog):
    _validate(client, {"user_id": "1"})
    with caplog.at_level(logging.WARNING):
        assert client.warn_if_expiring(now=T0) is False
    assert client._expires_at is None
    assert _warnings(caplog) == []


def test_zero_expires_in_means_unknown(client):
    _validate(client, {"user_id": "1", "expires_in": 0})
    assert client._expires_at is None


def test_never_validated_is_silent(client, caplog):
    with caplog.at_level(logging.WARNING):
        assert client.warn_if_expiring(now=T0) is False


def test_token_never_logged(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": DAY})
    with caplog.at_level(logging.DEBUG):
        client.warn_if_expiring(now=T0)
    assert "SECRETTOKEN" not in caplog.text


def test_already_expired_warns(client, caplog):
    _validate(client, {"user_id": "1", "expires_in": 100})
    with caplog.at_level(logging.WARNING):
        assert client.warn_if_expiring(now=T0 + 1000) is True
    assert "expired" in _warnings(caplog)[0].getMessage()

