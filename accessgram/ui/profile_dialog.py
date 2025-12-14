"""Profile dialog for AccessGram.

Displays user profile information including bio, phone number,
and provides actions like messaging the user.
"""

import logging
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from accessgram.core.client import AccessGramClient
from accessgram.utils.async_bridge import create_task_with_callback

logger = logging.getLogger(__name__)


class ProfileDialog(Gtk.Window):
    """Dialog for displaying user profile information."""

    def __init__(
        self,
        parent: Gtk.Window,
        client: AccessGramClient,
        user: Any,
        on_message: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize the profile dialog.

        Args:
            parent: Parent window.
            client: Telegram client.
            user: The user entity to display.
            on_message: Callback when "Message" button is clicked.
        """
        super().__init__(
            title="Profile",
            transient_for=parent,
            modal=True,
            default_width=400,
            default_height=450,
        )

        self._client = client
        self._user = user
        self._on_message = on_message
        self._user_info: dict[str, Any] = {}

        self._build_ui()
        self._update_accessibility()
        self._load_profile()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.set_titlebar(header)

        # Content area with scrolling
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._content_box.set_margin_start(16)
        self._content_box.set_margin_end(16)
        self._content_box.set_margin_top(16)
        self._content_box.set_margin_bottom(16)

        # Loading spinner
        self._spinner = Gtk.Spinner()
        self._spinner.set_spinning(True)
        self._content_box.append(self._spinner)

        self._loading_label = Gtk.Label(label="Loading profile...")
        self._loading_label.add_css_class("dim-label")
        self._content_box.append(self._loading_label)

        scrolled.set_child(self._content_box)
        box.append(scrolled)

        # Action buttons at bottom
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_margin_start(16)
        button_box.set_margin_end(16)
        button_box.set_margin_top(8)
        button_box.set_margin_bottom(16)
        button_box.set_halign(Gtk.Align.END)

        self._message_button = Gtk.Button(label="Message")
        self._message_button.add_css_class("suggested-action")
        self._message_button.connect("clicked", self._on_message_clicked)
        self._message_button.set_sensitive(False)
        button_box.append(self._message_button)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda *args: self.close())
        button_box.append(close_button)

        box.append(button_box)
        self.set_child(box)

        # Set up Escape key to close dialog
        controller = Gtk.ShortcutController()
        self.add_controller(controller)
        controller.add_shortcut(
            Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
                action=Gtk.CallbackAction.new(lambda *args: self.close()),
            )
        )

    def _update_accessibility(self) -> None:
        """Update dialog accessibility."""
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["User profile dialog"],
        )

    def _load_profile(self) -> None:
        """Load the user's full profile information."""
        create_task_with_callback(
            self._client.get_full_user(self._user),
            self._on_profile_loaded,
            self._on_profile_error,
        )

    def _on_profile_loaded(self, info: dict[str, Any]) -> None:
        """Handle profile data loaded."""
        self._user_info = info
        self._spinner.set_spinning(False)
        self._spinner.set_visible(False)
        self._loading_label.set_visible(False)

        # Build profile display
        self._display_profile(info)

        # Enable message button
        self._message_button.set_sensitive(True)

    def _on_profile_error(self, error: Exception) -> None:
        """Handle profile loading error."""
        self._spinner.set_spinning(False)
        self._spinner.set_visible(False)
        self._loading_label.set_label(f"Failed to load profile: {error}")
        logger.exception("Failed to load profile: %s", error)

    def _display_profile(self, info: dict[str, Any]) -> None:
        """Display the profile information."""
        # Name
        first_name = info.get("first_name", "")
        last_name = info.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip() or "Unknown"

        name_label = Gtk.Label(label=full_name)
        name_label.set_xalign(0)
        name_label.add_css_class("title-1")
        self._content_box.append(name_label)

        # Username
        username = info.get("username", "")
        if username:
            username_label = Gtk.Label(label=f"@{username}")
            username_label.set_xalign(0)
            username_label.add_css_class("dim-label")
            self._content_box.append(username_label)

        # Badges (verified, premium, bot)
        badges = []
        if info.get("verified"):
            badges.append("Verified")
        if info.get("premium"):
            badges.append("Premium")
        if info.get("bot"):
            badges.append("Bot")

        if badges:
            badges_label = Gtk.Label(label=" | ".join(badges))
            badges_label.set_xalign(0)
            badges_label.add_css_class("caption")
            self._content_box.append(badges_label)

        # Separator
        separator1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator1.set_margin_top(8)
        separator1.set_margin_bottom(8)
        self._content_box.append(separator1)

        # Bio
        about = info.get("about", "")
        if about:
            bio_header = Gtk.Label(label="Bio")
            bio_header.set_xalign(0)
            bio_header.add_css_class("heading")
            self._content_box.append(bio_header)

            bio_label = Gtk.Label(label=about)
            bio_label.set_xalign(0)
            bio_label.set_wrap(True)
            bio_label.set_selectable(True)
            self._content_box.append(bio_label)
        else:
            no_bio_label = Gtk.Label(label="No bio")
            no_bio_label.set_xalign(0)
            no_bio_label.add_css_class("dim-label")
            self._content_box.append(no_bio_label)

        # Phone number
        phone = info.get("phone", "")
        if phone:
            separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            separator2.set_margin_top(8)
            separator2.set_margin_bottom(8)
            self._content_box.append(separator2)

            phone_header = Gtk.Label(label="Phone")
            phone_header.set_xalign(0)
            phone_header.add_css_class("heading")
            self._content_box.append(phone_header)

            phone_label = Gtk.Label(label=f"+{phone}")
            phone_label.set_xalign(0)
            phone_label.set_selectable(True)
            self._content_box.append(phone_label)

        # Common chats count
        common_chats = info.get("common_chats_count", 0)
        if common_chats > 0:
            separator3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            separator3.set_margin_top(8)
            separator3.set_margin_bottom(8)
            self._content_box.append(separator3)

            common_label = Gtk.Label(
                label=f"{common_chats} group{'s' if common_chats != 1 else ''} in common"
            )
            common_label.set_xalign(0)
            common_label.add_css_class("dim-label")
            self._content_box.append(common_label)

        # Update window title
        self.set_title(f"Profile - {full_name}")

        # Update accessibility
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"Profile for {full_name}"],
        )

    def _on_message_clicked(self, button: Gtk.Button) -> None:
        """Handle Message button click."""
        if self._on_message:
            self._on_message(self._user)
        self.close()
