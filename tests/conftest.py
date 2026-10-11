"""Suite-wide safety: no test may ever create a real tray icon (it would sit in the user's notification area)."""

import os

os.environ["STREAMPILOT_NO_TRAY"] = "1"
