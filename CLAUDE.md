# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Development Commands

```bash
# Activate virtual environment (required for all commands)
source venv/bin/activate

# Run the application
python -m accessgram

# Install in development mode
pip install -e ".[dev]"

# Code quality
black accessgram/           # Format code
ruff check accessgram/      # Lint
mypy accessgram/            # Type check
```

## Architecture

### Event Loop Integration

The application bridges GTK's GLib main loop with Python's asyncio to support Telethon's async operations:

- `utils/async_bridge.py` sets up `GLibEventLoopPolicy` (PyGObject 3.50+)
- `run_async(coro)` schedules coroutines from synchronous GTK callbacks
- `create_task_with_callback()` provides callback-based async for UI updates

### Application Flow

1. `__main__.py` initializes GStreamer and sets up the async-GLib bridge
2. `app.py` (`AccessGramApplication`) manages lifecycle, shows credentials/login dialogs, transitions to main window
3. `core/auth.py` (`AuthManager`) handles phone/code/2FA authentication flow with state machine
4. `core/client.py` (`AccessGramClient`) wraps Telethon, manages event callbacks for messages/edits/deletes/reads
5. `ui/window.py` (`MainWindow`) contains the chat list and message view

### Key Patterns

**UI Updates from Async Code**: Use `GLib.idle_add()` to safely update GTK widgets from async callbacks:
```python
def _on_event(self, event):
    def update_ui():
        self._label.set_text(event.text)
        return False  # Don't repeat
    GLib.idle_add(update_ui)
```

**Telegram Event Handling**: Register callbacks via `AccessGramClient`:
```python
self._client.on_new_message(self._on_new_message_event)
self._client.on_message_read(self._on_message_read_event)
```

**Accessibility**: Every interactive widget needs:
- `update_property([Gtk.AccessibleProperty.LABEL], ["description"])` for accessible labels
- `update_relation([Gtk.AccessibleRelation.LABELLED_BY], [label_widget])` for form fields
- Use `ScreenReaderAnnouncer` for dynamic announcements (new messages, actions)

### Data Flow

- Config stored in `~/.config/accessgram/config.json`
- Session file in `~/.local/share/accessgram/`
- Downloads go to `~/.local/share/accessgram/downloads/`

## UI Structure

- `ChatRow` / `MessageRow` are `Gtk.ListBoxRow` subclasses in `ui/window.py`
- `ui/widgets/` contains reusable widgets: `VoicePlayerWidget`, `VoiceRecorderWidget`, `MediaDownloadWidget`
- All use GTK4's `GtkListBox` (not `GtkListView`) for better screen reader support

## Audio

- `audio/player.py`: GStreamer pipeline for OGG/Opus playback
- `audio/recorder.py`: GStreamer pipeline for voice recording
- Both use callbacks for state/level/position changes, updated via `GLib.idle_add()`
