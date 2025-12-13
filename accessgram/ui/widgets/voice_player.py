"""Voice message player widget for AccessGram.

Provides an accessible audio player for Telegram voice messages
with play/pause controls and progress display.
"""

import logging
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from accessgram.audio.player import AudioPlayer, PlayerState, get_player
from accessgram.core.media import MediaManager
from accessgram.utils.async_bridge import create_task_with_callback

logger = logging.getLogger(__name__)


class VoicePlayerWidget(Gtk.Box):
    """Widget for playing voice messages.

    Displays play/pause button, progress bar, and duration.
    Handles downloading voice messages before playback.
    """

    def __init__(self, message: Any, media_manager: MediaManager | None = None) -> None:
        """Initialize the voice player widget.

        Args:
            message: The Telethon message containing a voice note.
            media_manager: Optional media manager for downloads.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.message = message
        self._media_manager = media_manager
        self._player = get_player()
        self._voice_path: Path | None = None
        self._is_current = False  # Whether this widget owns the player
        self._duration = self._get_duration()

        self._build_ui()

    def _get_duration(self) -> int:
        """Get voice message duration in seconds."""
        if self.message.voice and self.message.voice.attributes:
            for attr in self.message.voice.attributes:
                if hasattr(attr, "duration"):
                    return attr.duration
        return 0

    def _format_time(self, seconds: float) -> str:
        """Format seconds as M:SS."""
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins}:{secs:02d}"

    def _build_ui(self) -> None:
        """Build the player UI."""
        # Play/Pause button
        self._play_button = Gtk.Button()
        self._play_button.set_icon_name("media-playback-start-symbolic")
        self._play_button.add_css_class("circular")
        self._play_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Play voice message"],
        )
        self._play_button.connect("clicked", self._on_play_clicked)
        self.append(self._play_button)

        # Progress/time display
        time_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        time_box.set_hexpand(True)

        # Progress bar
        self._progress = Gtk.ProgressBar()
        self._progress.set_fraction(0)
        self._progress.set_hexpand(True)
        self._progress.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Playback progress"],
        )
        time_box.append(self._progress)

        # Time labels
        time_labels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        time_labels.set_hexpand(True)

        self._position_label = Gtk.Label(label="0:00")
        self._position_label.add_css_class("caption")
        self._position_label.add_css_class("dim-label")
        self._position_label.set_xalign(0)
        time_labels.append(self._position_label)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        time_labels.append(spacer)

        self._duration_label = Gtk.Label(label=self._format_time(self._duration))
        self._duration_label.add_css_class("caption")
        self._duration_label.add_css_class("dim-label")
        self._duration_label.set_xalign(1)
        time_labels.append(self._duration_label)

        time_box.append(time_labels)
        self.append(time_box)

        # Loading spinner (hidden by default)
        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        self.append(self._spinner)

    def _on_play_clicked(self, button: Gtk.Button) -> None:
        """Handle play/pause button click."""
        if self._is_current and self._player.state == PlayerState.PLAYING:
            # Pause
            self._player.pause()
            self._update_button_state(PlayerState.PAUSED)
        elif self._is_current and self._player.state == PlayerState.PAUSED:
            # Resume
            self._player.play()
            self._update_button_state(PlayerState.PLAYING)
        elif self._voice_path and self._voice_path.exists():
            # Play from downloaded file
            self._start_playback()
        else:
            # Need to download first
            self._download_and_play()

    def _download_and_play(self) -> None:
        """Download the voice message and then play it."""
        self._set_loading(True)
        self._play_button.set_sensitive(False)

        # Download to cache
        create_task_with_callback(
            self._download_voice(),
            self._on_download_complete,
            self._on_download_error,
        )

    async def _download_voice(self) -> Path | None:
        """Download the voice message."""
        if self._media_manager:
            return await self._media_manager.download_voice(self.message)
        else:
            # Fallback: use client directly (need to get it somehow)
            # For now, just return None
            logger.warning("No media manager available for download")
            return None

    def _on_download_complete(self, path: Path | None) -> None:
        """Handle download completion."""
        self._set_loading(False)
        self._play_button.set_sensitive(True)

        if path:
            self._voice_path = path
            self._start_playback()
        else:
            logger.error("Failed to download voice message")

    def _on_download_error(self, error: Exception) -> None:
        """Handle download error."""
        self._set_loading(False)
        self._play_button.set_sensitive(True)
        logger.exception("Failed to download voice message: %s", error)

    def _start_playback(self) -> None:
        """Start playing the voice message."""
        if not self._voice_path:
            return

        # Stop any other playback
        if self._player.state != PlayerState.STOPPED:
            self._player.stop()

        # Set up callbacks
        self._player.set_callbacks(
            on_state_changed=self._on_state_changed,
            on_position_changed=self._on_position_changed,
            on_finished=self._on_finished,
            on_error=self._on_error,
        )

        # Load and play
        if self._player.load(self._voice_path):
            self._is_current = True
            self._player.play()
            self._update_button_state(PlayerState.PLAYING)

    def _on_state_changed(self, state: PlayerState) -> None:
        """Handle player state changes."""
        GLib.idle_add(self._update_button_state, state)

    def _on_position_changed(self, position: float, duration: float) -> None:
        """Handle position updates."""
        def update():
            if duration > 0:
                self._progress.set_fraction(position / duration)
            self._position_label.set_label(self._format_time(position))
            return False

        GLib.idle_add(update)

    def _on_finished(self) -> None:
        """Handle playback finished."""
        def reset():
            self._is_current = False
            self._update_button_state(PlayerState.STOPPED)
            self._progress.set_fraction(0)
            self._position_label.set_label("0:00")
            return False

        GLib.idle_add(reset)

    def _on_error(self, error: str) -> None:
        """Handle playback error."""
        logger.error("Voice playback error: %s", error)
        GLib.idle_add(self._on_finished)

    def _update_button_state(self, state: PlayerState) -> None:
        """Update button icon based on player state."""
        if state == PlayerState.PLAYING:
            self._play_button.set_icon_name("media-playback-pause-symbolic")
            self._play_button.update_property(
                [Gtk.AccessibleProperty.LABEL],
                ["Pause voice message"],
            )
        else:
            self._play_button.set_icon_name("media-playback-start-symbolic")
            self._play_button.update_property(
                [Gtk.AccessibleProperty.LABEL],
                ["Play voice message"],
            )

    def _set_loading(self, loading: bool) -> None:
        """Show/hide loading state."""
        self._spinner.set_visible(loading)
        if loading:
            self._spinner.start()
        else:
            self._spinner.stop()

    def stop(self) -> None:
        """Stop playback if this widget owns the player."""
        if self._is_current:
            self._player.stop()
            self._is_current = False
