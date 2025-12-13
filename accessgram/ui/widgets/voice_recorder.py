"""Voice message recording widget for AccessGram.

Provides an accessible voice recording interface with
recording controls, duration display, and level indicator.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from accessgram.audio.recorder import AudioRecorder, RecorderState, get_recorder

logger = logging.getLogger(__name__)


class VoiceRecorderWidget(Gtk.Box):
    """Widget for recording voice messages.

    Shows a microphone button when idle, switches to recording
    controls (cancel, duration, send) when recording.
    """

    def __init__(
        self,
        on_recording_complete: Callable[[Path], None] | None = None,
        on_recording_cancelled: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the voice recorder widget.

        Args:
            on_recording_complete: Called with the recorded file path when done.
            on_recording_cancelled: Called when recording is cancelled.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._on_recording_complete = on_recording_complete
        self._on_recording_cancelled = on_recording_cancelled
        self._recorder = get_recorder()
        self._duration_timer: int | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the widget UI."""
        # Stack for switching between idle and recording states
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)
        self.append(self._stack)

        # Idle state: microphone button
        self._idle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._record_button = Gtk.Button()
        self._record_button.set_icon_name("audio-input-microphone-symbolic")
        self._record_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Record voice message"],
        )
        self._record_button.connect("clicked", self._on_record_clicked)
        self._idle_box.append(self._record_button)
        self._stack.add_named(self._idle_box, "idle")

        # Recording state: cancel, duration, level, send
        self._recording_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Cancel button
        self._cancel_button = Gtk.Button()
        self._cancel_button.set_icon_name("process-stop-symbolic")
        self._cancel_button.add_css_class("destructive-action")
        self._cancel_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Cancel recording"],
        )
        self._cancel_button.connect("clicked", self._on_cancel_clicked)
        self._recording_box.append(self._cancel_button)

        # Recording indicator and duration
        indicator_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Recording dot (red circle)
        self._recording_dot = Gtk.Label(label="\u2022")  # Bullet point
        self._recording_dot.add_css_class("error")  # Red color
        indicator_box.append(self._recording_dot)

        # Duration label
        self._duration_label = Gtk.Label(label="0:00")
        self._duration_label.set_width_chars(5)
        self._duration_label.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Recording duration"],
        )
        indicator_box.append(self._duration_label)

        self._recording_box.append(indicator_box)

        # Level indicator (progress bar showing audio level)
        self._level_bar = Gtk.LevelBar()
        self._level_bar.set_min_value(0)
        self._level_bar.set_max_value(1)
        self._level_bar.set_value(0)
        self._level_bar.set_hexpand(True)
        self._level_bar.set_size_request(80, -1)
        self._level_bar.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Audio input level"],
        )
        self._recording_box.append(self._level_bar)

        # Send button
        self._send_button = Gtk.Button()
        self._send_button.set_icon_name("document-send-symbolic")
        self._send_button.add_css_class("suggested-action")
        self._send_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Send voice message"],
        )
        self._send_button.connect("clicked", self._on_send_clicked)
        self._recording_box.append(self._send_button)

        self._stack.add_named(self._recording_box, "recording")

        # Start in idle state
        self._stack.set_visible_child_name("idle")

    def _on_record_clicked(self, button: Gtk.Button) -> None:
        """Start recording."""
        self._recorder.set_callbacks(
            on_state_changed=self._on_recorder_state_changed,
            on_level_changed=self._on_level_changed,
            on_error=self._on_recorder_error,
        )

        if self._recorder.start():
            self._stack.set_visible_child_name("recording")
            self._start_duration_timer()
            # Announce to screen reader
            self._cancel_button.grab_focus()

    def _on_cancel_clicked(self, button: Gtk.Button) -> None:
        """Cancel recording."""
        self._stop_duration_timer()
        self._recorder.cancel()
        self._stack.set_visible_child_name("idle")
        self._reset_ui()

        if self._on_recording_cancelled:
            self._on_recording_cancelled()

    def _on_send_clicked(self, button: Gtk.Button) -> None:
        """Stop recording and send."""
        self._stop_duration_timer()
        output_path = self._recorder.stop()
        self._stack.set_visible_child_name("idle")
        self._reset_ui()

        if output_path and self._on_recording_complete:
            self._on_recording_complete(output_path)

    def _on_recorder_state_changed(self, state: RecorderState) -> None:
        """Handle recorder state changes."""

        def update():
            if state == RecorderState.IDLE:
                self._stack.set_visible_child_name("idle")
                self._stop_duration_timer()
                self._reset_ui()
            return False

        GLib.idle_add(update)

    def _on_level_changed(self, level: float) -> None:
        """Handle audio level changes."""

        def update():
            self._level_bar.set_value(level)
            return False

        GLib.idle_add(update)

    def _on_recorder_error(self, error: str) -> None:
        """Handle recorder errors."""
        logger.error("Recording error: %s", error)

        def update():
            self._stack.set_visible_child_name("idle")
            self._stop_duration_timer()
            self._reset_ui()
            return False

        GLib.idle_add(update)

    def _start_duration_timer(self) -> None:
        """Start the duration update timer."""
        self._stop_duration_timer()
        self._duration_timer = GLib.timeout_add(100, self._update_duration)

    def _stop_duration_timer(self) -> None:
        """Stop the duration update timer."""
        if self._duration_timer:
            GLib.source_remove(self._duration_timer)
            self._duration_timer = None

    def _update_duration(self) -> bool:
        """Update the duration display."""
        if self._recorder.state != RecorderState.RECORDING:
            return False

        duration = self._recorder.get_duration()
        mins = int(duration) // 60
        secs = int(duration) % 60
        self._duration_label.set_label(f"{mins}:{secs:02d}")

        # Update accessible description with current duration
        self._duration_label.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"Recording duration: {mins} minutes {secs} seconds"],
        )

        return True  # Continue timer

    def _reset_ui(self) -> None:
        """Reset UI to initial state."""
        self._duration_label.set_label("0:00")
        self._level_bar.set_value(0)

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recorder.state == RecorderState.RECORDING

    def cancel_recording(self) -> None:
        """Cancel any active recording."""
        if self.is_recording:
            self._on_cancel_clicked(self._cancel_button)
