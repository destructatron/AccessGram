"""GStreamer-based audio recorder for AccessGram.

Handles recording voice messages in OGG/Opus format
as required by Telegram.
"""

import logging
import tempfile
from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gst", "1.0")

from gi.repository import GLib, Gst

logger = logging.getLogger(__name__)


class RecorderState(Enum):
    """Audio recorder state."""

    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()


class AudioRecorder:
    """GStreamer-based audio recorder.

    Records audio from the default input device and encodes to
    OGG/Opus format for Telegram voice messages.
    """

    def __init__(self) -> None:
        """Initialize the audio recorder."""
        self._pipeline: Gst.Pipeline | None = None
        self._state = RecorderState.IDLE
        self._output_path: Path | None = None

        # Callbacks
        self._on_state_changed: Callable[[RecorderState], None] | None = None
        self._on_level_changed: Callable[[float], None] | None = None
        self._on_error: Callable[[str], None] | None = None

        # Duration tracking
        self._start_time: float = 0
        self._duration_timer: int | None = None

    @property
    def state(self) -> RecorderState:
        """Get current recorder state."""
        return self._state

    @property
    def output_path(self) -> Path | None:
        """Get the output file path."""
        return self._output_path

    def set_callbacks(
        self,
        on_state_changed: Callable[[RecorderState], None] | None = None,
        on_level_changed: Callable[[float], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Set recorder callbacks.

        Args:
            on_state_changed: Called when recorder state changes.
            on_level_changed: Called with audio level (0.0 - 1.0).
            on_error: Called with error message on error.
        """
        self._on_state_changed = on_state_changed
        self._on_level_changed = on_level_changed
        self._on_error = on_error

    def start(self, output_path: Path | str | None = None) -> bool:
        """Start recording.

        Args:
            output_path: Path for output file. If None, uses temp file.

        Returns:
            True if recording started successfully.
        """
        if self._state == RecorderState.RECORDING:
            logger.warning("Already recording")
            return False

        # Clean up any existing pipeline
        self._cleanup()

        # Set up output path
        if output_path:
            self._output_path = Path(output_path)
        else:
            # Create temp file
            fd, path = tempfile.mkstemp(suffix=".ogg", prefix="voice_")
            self._output_path = Path(path)

        try:
            # Build the pipeline
            # Pipeline: autoaudiosrc -> audioconvert -> audioresample -> opusenc -> oggmux -> filesink
            pipeline_str = (
                "autoaudiosrc ! "
                "audioconvert ! "
                "audioresample ! "
                "level interval=100000000 ! "  # 100ms intervals for level monitoring
                "opusenc bitrate=64000 ! "
                "oggmux ! "
                f"filesink location={self._output_path}"
            )

            self._pipeline = Gst.parse_launch(pipeline_str)
            if not self._pipeline:
                raise RuntimeError("Failed to create recording pipeline")

            # Connect to bus messages
            bus = self._pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::error", self._on_gst_error)
            bus.connect("message::element", self._on_gst_element)
            bus.connect("message::state-changed", self._on_gst_state_changed)

            # Start recording
            ret = self._pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Failed to start recording")

            self._state = RecorderState.RECORDING
            self._start_time = GLib.get_monotonic_time() / 1_000_000  # Convert to seconds

            logger.info("Started recording to: %s", self._output_path)

            if self._on_state_changed:
                self._on_state_changed(self._state)

            return True

        except Exception as e:
            logger.exception("Failed to start recording: %s", e)
            self._cleanup()
            if self._on_error:
                self._on_error(str(e))
            return False

    def pause(self) -> bool:
        """Pause recording.

        Returns:
            True if paused successfully.
        """
        if not self._pipeline or self._state != RecorderState.RECORDING:
            return False

        ret = self._pipeline.set_state(Gst.State.PAUSED)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Failed to pause recording")
            return False

        self._state = RecorderState.PAUSED
        if self._on_state_changed:
            self._on_state_changed(self._state)

        return True

    def resume(self) -> bool:
        """Resume recording after pause.

        Returns:
            True if resumed successfully.
        """
        if not self._pipeline or self._state != RecorderState.PAUSED:
            return False

        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Failed to resume recording")
            return False

        self._state = RecorderState.RECORDING
        if self._on_state_changed:
            self._on_state_changed(self._state)

        return True

    def stop(self) -> Path | None:
        """Stop recording and return the output file path.

        Returns:
            Path to the recorded file, or None if no recording.
        """
        if not self._pipeline:
            return None

        # Send EOS to properly close the file
        self._pipeline.send_event(Gst.Event.new_eos())

        # Wait for EOS to be processed (with timeout)
        bus = self._pipeline.get_bus()
        bus.timed_pop_filtered(Gst.SECOND * 5, Gst.MessageType.EOS | Gst.MessageType.ERROR)

        # Stop the pipeline
        self._pipeline.set_state(Gst.State.NULL)

        output = self._output_path
        self._state = RecorderState.IDLE

        if self._on_state_changed:
            self._on_state_changed(self._state)

        logger.info("Stopped recording. File: %s", output)

        # Clean up but keep the output path
        self._pipeline = None

        return output

    def cancel(self) -> None:
        """Cancel recording and delete the output file."""
        output = self._output_path
        self._cleanup()

        # Delete the temp file
        if output and output.exists():
            try:
                output.unlink()
                logger.info("Deleted cancelled recording: %s", output)
            except OSError as e:
                logger.warning("Failed to delete cancelled recording: %s", e)

        if self._on_state_changed:
            self._on_state_changed(self._state)

    def get_duration(self) -> float:
        """Get current recording duration in seconds."""
        if self._state != RecorderState.RECORDING:
            return 0.0

        current_time = GLib.get_monotonic_time() / 1_000_000
        return current_time - self._start_time

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._duration_timer:
            GLib.source_remove(self._duration_timer)
            self._duration_timer = None

        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None

        self._output_path = None
        self._state = RecorderState.IDLE

    def _on_gst_error(self, bus: Gst.Bus, message: Gst.Message) -> None:
        """Handle GStreamer error."""
        err, debug = message.parse_error()
        logger.error("GStreamer recording error: %s (%s)", err, debug)
        self._cleanup()

        if self._on_error:
            self._on_error(str(err))

    def _on_gst_element(self, bus: Gst.Bus, message: Gst.Message) -> None:
        """Handle GStreamer element messages (for level monitoring)."""
        structure = message.get_structure()
        if not structure:
            return

        if structure.get_name() == "level":
            # Get RMS levels (we'll use the max of all channels)
            rms = structure.get_value("rms")
            if rms:
                # Convert from dB to linear (0.0 - 1.0)
                # RMS values are in dB, typically -60 to 0
                max_rms = max(rms)
                # Normalize: -60dB -> 0.0, 0dB -> 1.0
                level = (max_rms + 60) / 60
                level = max(0.0, min(1.0, level))

                if self._on_level_changed:
                    self._on_level_changed(level)

    def _on_gst_state_changed(
        self,
        bus: Gst.Bus,
        message: Gst.Message,
    ) -> None:
        """Handle GStreamer state change."""
        if message.src != self._pipeline:
            return

        old_state, new_state, pending = message.parse_state_changed()
        logger.debug(
            "Recorder state changed: %s -> %s",
            old_state.value_nick,
            new_state.value_nick,
        )

    def __del__(self) -> None:
        """Clean up on deletion."""
        self._cleanup()


# Singleton instance
_recorder: AudioRecorder | None = None


def get_recorder() -> AudioRecorder:
    """Get the shared audio recorder instance."""
    global _recorder
    if _recorder is None:
        _recorder = AudioRecorder()
    return _recorder
