"""Main application window for AccessGram.

This module contains the main window with the chat list sidebar
and message view area.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk

from accessgram.accessibility.announcer import ScreenReaderAnnouncer
from accessgram.core.client import AccessGramClient
from accessgram.core.media import MediaManager
from accessgram.ui.search_dialog import SearchDialog
from accessgram.ui.widgets.media_download import MediaDownloadWidget
from accessgram.ui.widgets.voice_player import VoicePlayerWidget
from accessgram.ui.widgets.voice_recorder import VoiceRecorderWidget
from accessgram.utils.async_bridge import create_task_with_callback, run_async
from accessgram.utils.config import Config

logger = logging.getLogger(__name__)


class ChatRow(Gtk.ListBoxRow):
    """A row in the chat list representing a dialog."""

    def __init__(self, dialog: Any) -> None:
        """Initialize a chat row.

        Args:
            dialog: The Telethon Dialog object.
        """
        super().__init__()
        self.dialog = dialog
        self._build_ui()
        self._update_accessibility()

    def _build_ui(self) -> None:
        """Build the row UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        # Chat info (name and preview)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)

        # Chat name
        self._name_label = Gtk.Label(label=self.dialog.name or "Unknown")
        self._name_label.set_xalign(0)
        self._name_label.set_ellipsize(True)
        self._name_label.add_css_class("heading")
        info_box.append(self._name_label)

        # Last message preview
        preview_text = self._get_preview_text()
        self._preview_label = Gtk.Label(label=preview_text)
        self._preview_label.set_xalign(0)
        self._preview_label.set_ellipsize(True)
        self._preview_label.add_css_class("dim-label")
        info_box.append(self._preview_label)

        box.append(info_box)

        # Right side: unread count and time
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_box.set_valign(Gtk.Align.CENTER)

        # Time of last message
        if self.dialog.message and self.dialog.message.date:
            time_str = self._format_time(self.dialog.message.date)
            time_label = Gtk.Label(label=time_str)
            time_label.add_css_class("dim-label")
            time_label.add_css_class("caption")
            right_box.append(time_label)

        # Unread count badge (always create, hide if 0)
        self._unread_label = Gtk.Label(label=str(self.dialog.unread_count) if self.dialog.unread_count else "")
        self._unread_label.add_css_class("badge")
        self._unread_label.add_css_class("accent")
        self._unread_label.set_halign(Gtk.Align.END)
        self._unread_label.set_visible(self.dialog.unread_count > 0)
        right_box.append(self._unread_label)

        box.append(right_box)
        self.set_child(box)

    def _get_preview_text(self) -> str:
        """Get preview text for the last message."""
        if not self.dialog.message:
            return "No messages"

        msg = self.dialog.message
        if msg.text:
            return msg.text[:50].replace("\n", " ")
        elif msg.photo:
            return "Photo"
        elif msg.video:
            return "Video"
        elif msg.voice:
            return "Voice message"
        elif msg.audio:
            return "Audio"
        elif msg.document:
            return "Document"
        elif msg.sticker:
            return "Sticker"
        else:
            return "Message"

    def _format_time(self, dt: datetime) -> str:
        """Format a datetime for display."""
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        delta = now - dt

        if delta.days == 0:
            return dt.strftime("%H:%M")
        elif delta.days == 1:
            return "Yesterday"
        elif delta.days < 7:
            return dt.strftime("%a")
        else:
            return dt.strftime("%d/%m/%y")

    def _update_accessibility(self) -> None:
        """Update accessible properties."""
        parts = [self.dialog.name or "Unknown chat"]

        if self.dialog.unread_count > 0:
            parts.append(f"{self.dialog.unread_count} unread messages")

        preview = self._get_preview_text()
        parts.append(f"Last message: {preview}")

        accessible_label = ", ".join(parts)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [accessible_label],
        )

    def update_dialog(self, dialog: Any) -> None:
        """Update the row with new dialog data."""
        self.dialog = dialog
        self._name_label.set_label(dialog.name or "Unknown")
        self._preview_label.set_label(self._get_preview_text())

        # Update unread badge
        if dialog.unread_count > 0:
            self._unread_label.set_label(str(dialog.unread_count))
            self._unread_label.set_visible(True)
        else:
            self._unread_label.set_visible(False)

        self._update_accessibility()


class MessageRow(Gtk.ListBoxRow):
    """A row displaying a single message."""

    def __init__(self, message: Any, media_manager: Any = None) -> None:
        """Initialize a message row.

        Args:
            message: The Telethon Message object.
            media_manager: Optional MediaManager for downloading media.
        """
        super().__init__()
        self.message = message
        self._media_manager = media_manager
        self._build_ui()
        self._update_accessibility()

    def _build_ui(self) -> None:
        """Build the message UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        # Reply context (if this is a reply)
        reply_widget = self._build_reply_context()
        if reply_widget:
            box.append(reply_widget)

        # Header: sender and time
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        sender_name = self._get_sender_name()
        sender_label = Gtk.Label(label=sender_name)
        sender_label.set_xalign(0)
        sender_label.add_css_class("heading")
        header.append(sender_label)

        if self.message.date:
            time_str = self.message.date.strftime("%H:%M")
            time_label = Gtk.Label(label=time_str)
            time_label.add_css_class("dim-label")
            time_label.add_css_class("caption")
            header.append(time_label)

        # Read status indicator for outgoing messages
        if self.message.out:
            self._status_label = Gtk.Label()
            self._status_label.add_css_class("dim-label")
            self._status_label.add_css_class("caption")
            self._update_read_status()
            header.append(self._status_label)
        else:
            self._status_label = None

        box.append(header)

        # Message content
        content = self._build_content()
        box.append(content)

        self.set_child(box)

    def _build_reply_context(self) -> Gtk.Widget | None:
        """Build the reply context widget if this message is a reply."""
        # Check if message has reply_to info
        if not hasattr(self.message, "reply_to") or not self.message.reply_to:
            return None

        reply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        reply_box.add_css_class("dim-label")

        # Reply icon
        reply_icon = Gtk.Image.new_from_icon_name("mail-reply-sender-symbolic")
        reply_icon.set_pixel_size(12)
        reply_box.append(reply_icon)

        # Reply info
        reply_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Try to get the reply message for context
        reply_header = "Replying to a message"
        reply_preview = ""

        # Check if we have the reply message available
        if hasattr(self.message, "reply_to_msg") and self.message.reply_to_msg:
            reply_msg = self.message.reply_to_msg
            # Get sender name
            if reply_msg.out:
                sender = "yourself"
            elif reply_msg.sender:
                if hasattr(reply_msg.sender, "first_name"):
                    sender = reply_msg.sender.first_name or "Unknown"
                elif hasattr(reply_msg.sender, "title"):
                    sender = reply_msg.sender.title or "Unknown"
                else:
                    sender = "Unknown"
            else:
                sender = "Unknown"
            reply_header = f"Replying to {sender}"

            # Get preview
            if reply_msg.text:
                reply_preview = reply_msg.text[:40]
                if len(reply_msg.text) > 40:
                    reply_preview += "..."
            elif reply_msg.voice:
                reply_preview = "Voice message"
            elif reply_msg.photo:
                reply_preview = "Photo"
            elif reply_msg.video:
                reply_preview = "Video"
            elif reply_msg.document:
                reply_preview = "Document"

        # Reply header label
        header_label = Gtk.Label(label=reply_header)
        header_label.set_xalign(0)
        header_label.add_css_class("caption")
        reply_info.append(header_label)

        # Reply preview if available
        if reply_preview:
            preview_label = Gtk.Label(label=reply_preview)
            preview_label.set_xalign(0)
            preview_label.set_ellipsize(True)
            preview_label.add_css_class("caption")
            reply_info.append(preview_label)

        reply_box.append(reply_info)

        # Store reply message ID for potential navigation
        self._reply_to_msg_id = getattr(self.message.reply_to, "reply_to_msg_id", None)

        return reply_box

    def _get_sender_name(self) -> str:
        """Get the sender's display name."""
        if self.message.out:
            return "You"
        if self.message.sender:
            if hasattr(self.message.sender, "first_name"):
                name = self.message.sender.first_name or ""
                if self.message.sender.last_name:
                    name += " " + self.message.sender.last_name
                return name or "Unknown"
            elif hasattr(self.message.sender, "title"):
                return self.message.sender.title or "Unknown"
        return "Unknown"

    def _build_content(self) -> Gtk.Widget:
        """Build the message content widget."""
        # Text message
        if self.message.text:
            label = Gtk.Label(label=self.message.text)
            label.set_xalign(0)
            label.set_wrap(True)
            label.set_wrap_mode(True)
            label.set_selectable(True)
            return label

        # Voice message
        if self.message.voice:
            return self._build_voice_widget()

        # Photo
        if self.message.photo:
            return MediaDownloadWidget(self.message, self._media_manager, "photo")

        # Video
        if self.message.video:
            return MediaDownloadWidget(self.message, self._media_manager, "video")

        # Audio
        if self.message.audio:
            return MediaDownloadWidget(self.message, self._media_manager, "audio")

        # Document
        if self.message.document:
            return MediaDownloadWidget(self.message, self._media_manager, "document")

        # Sticker
        if self.message.sticker:
            emoji = ""
            if self.message.sticker.attributes:
                for attr in self.message.sticker.attributes:
                    if hasattr(attr, "alt"):
                        emoji = attr.alt
                        break
            label = Gtk.Label(label=f"[Sticker {emoji}]")
            label.set_xalign(0)
            return label

        # Fallback
        label = Gtk.Label(label="[Message]")
        label.set_xalign(0)
        label.add_css_class("dim-label")
        return label

    def _build_voice_widget(self) -> Gtk.Widget:
        """Build a widget for voice messages."""
        return VoicePlayerWidget(self.message, self._media_manager)

    def _update_accessibility(self) -> None:
        """Update accessible properties."""
        sender = self._get_sender_name()
        time_str = self.message.date.strftime("%H:%M") if self.message.date else ""

        # Check if this is a reply
        reply_prefix = ""
        if hasattr(self.message, "reply_to") and self.message.reply_to:
            if hasattr(self.message, "reply_to_msg") and self.message.reply_to_msg:
                reply_msg = self.message.reply_to_msg
                if reply_msg.out:
                    reply_sender = "yourself"
                elif reply_msg.sender and hasattr(reply_msg.sender, "first_name"):
                    reply_sender = reply_msg.sender.first_name or "someone"
                else:
                    reply_sender = "someone"
                reply_prefix = f"Replying to {reply_sender}: "
            else:
                reply_prefix = "Reply: "

        if self.message.text:
            content = self.message.text
        elif self.message.voice:
            content = "Voice message"
        elif self.message.photo:
            content = "Photo"
        elif self.message.video:
            content = "Video"
        elif self.message.document:
            content = "Document"
        elif self.message.sticker:
            content = "Sticker"
        else:
            content = "Message"

        # Add read status for outgoing messages
        status_suffix = ""
        if self.message.out:
            is_read = getattr(self, "_is_read", False)
            status_suffix = ", seen" if is_read else ", sent"

        accessible_label = f"{sender}, {time_str}: {reply_prefix}{content}{status_suffix}"
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [accessible_label],
        )

    def _update_read_status(self) -> None:
        """Update the read status indicator."""
        if not self._status_label or not self.message.out:
            return

        # Check if message has been read
        # For private chats, we track this via the _is_read attribute we set
        is_read = getattr(self, "_is_read", False)

        if is_read:
            self._status_label.set_label("✓✓")  # Double checkmark for read
            self._status_label.set_tooltip_text("Seen")
        else:
            self._status_label.set_label("✓")  # Single checkmark for sent
            self._status_label.set_tooltip_text("Sent")

    def mark_as_read(self) -> None:
        """Mark this message as read by the recipient."""
        if self.message.out:
            self._is_read = True
            self._update_read_status()
            self._update_accessibility()

    @property
    def is_read(self) -> bool:
        """Check if message has been read."""
        return getattr(self, "_is_read", False)


class MainWindow(Gtk.ApplicationWindow):
    """Main application window with chat list and message view."""

    def __init__(
        self,
        application: Gtk.Application,
        client: AccessGramClient,
        config: Config,
        user_name: str,
    ) -> None:
        """Initialize the main window.

        Args:
            application: The GTK application.
            client: The Telegram client.
            config: Application configuration.
            user_name: Current user's name for display.
        """
        super().__init__(
            application=application,
            title=f"AccessGram - {user_name}",
            default_width=900,
            default_height=600,
        )

        self._client = client
        self._config = config
        self._user_name = user_name
        self._current_dialog = None
        self._dialogs: list[Any] = []
        self._dialog_rows: dict[int, ChatRow] = {}
        self._message_rows: dict[int, MessageRow] = {}  # Track message rows by ID
        self._muted_chats: set[int] = set()  # Track muted chat IDs locally
        self._reply_to_message: Any = None  # Message being replied to
        self._action_target_dialog: Any = None  # Target dialog for context menu actions

        # Media manager for downloads/uploads
        self._media_manager = MediaManager(client)

        # Screen reader announcer
        self._announcer = ScreenReaderAnnouncer(self)

        self._build_ui()
        self._setup_shortcuts()
        self._setup_event_handlers()

        # Set up accessibility
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"AccessGram main window, logged in as {user_name}"],
        )

    def _build_ui(self) -> None:
        """Build the main window UI."""
        # Header bar
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Main menu"],
        )

        # Create menu
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        # Search button
        search_button = Gtk.Button()
        search_button.set_icon_name("system-search-symbolic")
        search_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Search for people, groups, and channels"],
        )
        search_button.connect("clicked", self._on_search_clicked)
        header.pack_start(search_button)

        # Main content: Paned view
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(300)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)

        # Left pane: Chat list
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Chat filter entry
        self._chat_filter = Gtk.SearchEntry()
        self._chat_filter.set_placeholder_text("Filter chats...")
        self._chat_filter.set_margin_start(8)
        self._chat_filter.set_margin_end(8)
        self._chat_filter.set_margin_top(8)
        self._chat_filter.set_margin_bottom(8)
        self._chat_filter.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Filter conversations"],
        )
        self._chat_filter.connect("search-changed", self._on_filter_changed)
        left_box.append(self._chat_filter)

        # Chat list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._chat_listbox = Gtk.ListBox()
        self._chat_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._chat_listbox.set_activate_on_single_click(True)
        self._chat_listbox.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Conversations list"],
        )
        self._chat_listbox.connect("row-activated", self._on_chat_activated)
        self._setup_list_tab_behavior(self._chat_listbox, self._get_chat_list_tab_targets)
        self._setup_chat_context_menu()
        scrolled.set_child(self._chat_listbox)
        left_box.append(scrolled)

        paned.set_start_child(left_box)

        # Right pane: Chat view
        self._right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Placeholder when no chat selected
        self._placeholder = Gtk.Label(label="Select a chat to start messaging")
        self._placeholder.set_vexpand(True)
        self._placeholder.add_css_class("dim-label")
        self._right_box.append(self._placeholder)

        # Chat view (initially hidden)
        self._chat_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._chat_view.set_visible(False)
        self._chat_view.set_vexpand(True)

        # Chat header
        chat_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chat_header.set_margin_start(12)
        chat_header.set_margin_end(12)
        chat_header.set_margin_top(8)
        chat_header.set_margin_bottom(8)

        self._chat_title = Gtk.Label()
        self._chat_title.set_xalign(0)
        self._chat_title.set_hexpand(True)
        self._chat_title.add_css_class("title-2")
        chat_header.append(self._chat_title)

        self._chat_view.append(chat_header)

        # Messages list
        msg_scrolled = Gtk.ScrolledWindow()
        msg_scrolled.set_vexpand(True)
        msg_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._messages_listbox = Gtk.ListBox()
        self._messages_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._messages_listbox.set_activate_on_single_click(True)
        self._messages_listbox.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Messages - press Enter to reply"],
        )
        self._messages_listbox.connect("row-activated", self._on_message_activated)
        self._setup_list_tab_behavior(self._messages_listbox, self._get_messages_list_tab_targets)
        msg_scrolled.set_child(self._messages_listbox)
        self._chat_view.append(msg_scrolled)

        # Reply indicator (hidden by default)
        self._reply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._reply_box.set_margin_start(12)
        self._reply_box.set_margin_end(12)
        self._reply_box.set_margin_top(8)
        self._reply_box.set_visible(False)

        reply_icon = Gtk.Image.new_from_icon_name("mail-reply-sender-symbolic")
        self._reply_box.append(reply_icon)

        reply_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        reply_info.set_hexpand(True)

        self._reply_to_label = Gtk.Label(label="Replying to")
        self._reply_to_label.set_xalign(0)
        self._reply_to_label.add_css_class("dim-label")
        self._reply_to_label.add_css_class("caption")
        reply_info.append(self._reply_to_label)

        self._reply_preview_label = Gtk.Label()
        self._reply_preview_label.set_xalign(0)
        self._reply_preview_label.set_ellipsize(True)
        reply_info.append(self._reply_preview_label)

        self._reply_box.append(reply_info)

        # Cancel reply button
        cancel_reply_button = Gtk.Button()
        cancel_reply_button.set_icon_name("window-close-symbolic")
        cancel_reply_button.add_css_class("flat")
        cancel_reply_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Cancel reply"],
        )
        cancel_reply_button.connect("clicked", self._on_cancel_reply)
        self._reply_box.append(cancel_reply_button)

        self._chat_view.append(self._reply_box)

        # Compose area
        compose_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        compose_box.set_margin_start(12)
        compose_box.set_margin_end(12)
        compose_box.set_margin_top(8)
        compose_box.set_margin_bottom(12)

        # Attach button
        self._attach_button = Gtk.Button()
        self._attach_button.set_icon_name("mail-attachment-symbolic")
        self._attach_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Attach file"],
        )
        self._attach_button.connect("clicked", self._on_attach_clicked)
        compose_box.append(self._attach_button)

        # Message entry
        self._message_entry = Gtk.Entry()
        self._message_entry.set_placeholder_text("Type a message...")
        self._message_entry.set_hexpand(True)
        self._message_entry.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Message input"],
        )
        self._message_entry.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            ["Type your message here and press Enter to send"],
        )
        self._message_entry.connect("activate", self._on_send_message)
        compose_box.append(self._message_entry)

        # Voice recorder widget
        self._voice_recorder = VoiceRecorderWidget(
            on_recording_complete=self._on_voice_recording_complete,
            on_recording_cancelled=self._on_voice_recording_cancelled,
        )
        compose_box.append(self._voice_recorder)

        # Send button
        send_button = Gtk.Button()
        send_button.set_icon_name("document-send-symbolic")
        send_button.add_css_class("suggested-action")
        send_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Send message"],
        )
        send_button.connect("clicked", self._on_send_message)
        compose_box.append(send_button)

        self._chat_view.append(compose_box)
        self._right_box.append(self._chat_view)

        paned.set_end_child(self._right_box)
        self.set_child(paned)

        # Set up window actions
        self._setup_actions()

    def _setup_actions(self) -> None:
        """Set up window-level actions."""
        # Mute chat action
        mute_action = Gio.SimpleAction.new("mute-chat", None)
        mute_action.connect("activate", self._on_mute_chat)
        self.add_action(mute_action)

        # Unmute chat action
        unmute_action = Gio.SimpleAction.new("unmute-chat", None)
        unmute_action.connect("activate", self._on_unmute_chat)
        self.add_action(unmute_action)

        # Leave chat action
        leave_action = Gio.SimpleAction.new("leave-chat", None)
        leave_action.connect("activate", self._on_leave_chat)
        self.add_action(leave_action)

        # Delete chat action
        delete_action = Gio.SimpleAction.new("delete-chat", None)
        delete_action.connect("activate", self._on_delete_chat)
        self.add_action(delete_action)

    def _setup_list_tab_behavior(
        self,
        listbox: Gtk.ListBox,
        get_targets: callable,
    ) -> None:
        """Set up Tab key behavior for a listbox.

        Makes Tab/Shift+Tab move focus out of the list instead of
        cycling through individual items. Arrow keys still navigate items.

        Args:
            listbox: The listbox to configure.
            get_targets: Callable returning (next_widget, prev_widget) for Tab targets.
        """
        controller = Gtk.EventControllerKey()

        def on_key_pressed(ctrl, keyval, keycode, state):
            from gi.repository import Gdk

            # Shift+Tab sends ISO_Left_Tab, regular Tab sends KEY_Tab
            if keyval == Gdk.KEY_ISO_Left_Tab:
                next_widget, prev_widget = get_targets()
                if prev_widget:
                    prev_widget.grab_focus()
                    return True
            elif keyval == Gdk.KEY_Tab:
                next_widget, prev_widget = get_targets()
                if next_widget:
                    next_widget.grab_focus()
                    return True

            return False

        controller.connect("key-pressed", on_key_pressed)
        listbox.add_controller(controller)

    def _get_chat_list_tab_targets(self) -> tuple[Gtk.Widget | None, Gtk.Widget | None]:
        """Get Tab navigation targets for the chat list.

        Returns:
            Tuple of (next_widget, prev_widget).
        """
        # Tab forward goes to messages list (if visible) or message entry
        if self._chat_view.get_visible():
            next_widget = self._messages_listbox
        else:
            next_widget = self._chat_filter

        # Tab backward goes to filter
        prev_widget = self._chat_filter

        return next_widget, prev_widget

    def _get_messages_list_tab_targets(self) -> tuple[Gtk.Widget | None, Gtk.Widget | None]:
        """Get Tab navigation targets for the messages list.

        Returns:
            Tuple of (next_widget, prev_widget).
        """
        # Tab forward goes to attach button
        next_widget = self._attach_button

        # Tab backward goes to chat list
        prev_widget = self._chat_listbox

        return next_widget, prev_widget

    def _setup_chat_context_menu(self) -> None:
        """Set up context menu for chat list items."""
        from gi.repository import Gdk

        # Track which dialog the context menu is targeting
        self._context_menu_dialog = None
        self._chat_context_menu = None

        # Create the menu model (shared across all context menu instances)
        self._chat_context_menu_model = Gio.Menu()
        self._chat_context_menu_model.append("Mute chat", "win.mute-chat")
        self._chat_context_menu_model.append("Unmute chat", "win.unmute-chat")
        self._chat_context_menu_model.append("Leave chat", "win.leave-chat")
        self._chat_context_menu_model.append("Delete chat", "win.delete-chat")

        # Right-click gesture
        click_gesture = Gtk.GestureClick()
        click_gesture.set_button(Gdk.BUTTON_SECONDARY)
        click_gesture.connect("pressed", self._on_chat_context_menu_click)
        self._chat_listbox.add_controller(click_gesture)

        # Keyboard controller for F10 and Menu key
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_chat_context_menu_key)
        self._chat_listbox.add_controller(key_controller)

    def _show_chat_context_menu(self, row: Gtk.ListBoxRow) -> None:
        """Show context menu for a chat row."""
        if not hasattr(row, "dialog"):
            return

        # Store the target dialog for actions
        self._context_menu_dialog = row.dialog

        # Clean up previous popover if it exists
        if self._chat_context_menu is not None:
            self._chat_context_menu.unparent()

        # Create new popover parented to this row
        self._chat_context_menu = Gtk.PopoverMenu.new_from_model(
            self._chat_context_menu_model
        )
        self._chat_context_menu.set_parent(row)
        self._chat_context_menu.set_has_arrow(False)
        self._chat_context_menu.connect("closed", self._on_context_menu_closed)
        self._chat_context_menu.popup()

    def _on_context_menu_closed(self, popover: Gtk.PopoverMenu) -> None:
        """Clear context menu target when menu closes."""
        self._context_menu_dialog = None

    def _on_chat_context_menu_click(
        self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float
    ) -> None:
        """Handle right-click on chat list."""
        row = self._chat_listbox.get_row_at_y(int(y))
        if row is not None:
            self._show_chat_context_menu(row)

    def _on_chat_context_menu_key(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> bool:
        """Handle keyboard shortcuts for context menu (F10, Menu key)."""
        from gi.repository import Gdk

        if keyval in (Gdk.KEY_F10, Gdk.KEY_Menu):
            row = self._chat_listbox.get_selected_row()
            if row is not None:
                self._show_chat_context_menu(row)
                return True
        return False

    def _get_context_menu_target(self) -> Any:
        """Get the dialog that context menu actions should target.

        Returns the context menu target if set, otherwise the current dialog.
        """
        return self._context_menu_dialog or self._current_dialog

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        controller = Gtk.ShortcutController()
        self.add_controller(controller)

        # Ctrl+N: New chat / search
        controller.add_shortcut(
            Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string("<Control>n"),
                action=Gtk.CallbackAction.new(lambda *args: self._on_search_clicked(None)),
            )
        )

        # Ctrl+F: Focus filter
        controller.add_shortcut(
            Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string("<Control>f"),
                action=Gtk.CallbackAction.new(lambda *args: self._chat_filter.grab_focus()),
            )
        )

        # Escape: Clear selection / back to chat list
        controller.add_shortcut(
            Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
                action=Gtk.CallbackAction.new(self._on_escape),
            )
        )

    def _setup_event_handlers(self) -> None:
        """Set up Telegram event handlers."""
        self._client.on_new_message(self._on_new_message_event)
        self._client.on_message_read(self._on_message_read_event)

    def _on_escape(self, *args) -> bool:
        """Handle Escape key."""
        if self._chat_filter.has_focus():
            self._chat_filter.set_text("")
            self._chat_listbox.grab_focus()
        elif self._message_entry.has_focus():
            self._chat_listbox.grab_focus()
        return True

    # =========================================================================
    # Dialog Loading
    # =========================================================================

    async def load_dialogs(self) -> None:
        """Load the chat list."""
        logger.info("Loading dialogs...")
        self._dialogs = await self._client.get_dialogs(limit=None)

        # Clear existing rows
        while True:
            row = self._chat_listbox.get_first_child()
            if row is None:
                break
            self._chat_listbox.remove(row)
        self._dialog_rows.clear()

        # Add dialog rows
        for dialog in self._dialogs:
            row = ChatRow(dialog)
            self._chat_listbox.append(row)
            self._dialog_rows[dialog.id] = row

        logger.info("Loaded %d dialogs", len(self._dialogs))
        self._announcer.announce(f"Loaded {len(self._dialogs)} conversations")

    def _on_filter_changed(self, entry: Gtk.SearchEntry) -> None:
        """Handle chat filter text change."""
        filter_text = entry.get_text().lower()

        for dialog in self._dialogs:
            row = self._dialog_rows.get(dialog.id)
            if row:
                name = dialog.name or ""
                visible = filter_text in name.lower()
                row.set_visible(visible)

    def _move_dialog_to_top(self, dialog_id: int) -> None:
        """Move a dialog to the top of the chat list."""
        row = self._dialog_rows.get(dialog_id)
        if not row:
            return

        # Check if already at top
        first_row = self._chat_listbox.get_row_at_index(0)
        if first_row == row:
            return  # Already at top, nothing to do

        # Find the dialog in our list and move it to front
        for i, dialog in enumerate(self._dialogs):
            if dialog.id == dialog_id:
                # Move to front of list
                self._dialogs.insert(0, self._dialogs.pop(i))
                break

        # Make row non-selectable and non-focusable during move to prevent
        # accessibility announcements
        row.set_selectable(False)
        row.set_can_focus(False)

        # Remove and re-insert the row at the top
        self._chat_listbox.remove(row)
        self._chat_listbox.prepend(row)

        # Restore selectability
        row.set_selectable(True)
        row.set_can_focus(True)

    # =========================================================================
    # Chat Selection
    # =========================================================================

    def _on_chat_activated(self, listbox: Gtk.ListBox, row: ChatRow) -> None:
        """Handle chat selection."""
        self._current_dialog = row.dialog
        self._show_chat_view()
        run_async(self._load_messages())

    def _show_chat_view(self) -> None:
        """Show the chat view and hide placeholder."""
        self._placeholder.set_visible(False)
        self._chat_view.set_visible(True)

        if self._current_dialog:
            self._chat_title.set_label(self._current_dialog.name or "Chat")
            self._messages_listbox.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [f"Messages in {self._current_dialog.name}"],
            )

    async def _load_messages(self) -> None:
        """Load messages for current chat."""
        if not self._current_dialog:
            return

        chat_name = self._current_dialog.name

        try:
            # Clear existing messages
            while True:
                row = self._messages_listbox.get_first_child()
                if row is None:
                    break
                self._messages_listbox.remove(row)
            self._message_rows.clear()

            # Load messages (newest first, then reverse for display)
            messages = await self._client.get_messages(
                self._current_dialog.entity,
                limit=self._config.max_messages_to_load,
            )

            # Get the read_outbox_max_id to determine which outgoing messages have been read
            read_outbox_max_id = getattr(self._current_dialog.dialog, "read_outbox_max_id", 0)

            # Add in chronological order (oldest first)
            for message in reversed(messages):
                if message.text or message.media:
                    row = MessageRow(message, self._media_manager)
                    self._messages_listbox.append(row)
                    # Track outgoing message rows for read status updates
                    if message.out and message.id:
                        self._message_rows[message.id] = row
                        # Mark as read if already seen by recipient
                        if message.id <= read_outbox_max_id:
                            row.mark_as_read()

            # Mark messages as read
            try:
                await self._client.mark_read(self._current_dialog.entity)
            except Exception as e:
                logger.debug("Could not mark messages as read: %s", e)

            # Update the unread count in the chat list
            if self._current_dialog.unread_count > 0:
                self._current_dialog.unread_count = 0
                row = self._dialog_rows.get(self._current_dialog.id)
                if row:
                    row.update_dialog(self._current_dialog)

        except Exception as e:
            logger.exception("Error loading messages: %s", e)

        finally:
            # Always focus message entry and announce (must be on main thread)
            def focus_and_announce():
                self._message_entry.grab_focus()
                self._announcer.announce(f"Opened chat with {chat_name}")
                return False
            GLib.idle_add(focus_and_announce)

    # =========================================================================
    # Reply Handling
    # =========================================================================

    def _on_message_activated(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        """Handle message row activation - set as reply target."""
        if not isinstance(row, MessageRow):
            return

        message = row.message
        self._reply_to_message = message

        # Update reply indicator
        sender = self._get_message_sender_name(message)
        self._reply_to_label.set_label(f"Replying to {sender}")

        # Set preview text
        if message.text:
            preview = message.text[:60]
            if len(message.text) > 60:
                preview += "..."
        elif message.voice:
            preview = "Voice message"
        elif message.photo:
            preview = "Photo"
        elif message.video:
            preview = "Video"
        elif message.document:
            preview = "Document"
        else:
            preview = "Message"
        self._reply_preview_label.set_label(preview)

        # Show reply indicator
        self._reply_box.set_visible(True)

        # Focus message entry
        self._message_entry.grab_focus()
        self._announcer.announce(f"Replying to {sender}")

    def _on_cancel_reply(self, button: Gtk.Button) -> None:
        """Cancel replying to a message."""
        self._clear_reply()
        self._announcer.announce("Reply cancelled")
        self._message_entry.grab_focus()

    def _clear_reply(self) -> None:
        """Clear the reply state."""
        self._reply_to_message = None
        self._reply_box.set_visible(False)
        self._reply_to_label.set_label("Replying to")
        self._reply_preview_label.set_label("")

    def _get_message_sender_name(self, message: Any) -> str:
        """Get the sender name for a message."""
        if message.out:
            return "yourself"
        if message.sender:
            if hasattr(message.sender, "first_name"):
                name = message.sender.first_name or ""
                if message.sender.last_name:
                    name += " " + message.sender.last_name
                return name or "Unknown"
            elif hasattr(message.sender, "title"):
                return message.sender.title or "Unknown"
        return "Unknown"

    # =========================================================================
    # Message Sending
    # =========================================================================

    def _on_send_message(self, widget: Gtk.Widget) -> None:
        """Handle send message action."""
        text = self._message_entry.get_text().strip()
        if not text or not self._current_dialog:
            return

        self._message_entry.set_text("")
        self._message_entry.set_sensitive(False)

        # Get reply_to message ID if replying
        reply_to = self._reply_to_message.id if self._reply_to_message else None

        create_task_with_callback(
            self._send_message_async(self._current_dialog.entity, text, reply_to),
            self._on_message_sent,
            self._on_message_error,
        )

    async def _send_message_async(self, entity: Any, text: str, reply_to: int | None) -> Any:
        """Send a message with optional reply."""
        if reply_to:
            return await self._client._client.send_message(entity, text, reply_to=reply_to)
        else:
            return await self._client.send_message(entity, text)

    def _on_message_sent(self, message: Any) -> None:
        """Handle successful message send."""
        self._message_entry.set_sensitive(True)
        self._message_entry.grab_focus()

        # If this was a reply, attach the reply message before clearing
        if self._reply_to_message:
            message.reply_to_msg = self._reply_to_message

        # Clear reply state
        self._clear_reply()

        # Add message to list
        row = MessageRow(message, self._media_manager)
        self._messages_listbox.append(row)

        # Update the dialog in the chat list
        if self._current_dialog:
            self._current_dialog.message = message
            dialog_row = self._dialog_rows.get(self._current_dialog.id)
            if dialog_row:
                dialog_row.update_dialog(self._current_dialog)

            # Move dialog to top of list
            self._move_dialog_to_top(self._current_dialog.id)

        if self._config.announce_sent_messages:
            self._announcer.announce("Message sent")

    def _on_message_error(self, error: Exception) -> None:
        """Handle message send error."""
        self._message_entry.set_sensitive(True)
        self._announcer.announce(f"Failed to send message: {error}")
        logger.exception("Failed to send message: %s", error)

    # =========================================================================
    # Event Handlers
    # =========================================================================

    def _on_new_message_event(self, event) -> None:
        """Handle incoming message event."""
        message = event.message
        chat_id = event.chat_id

        # Check if this is the currently open chat
        is_current_chat = self._current_dialog and self._current_dialog.id == chat_id

        # Update dialog in list
        def update_dialog_list():
            for dialog in self._dialogs:
                if dialog.id == chat_id:
                    # Update last message
                    dialog.message = message

                    # Increment unread count if not current chat and not our own message
                    if not is_current_chat and not message.out:
                        dialog.unread_count = getattr(dialog, 'unread_count', 0) + 1

                    # Update the row
                    row = self._dialog_rows.get(dialog.id)
                    if row:
                        row.update_dialog(dialog)

                    # Move to top of list
                    self._move_dialog_to_top(chat_id)
                    break
            return False  # Don't repeat

        GLib.idle_add(update_dialog_list)

        # Add to message view if current chat
        if is_current_chat:
            # Fetch sender and reply message, then add to view
            run_async(self._prepare_and_add_message(message, chat_id))
            # Mark as read since we're viewing this chat
            if not message.out:
                run_async(self._client.mark_read(self._current_dialog.entity))

    async def _prepare_and_add_message(self, message: Any, chat_id: int) -> None:
        """Fetch sender and reply message, then add the message row."""
        # Fetch sender if not available
        if not message.sender:
            try:
                sender = await message.get_sender()
                if sender:
                    message._sender = sender
            except Exception as e:
                logger.debug("Could not fetch sender: %s", e)

        # Fetch reply message if this is a reply
        if message.reply_to:
            try:
                reply_msg = await message.get_reply_message()
                if reply_msg:
                    message.reply_to_msg = reply_msg
            except Exception as e:
                logger.debug("Could not fetch reply message: %s", e)

        GLib.idle_add(self._add_message_row, message)

        # Announce after adding (so sender info is available)
        self._announce_new_message(message, chat_id)

    def _announce_new_message(self, message: Any, chat_id: int) -> None:
        """Announce a new message to the screen reader."""
        is_muted = chat_id in self._muted_chats
        if self._config.announce_new_messages and not message.out and not is_muted:
            sender = "Unknown"
            if message.sender:
                if hasattr(message.sender, "first_name"):
                    sender = message.sender.first_name or "Unknown"
                elif hasattr(message.sender, "title"):
                    sender = message.sender.title or "Unknown"

            preview = message.text[:50] if message.text else "Media"

            def announce(s=sender, p=preview):
                self._announcer.announce(f"New message from {s}: {p}")
                return False

            GLib.idle_add(announce)

    def _add_message_row(self, message: Any) -> bool:
        """Add a message row (called from main thread)."""
        if message.text or message.media:
            row = MessageRow(message, self._media_manager)
            self._messages_listbox.append(row)
            # Track outgoing message rows for read status updates
            if message.out and message.id:
                self._message_rows[message.id] = row
        return False  # Don't repeat

    def _on_message_read_event(self, event) -> None:
        """Handle message read event."""
        # event.max_id contains the ID of the last read message
        # All messages with ID <= max_id have been read
        max_id = event.max_id
        chat_id = event.chat_id

        # Only process if this is for the current chat
        if not self._current_dialog or self._current_dialog.id != chat_id:
            return

        # Update read status for all outgoing messages up to max_id
        def update_read_status():
            for msg_id, row in list(self._message_rows.items()):
                if msg_id <= max_id and row.message.out and not row.is_read:
                    row.mark_as_read()
            return False

        GLib.idle_add(update_read_status)

    # =========================================================================
    # Actions
    # =========================================================================

    def _on_search_clicked(self, button: Gtk.Button | None) -> None:
        """Open search dialog."""
        dialog = SearchDialog(
            parent=self,
            client=self._client,
            on_select=self._on_search_select,
        )
        dialog.present()

    def _on_search_select(self, entity: Any) -> None:
        """Handle selection from search dialog."""
        # Check if we already have a dialog with this entity
        entity_id = getattr(entity, "id", None)
        if entity_id:
            for dialog in self._dialogs:
                if dialog.entity.id == entity_id:
                    # Select the existing dialog
                    row = self._dialog_rows.get(dialog.id)
                    if row:
                        self._chat_listbox.select_row(row)
                        self._on_chat_activated(self._chat_listbox, row)
                    return

        # Start a new conversation
        self._announcer.announce(f"Starting conversation with {self._get_entity_name(entity)}")
        create_task_with_callback(
            self._start_conversation(entity),
            lambda _: None,
            self._on_start_conversation_error,
        )

    async def _start_conversation(self, entity: Any) -> None:
        """Start a new conversation with an entity."""
        # Open the chat view for this entity directly
        # Create a fake dialog-like object for UI purposes
        class PseudoDialog:
            def __init__(self, ent):
                self.entity = ent
                self.id = getattr(ent, "id", 0)
                self.name = self._get_name(ent)
                self.message = None
                self.unread_count = 0

            def _get_name(self, ent):
                if hasattr(ent, "first_name"):
                    name = ent.first_name or ""
                    if ent.last_name:
                        name += " " + ent.last_name
                    return name or "Unknown"
                elif hasattr(ent, "title"):
                    return ent.title or "Unknown"
                return "Unknown"

        pseudo_dialog = PseudoDialog(entity)

        # Set this as current dialog and show the chat view
        self._current_dialog = pseudo_dialog

        # Show chat view
        self._placeholder.set_visible(False)
        self._chat_view.set_visible(True)
        self._chat_title.set_label(pseudo_dialog.name)
        self._chat_title.add_css_class("heading")

        # Clear existing messages
        while True:
            row = self._messages_listbox.get_first_child()
            if row is None:
                break
            self._messages_listbox.remove(row)

        # Try to load any existing messages
        messages = await self._client.get_messages(entity, limit=self._config.max_messages_to_load)

        for message in reversed(messages):
            if message.text or message.media:
                row = MessageRow(message, self._media_manager)
                self._messages_listbox.append(row)

        # Focus message entry
        self._message_entry.grab_focus()
        self._announcer.announce(f"Opened chat with {pseudo_dialog.name}")

    def _on_start_conversation_error(self, error: Exception) -> None:
        """Handle error starting conversation."""
        self._announcer.announce(f"Failed to start conversation: {error}")
        logger.exception("Failed to start conversation: %s", error)

    def _get_entity_name(self, entity: Any) -> str:
        """Get display name for an entity."""
        if hasattr(entity, "first_name"):
            name = entity.first_name or ""
            if entity.last_name:
                name += " " + entity.last_name
            return name or "Unknown"
        elif hasattr(entity, "title"):
            return entity.title or "Unknown"
        return "Unknown"

    def _on_attach_clicked(self, button: Gtk.Button) -> None:
        """Open file chooser for attachment."""
        if not self._current_dialog:
            self._announcer.announce("No chat selected")
            return

        # Create file dialog
        dialog = Gtk.FileDialog()
        dialog.set_title("Select file to send")
        dialog.set_modal(True)

        # Open file chooser
        dialog.open(self, None, self._on_file_selected)

    def _on_file_selected(self, dialog: Gtk.FileDialog, result: Any) -> None:
        """Handle file selection from dialog."""
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = Path(file.get_path())
                self._send_file(file_path)
        except GLib.Error as e:
            # User cancelled or error
            if e.code != 2:  # Not "cancelled" error
                logger.error("File dialog error: %s", e)

    def _send_file(self, file_path: Path) -> None:
        """Send a file to the current chat."""
        if not self._current_dialog:
            return

        filename = file_path.name
        self._announcer.announce(f"Sending {filename}")

        create_task_with_callback(
            self._media_manager.upload_file(
                self._current_dialog.entity,
                file_path,
                progress_callback=self._on_upload_progress,
            ),
            self._on_file_sent,
            self._on_file_send_error,
        )

    def _on_upload_progress(self, current: int, total: int) -> None:
        """Handle upload progress."""
        # Could show a progress indicator in the UI
        if total > 0:
            percent = int((current / total) * 100)
            if percent % 25 == 0:  # Announce at 25%, 50%, 75%, 100%
                logger.debug("Upload progress: %d%%", percent)

    def _on_file_sent(self, message: Any) -> None:
        """Handle successful file send."""
        # Add message to list
        row = MessageRow(message, self._media_manager)
        self._messages_listbox.append(row)

        # Update the dialog in the chat list
        if self._current_dialog:
            self._current_dialog.message = message
            dialog_row = self._dialog_rows.get(self._current_dialog.id)
            if dialog_row:
                dialog_row.update_dialog(self._current_dialog)
            self._move_dialog_to_top(self._current_dialog.id)

        self._announcer.announce("File sent")
        self._message_entry.grab_focus()

    def _on_file_send_error(self, error: Exception) -> None:
        """Handle file send error."""
        self._announcer.announce(f"Failed to send file: {error}")
        logger.exception("Failed to send file: %s", error)

    def _on_voice_recording_complete(self, voice_path: Path) -> None:
        """Handle completed voice recording."""
        if not self._current_dialog:
            self._announcer.announce("No chat selected")
            return

        self._announcer.announce("Sending voice message")

        create_task_with_callback(
            self._client.send_file(
                self._current_dialog.entity,
                voice_path,
                voice_note=True,
            ),
            self._on_voice_sent,
            self._on_voice_send_error,
        )

    def _on_voice_recording_cancelled(self) -> None:
        """Handle cancelled voice recording."""
        self._announcer.announce("Voice recording cancelled")
        self._message_entry.grab_focus()

    def _on_voice_sent(self, message: Any) -> None:
        """Handle successful voice message send."""
        # Add message to list
        row = MessageRow(message, self._media_manager)
        self._messages_listbox.append(row)

        # Update the dialog in the chat list
        if self._current_dialog:
            self._current_dialog.message = message
            dialog_row = self._dialog_rows.get(self._current_dialog.id)
            if dialog_row:
                dialog_row.update_dialog(self._current_dialog)
            self._move_dialog_to_top(self._current_dialog.id)

        self._announcer.announce("Voice message sent")
        self._message_entry.grab_focus()

    def _on_voice_send_error(self, error: Exception) -> None:
        """Handle voice message send error."""
        self._announcer.announce(f"Failed to send voice message: {error}")
        logger.exception("Failed to send voice message: %s", error)

    def _on_mute_chat(self, action: Gio.SimpleAction, param: None) -> None:
        """Mute the target chat."""
        target = self._get_context_menu_target()
        if not target:
            return

        chat_name = target.name or "this chat"
        chat_id = target.id
        create_task_with_callback(
            self._client.mute_chat(target.entity, mute=True),
            lambda success: self._on_mute_complete(success, chat_name, chat_id, True),
            lambda error: self._on_mute_error(error, True),
        )

    def _on_unmute_chat(self, action: Gio.SimpleAction, param: None) -> None:
        """Unmute the target chat."""
        target = self._get_context_menu_target()
        if not target:
            return

        chat_name = target.name or "this chat"
        chat_id = target.id
        create_task_with_callback(
            self._client.mute_chat(target.entity, mute=False),
            lambda success: self._on_mute_complete(success, chat_name, chat_id, False),
            lambda error: self._on_mute_error(error, False),
        )

    def _on_mute_complete(self, success: bool, chat_name: str, chat_id: int, muted: bool) -> None:
        """Handle mute/unmute completion."""
        if success:
            if muted:
                self._muted_chats.add(chat_id)
            else:
                self._muted_chats.discard(chat_id)

            action = "muted" if muted else "unmuted"
            self._announcer.announce(f"{chat_name} {action}")
        else:
            action = "mute" if muted else "unmute"
            self._announcer.announce(f"Failed to {action} {chat_name}")

    def _on_mute_error(self, error: Exception, muting: bool) -> None:
        """Handle mute/unmute error."""
        action = "mute" if muting else "unmute"
        self._announcer.announce(f"Failed to {action} chat: {error}")
        logger.exception("Failed to %s chat: %s", action, error)

    def _on_leave_chat(self, action: Gio.SimpleAction, param: None) -> None:
        """Leave target chat (group/channel)."""
        target = self._get_context_menu_target()
        if not target:
            return

        # Store target for use in confirmation callback
        self._action_target_dialog = target
        chat_name = target.name or "this chat"

        # Create confirmation dialog
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"Leave {chat_name}?")
        dialog.set_detail("You will no longer receive messages from this group or channel.")
        dialog.set_buttons(["Cancel", "Leave"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)

        dialog.choose(self, None, self._on_leave_chat_response)

    def _on_leave_chat_response(self, dialog: Gtk.AlertDialog, result: Any) -> None:
        """Handle leave chat confirmation response."""
        try:
            response = dialog.choose_finish(result)
            if response == 1:  # "Leave" button
                self._do_leave_chat()
        except GLib.Error:
            self._action_target_dialog = None  # Clear on cancel

    def _do_leave_chat(self) -> None:
        """Perform the leave chat action."""
        target = self._action_target_dialog
        if not target:
            return

        chat_name = target.name or "chat"
        self._announcer.announce(f"Leaving {chat_name}")

        create_task_with_callback(
            self._client.delete_dialog(target.entity, revoke=False),
            lambda _: self._on_chat_left(target),
            self._on_leave_chat_error,
        )

    def _on_chat_left(self, target: Any) -> None:
        """Handle successful leave."""
        chat_name = target.name if target else "chat"
        dialog_id = target.id

        # Remove from dialogs list
        self._dialogs = [d for d in self._dialogs if d.id != dialog_id]

        # Remove from UI
        row = self._dialog_rows.get(dialog_id)
        if row:
            self._chat_listbox.remove(row)
            del self._dialog_rows[dialog_id]

        # Clear current chat view if this was the open chat
        if self._current_dialog and self._current_dialog.id == dialog_id:
            self._current_dialog = None
            self._placeholder.set_visible(True)
            self._chat_view.set_visible(False)

            # Clear messages
            while True:
                row = self._messages_listbox.get_first_child()
                if row is None:
                    break
                self._messages_listbox.remove(row)

        self._action_target_dialog = None
        self._announcer.announce(f"Left {chat_name}")
        self._chat_listbox.grab_focus()

    def _on_leave_chat_error(self, error: Exception) -> None:
        """Handle leave chat error."""
        self._announcer.announce(f"Failed to leave chat: {error}")
        logger.exception("Failed to leave chat: %s", error)

    def _on_delete_chat(self, action: Gio.SimpleAction, param: None) -> None:
        """Delete target chat (private conversation)."""
        target = self._get_context_menu_target()
        if not target:
            return

        # Store target for use in confirmation callback
        self._action_target_dialog = target
        chat_name = target.name or "this chat"

        # Create confirmation dialog
        dialog = Gtk.AlertDialog()
        dialog.set_message(f"Delete conversation with {chat_name}?")
        dialog.set_detail("This will delete the chat history. This action cannot be undone.")
        dialog.set_buttons(["Cancel", "Delete"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)

        dialog.choose(self, None, self._on_delete_chat_response)

    def _on_delete_chat_response(self, dialog: Gtk.AlertDialog, result: Any) -> None:
        """Handle delete chat confirmation response."""
        try:
            response = dialog.choose_finish(result)
            if response == 1:  # "Delete" button
                self._do_delete_chat()
        except GLib.Error:
            self._action_target_dialog = None  # Clear on cancel

    def _do_delete_chat(self) -> None:
        """Perform the delete chat action."""
        target = self._action_target_dialog
        if not target:
            return

        chat_name = target.name or "chat"
        self._announcer.announce(f"Deleting conversation with {chat_name}")

        create_task_with_callback(
            self._client.delete_dialog(target.entity, revoke=True),
            lambda _: self._on_chat_deleted(target),
            self._on_delete_chat_error,
        )

    def _on_chat_deleted(self, target: Any) -> None:
        """Handle successful delete."""
        chat_name = target.name if target else "chat"
        dialog_id = target.id

        # Remove from dialogs list
        self._dialogs = [d for d in self._dialogs if d.id != dialog_id]

        # Remove from UI
        row = self._dialog_rows.get(dialog_id)
        if row:
            self._chat_listbox.remove(row)
            del self._dialog_rows[dialog_id]

        # Clear current chat view if this was the open chat
        if self._current_dialog and self._current_dialog.id == dialog_id:
            self._current_dialog = None
            self._placeholder.set_visible(True)
            self._chat_view.set_visible(False)

            # Clear messages
            while True:
                row = self._messages_listbox.get_first_child()
                if row is None:
                    break
                self._messages_listbox.remove(row)

        self._action_target_dialog = None
        self._announcer.announce(f"Deleted conversation with {chat_name}")
        self._chat_listbox.grab_focus()

    def _on_delete_chat_error(self, error: Exception) -> None:
        """Handle delete chat error."""
        self._announcer.announce(f"Failed to delete chat: {error}")
        logger.exception("Failed to delete chat: %s", error)
