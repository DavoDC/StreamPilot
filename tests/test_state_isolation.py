"""Guard: running the daemon heartbeat in tests never touches the shared data/state/status.json."""
import os

import daemon as daemon_mod


def test_heartbeat_writes_to_test_scoped_status_path(tmp_path):
    real = os.path.abspath(os.path.join(os.path.dirname(daemon_mod.__file__), "..", "data", "state", "status.json"))
    assert os.path.abspath(daemon_mod.STATUS_PATH) != real
    assert os.path.abspath(daemon_mod.STATUS_PATH).startswith(str(tmp_path))
