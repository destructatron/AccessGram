"""Screen reader announcer for AccessGram.

Provides utilities for announcing messages to screen readers
via GTK4's accessibility APIs.
"""

import logging

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

logger = logging.getLogger(__name__)


class ScreenReaderAnnouncer:
    """Utility class for announcing messages to screen readers.

    Uses GTK4's `gtk_accessible_announce()` method (available in GTK 4.14+)
    to send announcements to screen readers like Orca.
    """

    def __init__(self, widget: Gtk.Widget) -> None:
        """Initialize the announcer.

        Args:
            widget: The widget to use for announcements (usually main window).
        """
        self._widget = widget
        self._has_announce = hasattr(widget, "announce")

        if not self._has_announce:
            logger.warning(
                "GTK widget does not have announce() method. "
                "Screen reader announcements may not work. "
                "Requires GTK 4.14 or later."
            )

    def announce(
        self,
        message: str,
        priority: Gtk.AccessibleAnnouncementPriority | None = None,
    ) -> None:
        """Announce a message to the screen reader.

        Args:
            message: The message to announce.
            priority: Announcement priority. Defaults to MEDIUM.
        """
        if not message:
            return

        if priority is None:
            priority = Gtk.AccessibleAnnouncementPriority.MEDIUM

        if self._has_announce:
            try:
                self._widget.announce(message, priority)
                logger.debug("Announced: %s", message)
            except Exception as e:
                logger.warning("Failed to announce message: %s", e)
        else:
            # Fallback: just log
            logger.info("Screen reader announcement: %s", message)

    def announce_polite(self, message: str) -> None:
        """Announce a message with low priority (polite).

        Use for non-urgent information that can wait.

        Args:
            message: The message to announce.
        """
        self.announce(message, Gtk.AccessibleAnnouncementPriority.LOW)

    def announce_assertive(self, message: str) -> None:
        """Announce a message with high priority (assertive).

        Use for urgent information that should interrupt.

        Args:
            message: The message to announce.
        """
        self.announce(message, Gtk.AccessibleAnnouncementPriority.HIGH)

    def announce_new_message(self, sender: str, preview: str) -> None:
        """Announce an incoming message.

        Args:
            sender: The sender's name.
            preview: A short preview of the message content.
        """
        self.announce(f"New message from {sender}: {preview}")

    def announce_sent(self) -> None:
        """Announce that a message was sent successfully."""
        self.announce_polite("Message sent")

    def announce_error(self, error: str) -> None:
        """Announce an error.

        Args:
            error: The error message.
        """
        self.announce_assertive(f"Error: {error}")

    def announce_loading(self, what: str) -> None:
        """Announce that something is loading.

        Args:
            what: What is being loaded.
        """
        self.announce_polite(f"Loading {what}")

    def announce_loaded(self, what: str, count: int | None = None) -> None:
        """Announce that something finished loading.

        Args:
            what: What was loaded.
            count: Optional count of items loaded.
        """
        if count is not None:
            self.announce_polite(f"Loaded {count} {what}")
        else:
            self.announce_polite(f"Loaded {what}")
