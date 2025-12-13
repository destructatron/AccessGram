"""Media download widget for AccessGram.

Provides an accessible download interface for media messages
with progress display and file opening.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from accessgram.core.media import MediaManager, format_file_size
from accessgram.utils.async_bridge import create_task_with_callback

logger = logging.getLogger(__name__)


class MediaDownloadWidget(Gtk.Box):
    """Widget for downloading media from messages.

    Shows file info, download button, progress bar, and
    provides option to open downloaded files.
    """

    def __init__(
        self,
        message: Any,
        media_manager: MediaManager | None = None,
        media_type: str = "file",
    ) -> None:
        """Initialize the media download widget.

        Args:
            message: The Telethon message containing media.
            media_manager: MediaManager for handling downloads.
            media_type: Type of media ("photo", "video", "document", "audio").
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.message = message
        self._media_manager = media_manager
        self._media_type = media_type
        self._downloaded_path: Path | None = None
        self._is_downloading = False

        self._filename = self._get_filename()
        self._file_size = self._get_file_size()

        self._build_ui()

    def _get_filename(self) -> str:
        """Get the filename for the media."""
        if self.message.document:
            for attr in self.message.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    return attr.file_name
            return f"Document"
        elif self.message.photo:
            return "Photo"
        elif self.message.video:
            return "Video"
        elif self.message.audio:
            for attr in getattr(self.message.audio, "attributes", []):
                if hasattr(attr, "file_name") and attr.file_name:
                    return attr.file_name
            return "Audio"
        return "File"

    def _get_file_size(self) -> int:
        """Get the file size in bytes."""
        if self.message.document:
            return getattr(self.message.document, "size", 0)
        elif self.message.photo:
            # Get largest photo size
            if self.message.photo.sizes:
                for size in reversed(self.message.photo.sizes):
                    if hasattr(size, "size"):
                        return size.size
            return 0
        elif self.message.video:
            return getattr(self.message.video, "size", 0)
        elif self.message.audio:
            return getattr(self.message.audio, "size", 0)
        return 0

    def _get_icon_name(self) -> str:
        """Get icon name for the media type."""
        icons = {
            "photo": "image-x-generic-symbolic",
            "video": "video-x-generic-symbolic",
            "audio": "audio-x-generic-symbolic",
            "document": "text-x-generic-symbolic",
        }
        return icons.get(self._media_type, "folder-documents-symbolic")

    def _build_ui(self) -> None:
        """Build the widget UI."""
        # Icon
        icon = Gtk.Image.new_from_icon_name(self._get_icon_name())
        icon.set_pixel_size(24)
        self.append(icon)

        # Info box
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        # Filename
        self._filename_label = Gtk.Label(label=self._filename)
        self._filename_label.set_xalign(0)
        self._filename_label.set_ellipsize(True)
        info_box.append(self._filename_label)

        # Size
        if self._file_size > 0:
            size_str = format_file_size(self._file_size)
            self._size_label = Gtk.Label(label=size_str)
            self._size_label.set_xalign(0)
            self._size_label.add_css_class("dim-label")
            self._size_label.add_css_class("caption")
            info_box.append(self._size_label)

        # Progress bar (hidden by default)
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_visible(False)
        self._progress_bar.set_hexpand(True)
        info_box.append(self._progress_bar)

        self.append(info_box)

        # Download/Open button
        self._action_button = Gtk.Button()
        self._action_button.set_icon_name("folder-download-symbolic")
        self._action_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"Download {self._filename}"],
        )
        self._action_button.connect("clicked", self._on_action_clicked)
        self.append(self._action_button)

        # Update accessibility
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"{self._media_type.capitalize()}: {self._filename}, {format_file_size(self._file_size) if self._file_size else 'unknown size'}"],
        )

    def _on_action_clicked(self, button: Gtk.Button) -> None:
        """Handle action button click."""
        if self._downloaded_path and self._downloaded_path.exists():
            # Open the file
            self._open_file(self._downloaded_path)
        elif not self._is_downloading:
            # Start download
            self._start_download()

    def _start_download(self) -> None:
        """Start downloading the media."""
        if not self._media_manager:
            logger.warning("No media manager available for download")
            return

        self._is_downloading = True
        self._action_button.set_sensitive(False)
        self._progress_bar.set_visible(True)
        self._progress_bar.set_fraction(0)

        create_task_with_callback(
            self._media_manager.download_media(
                self.message,
                progress_callback=self._on_progress,
            ),
            self._on_download_complete,
            self._on_download_error,
        )

    def _on_progress(self, current: int, total: int) -> None:
        """Handle download progress."""
        def update():
            if total > 0:
                fraction = current / total
                self._progress_bar.set_fraction(fraction)
                percent = int(fraction * 100)
                self._progress_bar.update_property(
                    [Gtk.AccessibleProperty.VALUE_NOW],
                    [percent],
                )
            return False

        GLib.idle_add(update)

    def _on_download_complete(self, path: Path | None) -> None:
        """Handle download completion."""
        self._is_downloading = False
        self._progress_bar.set_visible(False)
        self._action_button.set_sensitive(True)

        if path and path.exists():
            self._downloaded_path = path
            # Update button to "Open"
            self._action_button.set_icon_name("document-open-symbolic")
            self._action_button.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [f"Open {self._filename}"],
            )
            logger.info("Downloaded to: %s", path)
        else:
            logger.error("Download failed - no file path returned")

    def _on_download_error(self, error: Exception) -> None:
        """Handle download error."""
        self._is_downloading = False
        self._progress_bar.set_visible(False)
        self._action_button.set_sensitive(True)
        logger.exception("Download failed: %s", error)

    def _open_file(self, path: Path) -> None:
        """Open a file with the default application."""
        try:
            # Use xdg-open on Linux
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Opened file: %s", path)
        except Exception as e:
            logger.exception("Failed to open file: %s", e)
