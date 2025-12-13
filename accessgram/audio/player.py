"""GStreamer-based audio player for AccessGram.

Handles playback of voice messages and other audio files,
with support for OGG/Opus format used by Telegram.
"""

import logging
from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gst", "1.0")

from gi.repository import GLib, Gst

logger = logging.getLogger(__name__)


class PlayerState(Enum):
    """Audio player state."""

    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()


class AudioPlayer:
    """GStreamer-based audio player.

    Uses the playbin element for automatic format detection and decoding.
    Supports OGG/Opus files as used by Telegram voice messages.
    """

    def __init__(self) -> None:
        """Initialize the audio player."""
        self._pipeline: Gst.Element | None = None
        self._state = PlayerState.STOPPED
        self._current_file: Path | None = None

        # Callbacks
        self._on_state_changed: Callable[[PlayerState], None] | None = None
        self._on_position_changed: Callable[[float, float], None] | None = None
        self._on_finished: Callable[[], None] | None = None
        self._on_error: Callable[[str], None] | None = None

        # Position update timer
        self._position_timer: int | None = None

    @property
    def state(self) -> PlayerState:
        """Get current player state."""
        return self._state

    @property
    def current_file(self) -> Path | None:
        """Get the currently loaded file."""
        return self._current_file

    def set_callbacks(
        self,
        on_state_changed: Callable[[PlayerState], None] | None = None,
        on_position_changed: Callable[[float, float], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Set player callbacks.

        Args:
            on_state_changed: Called when player state changes.
            on_position_changed: Called with (position, duration) in seconds.
            on_finished: Called when playback finishes.
            on_error: Called with error message on error.
        """
        self._on_state_changed = on_state_changed
        self._on_position_changed = on_position_changed
        self._on_finished = on_finished
        self._on_error = on_error

    def load(self, file_path: Path | str) -> bool:
        """Load an audio file for playback.

        Args:
            file_path: Path to the audio file.

        Returns:
            True if loaded successfully.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("Audio file does not exist: %s", file_path)
            if self._on_error:
                self._on_error(f"File not found: {file_path}")
            return False

        # Clean up existing pipeline
        self._cleanup()

        try:
            # Create playbin pipeline
            self._pipeline = Gst.ElementFactory.make("playbin", "player")
            if not self._pipeline:
                raise RuntimeError("Failed to create playbin element")

            # Set the file URI
            uri = file_path.as_uri()
            self._pipeline.set_property("uri", uri)

            # Connect to bus messages
            bus = self._pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::eos", self._on_eos)
            bus.connect("message::error", self._on_gst_error)
            bus.connect("message::state-changed", self._on_gst_state_changed)

            self._current_file = file_path
            self._state = PlayerState.STOPPED
            logger.info("Loaded audio file: %s", file_path)
            return True

        except Exception as e:
            logger.exception("Failed to load audio file: %s", e)
            if self._on_error:
                self._on_error(str(e))
            return False

    def play(self) -> bool:
        """Start or resume playback.

        Returns:
            True if playback started successfully.
        """
        if not self._pipeline:
            logger.warning("No audio file loaded")
            return False

        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Failed to start playback")
            if self._on_error:
                self._on_error("Failed to start playback")
            return False

        self._start_position_updates()
        return True

    def pause(self) -> bool:
        """Pause playback.

        Returns:
            True if paused successfully.
        """
        if not self._pipeline:
            return False

        ret = self._pipeline.set_state(Gst.State.PAUSED)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Failed to pause playback")
            return False

        self._stop_position_updates()
        return True

    def stop(self) -> None:
        """Stop playback and reset position."""
        if not self._pipeline:
            return

        self._pipeline.set_state(Gst.State.NULL)
        self._stop_position_updates()
        self._state = PlayerState.STOPPED

        if self._on_state_changed:
            self._on_state_changed(self._state)

    def toggle(self) -> None:
        """Toggle between play and pause."""
        if self._state == PlayerState.PLAYING:
            self.pause()
        else:
            self.play()

    def seek(self, position_seconds: float) -> bool:
        """Seek to a position in the audio.

        Args:
            position_seconds: Position in seconds.

        Returns:
            True if seek was successful.
        """
        if not self._pipeline:
            return False

        position_ns = int(position_seconds * Gst.SECOND)
        return self._pipeline.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            position_ns,
        )

    def get_position(self) -> float:
        """Get current playback position in seconds."""
        if not self._pipeline:
            return 0.0

        success, position = self._pipeline.query_position(Gst.Format.TIME)
        if success:
            return position / Gst.SECOND
        return 0.0

    def get_duration(self) -> float:
        """Get total duration in seconds."""
        if not self._pipeline:
            return 0.0

        success, duration = self._pipeline.query_duration(Gst.Format.TIME)
        if success:
            return duration / Gst.SECOND
        return 0.0

    def _cleanup(self) -> None:
        """Clean up resources."""
        self._stop_position_updates()

        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None

        self._current_file = None
        self._state = PlayerState.STOPPED

    def _start_position_updates(self) -> None:
        """Start periodic position updates."""
        if self._position_timer:
            return

        def update_position() -> bool:
            if self._state != PlayerState.PLAYING:
                return False

            position = self.get_position()
            duration = self.get_duration()

            if self._on_position_changed:
                self._on_position_changed(position, duration)

            return True  # Continue timer

        self._position_timer = GLib.timeout_add(200, update_position)

    def _stop_position_updates(self) -> None:
        """Stop position updates."""
        if self._position_timer:
            GLib.source_remove(self._position_timer)
            self._position_timer = None

    def _on_eos(self, bus: Gst.Bus, message: Gst.Message) -> None:
        """Handle end-of-stream."""
        logger.debug("Playback finished")
        self.stop()

        if self._on_finished:
            self._on_finished()

    def _on_gst_error(self, bus: Gst.Bus, message: Gst.Message) -> None:
        """Handle GStreamer error."""
        err, debug = message.parse_error()
        logger.error("GStreamer error: %s (%s)", err, debug)
        self.stop()

        if self._on_error:
            self._on_error(str(err))

    def _on_gst_state_changed(
        self,
        bus: Gst.Bus,
        message: Gst.Message,
    ) -> None:
        """Handle GStreamer state change."""
        # Only handle messages from the pipeline
        if message.src != self._pipeline:
            return

        old_state, new_state, pending = message.parse_state_changed()

        if new_state == Gst.State.PLAYING:
            self._state = PlayerState.PLAYING
        elif new_state == Gst.State.PAUSED:
            self._state = PlayerState.PAUSED
        elif new_state == Gst.State.NULL:
            self._state = PlayerState.STOPPED

        logger.debug("Player state changed: %s -> %s", old_state.value_nick, new_state.value_nick)

        if self._on_state_changed:
            self._on_state_changed(self._state)

    def __del__(self) -> None:
        """Clean up on deletion."""
        self._cleanup()


# Singleton instance for easy access
_player: AudioPlayer | None = None


def get_player() -> AudioPlayer:
    """Get the shared audio player instance."""
    global _player
    if _player is None:
        _player = AudioPlayer()
    return _player
