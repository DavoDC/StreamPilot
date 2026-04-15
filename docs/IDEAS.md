# StreamPilot - Ideas and TODOs

## Pending

1. **Add a `scripts/run-tests.bat`** - double-click test runner for easy local use
2. **System tray icon** - run StreamPilot in the system tray instead of a CLI window. Show status (idle/streaming/game detected), right-click menu to stop, show notifications via tray balloon tips. Use `pystray` + `Pillow` for the icon.

## Lower Priority

- Windows toast notification for unknown game detected ("Run 'streampilot config add-game'")
- `streampilot stop` command - send stop signal to running daemon process
- Auto-start with Windows (Task Scheduler entry)
- Multi-scene support (different scene per game)
