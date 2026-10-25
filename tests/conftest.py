"""Suite-wide safety: no test may ever create a real tray icon (it would sit in the user's notification area)."""

import os

os.environ["STREAMPILOT_NO_TRAY"] = "1"


import pytest


@pytest.fixture(autouse=True)
def _isolate_daemon_state_paths(tmp_path, monkeypatch):
    """Daemon tests must never write the shared data/state files (a live daemon,
    its dashboard or a concurrent test run reads them; Windows os.replace races)."""
    try:
        import daemon
    except Exception:
        return
    monkeypatch.setattr(daemon, "STATUS_PATH", str(tmp_path / "status.json"))
    monkeypatch.setattr(daemon, "SAB_SETTINGS_PATH", str(tmp_path / "sab_settings.json"))
