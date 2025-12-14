"""Search dialog for AccessGram.

Provides a dialog to search for users, groups, and channels
to start new conversations.
"""

import logging
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk

from accessgram.core.client import AccessGramClient
from accessgram.utils.async_bridge import create_task_with_callback

logger = logging.getLogger(__name__)


class SearchResultRow(Gtk.ListBoxRow):
    """A row displaying a search result."""

    def __init__(self, entity: Any) -> None:
        """Initialize a search result row.

        Args:
            entity: The Telethon user/chat/channel entity.
        """
        super().__init__()
        self.entity = entity
        self._build_ui()
        self._update_accessibility()

    def _build_ui(self) -> None:
        """Build the row UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        # Type icon
        icon_name = self._get_icon_name()
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(24)
        box.append(icon)

        # Info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        name = self._get_name()
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0)
        name_label.set_ellipsize(True)
        name_label.add_css_class("heading")
        info_box.append(name_label)

        # Username or type
        subtitle = self._get_subtitle()
        if subtitle:
            subtitle_label = Gtk.Label(label=subtitle)
            subtitle_label.set_xalign(0)
            subtitle_label.add_css_class("dim-label")
            subtitle_label.add_css_class("caption")
            info_box.append(subtitle_label)

        box.append(info_box)
        self.set_child(box)

    def _get_name(self) -> str:
        """Get display name for the entity."""
        if hasattr(self.entity, "first_name"):
            # User
            name = self.entity.first_name or ""
            if self.entity.last_name:
                name += " " + self.entity.last_name
            return name or "Unknown User"
        elif hasattr(self.entity, "title"):
            # Chat or channel
            return self.entity.title or "Unknown"
        return "Unknown"

    def _get_subtitle(self) -> str:
        """Get subtitle (username or type)."""
        if hasattr(self.entity, "username") and self.entity.username:
            return f"@{self.entity.username}"
        if hasattr(self.entity, "broadcast") and self.entity.broadcast:
            return "Channel"
        if hasattr(self.entity, "megagroup") and self.entity.megagroup:
            return "Group"
        if hasattr(self.entity, "participants_count"):
            return f"{self.entity.participants_count} members"
        return ""

    def _get_icon_name(self) -> str:
        """Get icon name based on entity type."""
        if hasattr(self.entity, "first_name"):
            return "avatar-default-symbolic"
        elif hasattr(self.entity, "broadcast") and self.entity.broadcast:
            return "system-users-symbolic"
        else:
            return "user-available-symbolic"

    def _update_accessibility(self) -> None:
        """Update accessible properties."""
        name = self._get_name()
        subtitle = self._get_subtitle()

        if subtitle:
            accessible_label = f"{name}, {subtitle}"
        else:
            accessible_label = name

        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [accessible_label],
        )


class SearchDialog(Gtk.Window):
    """Dialog for searching users, groups, and channels."""

    def __init__(
        self,
        parent: Gtk.Window,
        client: AccessGramClient,
        on_select: Callable[[Any], None],
        on_view_profile: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize the search dialog.

        Args:
            parent: Parent window.
            client: Telegram client.
            on_select: Callback when an entity is selected.
            on_view_profile: Optional callback when "View profile" is selected.
        """
        super().__init__(
            title="Search",
            transient_for=parent,
            modal=True,
            default_width=400,
            default_height=500,
        )

        self._client = client
        self._on_select = on_select
        self._on_view_profile = on_view_profile
        self._search_timeout: int | None = None
        self._results: list[Any] = []

        self._build_ui()
        self._setup_actions()
        self._setup_context_menu()
        self._update_accessibility()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.set_titlebar(header)

        # Search entry
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search users, groups, channels...")
        self._search_entry.set_margin_start(12)
        self._search_entry.set_margin_end(12)
        self._search_entry.set_margin_top(12)
        self._search_entry.set_margin_bottom(8)
        self._search_entry.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Search for users, groups, and channels"],
        )
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_entry.connect("activate", self._on_search_activate)
        self._search_entry.connect("stop-search", lambda *args: self.close())
        box.append(self._search_entry)

        # Results list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._results_listbox = Gtk.ListBox()
        self._results_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._results_listbox.set_activate_on_single_click(True)
        self._results_listbox.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Search results"],
        )
        self._results_listbox.connect("row-activated", self._on_result_activated)
        scrolled.set_child(self._results_listbox)
        box.append(scrolled)

        # Status label
        self._status_label = Gtk.Label(label="Type to search")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_margin_top(12)
        self._status_label.set_margin_bottom(12)
        box.append(self._status_label)

        # Spinner
        self._spinner = Gtk.Spinner()
        self._spinner.set_margin_bottom(12)
        self._spinner.set_visible(False)
        box.append(self._spinner)

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

        # Focus search entry
        self._search_entry.grab_focus()

    def _update_accessibility(self) -> None:
        """Update dialog accessibility."""
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Search dialog - find users, groups, and channels"],
        )

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Handle search text change with debouncing."""
        # Cancel previous timeout
        if self._search_timeout:
            GLib.source_remove(self._search_timeout)
            self._search_timeout = None

        query = entry.get_text().strip()
        if len(query) < 2:
            self._clear_results()
            self._status_label.set_label("Type at least 2 characters to search")
            return

        # Debounce: wait 300ms before searching
        self._search_timeout = GLib.timeout_add(300, self._do_search, query)

    def _on_search_activate(self, entry: Gtk.SearchEntry) -> None:
        """Handle Enter key in search."""
        query = entry.get_text().strip()
        if len(query) >= 2:
            self._do_search(query)

    def _do_search(self, query: str) -> bool:
        """Perform the search."""
        self._search_timeout = None
        self._status_label.set_label("Searching...")
        self._spinner.set_visible(True)
        self._spinner.start()

        create_task_with_callback(
            self._client.search_global(query, limit=30),
            self._on_search_results,
            self._on_search_error,
        )

        return False  # Don't repeat timeout

    def _on_search_results(self, results: list[Any]) -> None:
        """Handle search results."""
        self._spinner.stop()
        self._spinner.set_visible(False)
        self._results = results

        # Clear existing results
        self._clear_results()

        if not results:
            self._status_label.set_label("No results found")
            return

        self._status_label.set_label(f"Found {len(results)} results")

        # Add result rows
        for entity in results:
            row = SearchResultRow(entity)
            self._results_listbox.append(row)

    def _on_search_error(self, error: Exception) -> None:
        """Handle search error."""
        self._spinner.stop()
        self._spinner.set_visible(False)
        self._status_label.set_label(f"Search failed: {error}")
        logger.exception("Search failed: %s", error)

    def _clear_results(self) -> None:
        """Clear the results list."""
        while True:
            row = self._results_listbox.get_first_child()
            if row is None:
                break
            self._results_listbox.remove(row)

    def _on_result_activated(
        self,
        listbox: Gtk.ListBox,
        row: SearchResultRow,
    ) -> None:
        """Handle result selection."""
        self._on_select(row.entity)
        self.close()

    def _setup_actions(self) -> None:
        """Set up window-level actions."""
        # Message action (same as activating)
        message_action = Gio.SimpleAction.new("message-entity", None)
        message_action.connect("activate", self._on_message_action)
        self.add_action(message_action)

        # View profile action
        view_profile_action = Gio.SimpleAction.new("view-profile", None)
        view_profile_action.connect("activate", self._on_view_profile_action)
        self.add_action(view_profile_action)

    def _setup_context_menu(self) -> None:
        """Set up context menu for search results."""
        from gi.repository import Gdk

        # Track which entity the context menu is targeting
        self._context_menu_entity = None
        self._context_menu = None

        # Right-click gesture
        click_gesture = Gtk.GestureClick()
        click_gesture.set_button(Gdk.BUTTON_SECONDARY)
        click_gesture.connect("pressed", self._on_context_menu_click)
        self._results_listbox.add_controller(click_gesture)

        # Keyboard controller for F10 and Menu key
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_context_menu_key)
        self._results_listbox.add_controller(key_controller)

    def _build_context_menu_model(self, entity: Any) -> Gio.Menu:
        """Build context menu model for an entity."""
        menu = Gio.Menu()
        menu.append("Message", "win.message-entity")

        # Only show "View profile" for users (not channels/groups)
        if hasattr(entity, "first_name"):
            menu.append("View profile", "win.view-profile")

        return menu

    def _show_context_menu(self, row: SearchResultRow) -> None:
        """Show context menu for a search result row."""
        # Store the target entity for actions
        self._context_menu_entity = row.entity

        # Clean up previous popover if it exists
        if self._context_menu is not None:
            self._context_menu.unparent()

        # Create menu model
        menu_model = self._build_context_menu_model(row.entity)

        # Create new popover parented to this row
        self._context_menu = Gtk.PopoverMenu.new_from_model(menu_model)
        self._context_menu.set_parent(row)
        self._context_menu.set_has_arrow(False)
        self._context_menu.popup()

    def _on_context_menu_click(
        self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float
    ) -> None:
        """Handle right-click on results list."""
        row = self._results_listbox.get_row_at_y(int(y))
        if row is not None:
            self._show_context_menu(row)

    def _on_context_menu_key(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> bool:
        """Handle keyboard shortcuts for context menu (F10, Menu key)."""
        from gi.repository import Gdk

        if keyval in (Gdk.KEY_F10, Gdk.KEY_Menu):
            row = self._results_listbox.get_selected_row()
            if row is not None:
                self._show_context_menu(row)
                return True
        return False

    def _on_message_action(self, action: Gio.SimpleAction, param: None) -> None:
        """Handle message action from context menu."""
        entity = self._context_menu_entity
        if entity:
            self._on_select(entity)
            self.close()

    def _on_view_profile_action(self, action: Gio.SimpleAction, param: None) -> None:
        """Handle view profile action from context menu."""
        entity = self._context_menu_entity
        if entity and self._on_view_profile:
            self._on_view_profile(entity)
            self.close()
