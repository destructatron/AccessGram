"""Focus management utilities for AccessGram.

Provides utilities for managing keyboard focus in the UI
to ensure a good screen reader experience.
"""

import logging
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

logger = logging.getLogger(__name__)


class FocusManager:
    """Manages focus state for accessibility.

    Provides utilities for saving/restoring focus around dialogs,
    and navigating between major UI areas.
    """

    def __init__(self, window: Gtk.Window) -> None:
        """Initialize the focus manager.

        Args:
            window: The main application window.
        """
        self._window = window
        self._focus_stack: list[Gtk.Widget] = []

    def push_focus(self) -> None:
        """Save current focus before opening a dialog or popup.

        Call this before showing a modal dialog to remember where
        focus should return when the dialog closes.
        """
        current = self._window.get_focus()
        if current:
            self._focus_stack.append(current)
            logger.debug("Pushed focus: %s", current)

    def pop_focus(self) -> bool:
        """Restore focus after closing a dialog.

        Call this after a modal dialog closes to return focus
        to the previously focused widget.

        Returns:
            True if focus was restored, False if stack was empty.
        """
        if not self._focus_stack:
            return False

        widget = self._focus_stack.pop()
        if widget.is_visible() and widget.get_sensitive():
            widget.grab_focus()
            logger.debug("Restored focus to: %s", widget)
            return True

        # Widget no longer valid, try the next one
        return self.pop_focus()

    def clear_stack(self) -> None:
        """Clear the focus stack.

        Call this when resetting the UI state.
        """
        self._focus_stack.clear()

    def focus_widget(self, widget: Gtk.Widget) -> bool:
        """Focus a specific widget.

        Args:
            widget: The widget to focus.

        Returns:
            True if focus was successful.
        """
        if widget.is_visible() and widget.get_sensitive() and widget.get_can_focus():
            widget.grab_focus()
            return True
        return False

    def focus_first_child(self, container: Gtk.Widget) -> bool:
        """Focus the first focusable child of a container.

        Args:
            container: The container widget.

        Returns:
            True if a child was focused.
        """
        child = container.get_first_child()
        while child:
            if child.get_can_focus() and child.is_visible() and child.get_sensitive():
                child.grab_focus()
                return True

            # Try children of this child
            if isinstance(child, Gtk.Widget):
                if self.focus_first_child(child):
                    return True

            child = child.get_next_sibling()

        return False


def trap_focus(dialog: Gtk.Window) -> Gtk.EventControllerKey:
    """Set up focus trapping for a dialog.

    This ensures Tab/Shift+Tab cycling stays within the dialog,
    which is important for accessibility.

    Args:
        dialog: The dialog window to trap focus in.

    Returns:
        The key event controller (for cleanup if needed).
    """
    controller = Gtk.EventControllerKey()

    def on_key_pressed(
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: int,
    ) -> bool:
        from gi.repository import Gdk

        # Only handle Tab key
        if keyval not in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            return False

        # Get all focusable widgets in the dialog
        focusable = _get_focusable_widgets(dialog)
        if not focusable:
            return False

        current = dialog.get_focus()
        if current not in focusable:
            # Focus first widget
            focusable[0].grab_focus()
            return True

        current_index = focusable.index(current)

        # Shift+Tab goes backwards
        shift_pressed = state & Gdk.ModifierType.SHIFT_MASK

        if shift_pressed:
            # Go to previous (wrap around)
            new_index = (current_index - 1) % len(focusable)
        else:
            # Go to next (wrap around)
            new_index = (current_index + 1) % len(focusable)

        focusable[new_index].grab_focus()
        return True

    controller.connect("key-pressed", on_key_pressed)
    dialog.add_controller(controller)
    return controller


def _get_focusable_widgets(container: Gtk.Widget) -> list[Gtk.Widget]:
    """Get all focusable widgets in a container, in tab order.

    Args:
        container: The container to search.

    Returns:
        List of focusable widgets.
    """
    result = []

    def collect(widget: Gtk.Widget) -> None:
        if not widget.is_visible():
            return

        if widget.get_can_focus() and widget.get_sensitive():
            result.append(widget)

        # Recurse into children
        child = widget.get_first_child()
        while child:
            collect(child)
            child = child.get_next_sibling()

    collect(container)
    return result


def announce_focus_change(widget: Gtk.Widget, announcer: Any) -> None:
    """Announce when focus changes to a widget.

    This can help users understand where focus has moved,
    especially after actions that move focus unexpectedly.

    Args:
        widget: The widget that received focus.
        announcer: ScreenReaderAnnouncer instance.
    """
    # Get the accessible label
    label = None

    # Try to get label from accessible property
    # Note: GTK4's accessible API is different
    if hasattr(widget, "get_accessible_role"):
        role = widget.get_accessible_role()
        # Build description based on role and content
        if isinstance(widget, Gtk.Button):
            label = widget.get_label() or "Button"
        elif isinstance(widget, Gtk.Entry):
            label = widget.get_placeholder_text() or "Text entry"
        elif isinstance(widget, Gtk.Label):
            label = widget.get_label()

    if label and announcer:
        announcer.announce_polite(f"Focus: {label}")
