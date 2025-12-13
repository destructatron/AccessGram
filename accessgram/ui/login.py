"""Login view for AccessGram.

Handles the authentication UI flow: phone number entry,
verification code input, and two-factor authentication.
"""

import logging
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from accessgram.core.auth import AuthManager, AuthResult, AuthState
from accessgram.utils.async_bridge import create_task_with_callback

logger = logging.getLogger(__name__)


class LoginView(Gtk.Box):
    """Login view widget.

    Uses a GtkStack to transition between different authentication states:
    - Phone number entry
    - Verification code entry
    - Two-factor password entry
    """

    def __init__(self, auth_manager: AuthManager) -> None:
        """Initialize the login view.

        Args:
            auth_manager: The authentication manager to use.
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._auth_manager = auth_manager
        self._authorized_callback: Callable[[Any], None] | None = None

        self._build_ui()
        self._update_view_for_state(auth_manager.state)

    def connect_authorized_callback(self, callback: Callable[[Any], None]) -> None:
        """Set callback to be called when authorized.

        Args:
            callback: Function called with the user object on success.
        """
        self._authorized_callback = callback

    def _build_ui(self) -> None:
        """Build the login UI."""
        # Header
        header = Gtk.Label(label="Welcome to AccessGram")
        header.add_css_class("title-1")
        header.set_margin_top(30)
        header.set_margin_bottom(20)
        self.append(header)

        # Stack for different login states
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(200)
        self._stack.set_vexpand(True)

        # Phone number page
        self._stack.add_named(self._build_phone_page(), "phone")

        # Verification code page
        self._stack.add_named(self._build_code_page(), "code")

        # 2FA password page
        self._stack.add_named(self._build_password_page(), "password")

        self.append(self._stack)

    def _build_phone_page(self) -> Gtk.Widget:
        """Build the phone number entry page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_margin_top(20)
        page.set_margin_bottom(30)
        page.set_valign(Gtk.Align.CENTER)

        # Instructions
        instructions = Gtk.Label(
            label="Enter your phone number in international format",
            wrap=True,
        )
        instructions.set_margin_bottom(10)
        page.append(instructions)

        # Phone entry
        phone_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        phone_label = Gtk.Label(label="Phone Number")
        phone_label.set_xalign(0)
        phone_box.append(phone_label)

        self._phone_entry = Gtk.Entry()
        self._phone_entry.set_placeholder_text("+1234567890")
        self._phone_entry.set_input_purpose(Gtk.InputPurpose.PHONE)
        self._phone_entry.update_relation(
            [Gtk.AccessibleRelation.LABELLED_BY],
            [phone_label],
        )
        self._phone_entry.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            ["Enter your phone number with country code, for example plus 1 2 3 4 5 6 7 8 9 0"],
        )
        self._phone_entry.connect("activate", self._on_phone_activate)
        phone_box.append(self._phone_entry)

        page.append(phone_box)

        # Error label
        self._phone_error = Gtk.Label()
        self._phone_error.add_css_class("error")
        self._phone_error.set_visible(False)
        self._phone_error.set_wrap(True)
        page.append(self._phone_error)

        # Submit button
        self._phone_button = Gtk.Button(label="Send Code")
        self._phone_button.add_css_class("suggested-action")
        self._phone_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Send verification code to this phone number"],
        )
        self._phone_button.connect("clicked", self._on_phone_submit)
        page.append(self._phone_button)

        # Spinner for loading state
        self._phone_spinner = Gtk.Spinner()
        self._phone_spinner.set_visible(False)
        page.append(self._phone_spinner)

        return page

    def _build_code_page(self) -> Gtk.Widget:
        """Build the verification code entry page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_margin_top(20)
        page.set_margin_bottom(30)
        page.set_valign(Gtk.Align.CENTER)

        # Instructions
        instructions = Gtk.Label(
            label="Enter the verification code sent to your phone",
            wrap=True,
        )
        instructions.set_margin_bottom(10)
        page.append(instructions)

        # Code entry
        code_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        code_label = Gtk.Label(label="Verification Code")
        code_label.set_xalign(0)
        code_box.append(code_label)

        self._code_entry = Gtk.Entry()
        self._code_entry.set_placeholder_text("12345")
        self._code_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self._code_entry.set_max_length(10)
        self._code_entry.update_relation(
            [Gtk.AccessibleRelation.LABELLED_BY],
            [code_label],
        )
        self._code_entry.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            ["Enter the verification code you received via SMS or Telegram"],
        )
        self._code_entry.connect("activate", self._on_code_activate)
        code_box.append(self._code_entry)

        page.append(code_box)

        # Error label
        self._code_error = Gtk.Label()
        self._code_error.add_css_class("error")
        self._code_error.set_visible(False)
        self._code_error.set_wrap(True)
        page.append(self._code_error)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)

        back_button = Gtk.Button(label="Back")
        back_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Go back to phone number entry"],
        )
        back_button.connect("clicked", self._on_code_back)
        button_box.append(back_button)

        self._code_button = Gtk.Button(label="Verify")
        self._code_button.add_css_class("suggested-action")
        self._code_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Submit verification code"],
        )
        self._code_button.connect("clicked", self._on_code_submit)
        button_box.append(self._code_button)

        page.append(button_box)

        # Spinner
        self._code_spinner = Gtk.Spinner()
        self._code_spinner.set_visible(False)
        page.append(self._code_spinner)

        return page

    def _build_password_page(self) -> Gtk.Widget:
        """Build the 2FA password entry page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_margin_top(20)
        page.set_margin_bottom(30)
        page.set_valign(Gtk.Align.CENTER)

        # Instructions
        instructions = Gtk.Label(
            label="Your account has two-factor authentication enabled.\nEnter your password to continue.",
            wrap=True,
        )
        instructions.set_margin_bottom(10)
        page.append(instructions)

        # Password entry
        password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        password_label = Gtk.Label(label="Password")
        password_label.set_xalign(0)
        password_box.append(password_label)

        self._password_entry = Gtk.PasswordEntry()
        self._password_entry.set_show_peek_icon(True)
        self._password_entry.update_relation(
            [Gtk.AccessibleRelation.LABELLED_BY],
            [password_label],
        )
        self._password_entry.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            ["Enter your two-factor authentication password"],
        )
        self._password_entry.connect("activate", self._on_password_activate)
        password_box.append(self._password_entry)

        page.append(password_box)

        # Error label
        self._password_error = Gtk.Label()
        self._password_error.add_css_class("error")
        self._password_error.set_visible(False)
        self._password_error.set_wrap(True)
        page.append(self._password_error)

        # Submit button
        self._password_button = Gtk.Button(label="Sign In")
        self._password_button.add_css_class("suggested-action")
        self._password_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Sign in with password"],
        )
        self._password_button.connect("clicked", self._on_password_submit)
        page.append(self._password_button)

        # Spinner
        self._password_spinner = Gtk.Spinner()
        self._password_spinner.set_visible(False)
        page.append(self._password_spinner)

        return page

    def _update_view_for_state(self, state: AuthState) -> None:
        """Update the visible page based on auth state."""
        if state == AuthState.AWAITING_PHONE or state == AuthState.NOT_STARTED:
            self._stack.set_visible_child_name("phone")
            self._phone_entry.grab_focus()
        elif state == AuthState.AWAITING_CODE:
            self._stack.set_visible_child_name("code")
            self._code_entry.grab_focus()
        elif state == AuthState.AWAITING_PASSWORD:
            self._stack.set_visible_child_name("password")
            self._password_entry.grab_focus()

    def _set_loading(self, page: str, loading: bool) -> None:
        """Set loading state for a page."""
        if page == "phone":
            self._phone_button.set_sensitive(not loading)
            self._phone_entry.set_sensitive(not loading)
            self._phone_spinner.set_visible(loading)
            if loading:
                self._phone_spinner.start()
            else:
                self._phone_spinner.stop()
        elif page == "code":
            self._code_button.set_sensitive(not loading)
            self._code_entry.set_sensitive(not loading)
            self._code_spinner.set_visible(loading)
            if loading:
                self._code_spinner.start()
            else:
                self._code_spinner.stop()
        elif page == "password":
            self._password_button.set_sensitive(not loading)
            self._password_entry.set_sensitive(not loading)
            self._password_spinner.set_visible(loading)
            if loading:
                self._password_spinner.start()
            else:
                self._password_spinner.stop()

    # =========================================================================
    # Phone Number Handlers
    # =========================================================================

    def _on_phone_activate(self, entry: Gtk.Entry) -> None:
        """Handle Enter key in phone entry."""
        self._on_phone_submit(None)

    def _on_phone_submit(self, button: Gtk.Button | None) -> None:
        """Submit phone number."""
        phone = self._phone_entry.get_text().strip()
        if not phone:
            self._phone_error.set_label("Please enter your phone number")
            self._phone_error.set_visible(True)
            return

        self._phone_error.set_visible(False)
        self._set_loading("phone", True)

        create_task_with_callback(
            self._auth_manager.submit_phone(phone),
            self._on_phone_result,
            self._on_phone_error,
        )

    def _on_phone_result(self, result: AuthResult) -> None:
        """Handle phone submission result."""
        self._set_loading("phone", False)

        if result.is_error:
            self._phone_error.set_label(result.error or "Unknown error")
            self._phone_error.set_visible(True)
            return

        self._update_view_for_state(result.state)

    def _on_phone_error(self, error: Exception) -> None:
        """Handle phone submission error."""
        self._set_loading("phone", False)
        self._phone_error.set_label(f"Error: {error}")
        self._phone_error.set_visible(True)
        logger.exception("Phone submission failed: %s", error)

    # =========================================================================
    # Verification Code Handlers
    # =========================================================================

    def _on_code_activate(self, entry: Gtk.Entry) -> None:
        """Handle Enter key in code entry."""
        self._on_code_submit(None)

    def _on_code_back(self, button: Gtk.Button) -> None:
        """Go back to phone entry."""
        self._auth_manager.state = AuthState.AWAITING_PHONE
        self._update_view_for_state(AuthState.AWAITING_PHONE)

    def _on_code_submit(self, button: Gtk.Button | None) -> None:
        """Submit verification code."""
        code = self._code_entry.get_text().strip()
        if not code:
            self._code_error.set_label("Please enter the verification code")
            self._code_error.set_visible(True)
            return

        self._code_error.set_visible(False)
        self._set_loading("code", True)

        create_task_with_callback(
            self._auth_manager.submit_code(code),
            self._on_code_result,
            self._on_code_error,
        )

    def _on_code_result(self, result: AuthResult) -> None:
        """Handle code submission result."""
        self._set_loading("code", False)

        if result.state == AuthState.AUTHORIZED:
            self._on_authorized(result.user)
            return

        if result.is_error:
            self._code_error.set_label(result.error or "Unknown error")
            self._code_error.set_visible(True)
            # Check if we need to go back to phone
            if result.state == AuthState.AWAITING_PHONE:
                self._update_view_for_state(result.state)
            return

        self._update_view_for_state(result.state)

    def _on_code_error(self, error: Exception) -> None:
        """Handle code submission error."""
        self._set_loading("code", False)
        self._code_error.set_label(f"Error: {error}")
        self._code_error.set_visible(True)
        logger.exception("Code submission failed: %s", error)

    # =========================================================================
    # Password (2FA) Handlers
    # =========================================================================

    def _on_password_activate(self, entry: Gtk.PasswordEntry) -> None:
        """Handle Enter key in password entry."""
        self._on_password_submit(None)

    def _on_password_submit(self, button: Gtk.Button | None) -> None:
        """Submit 2FA password."""
        password = self._password_entry.get_text()
        if not password:
            self._password_error.set_label("Please enter your password")
            self._password_error.set_visible(True)
            return

        self._password_error.set_visible(False)
        self._set_loading("password", True)

        create_task_with_callback(
            self._auth_manager.submit_password(password),
            self._on_password_result,
            self._on_password_error,
        )

    def _on_password_result(self, result: AuthResult) -> None:
        """Handle password submission result."""
        self._set_loading("password", False)

        if result.state == AuthState.AUTHORIZED:
            self._on_authorized(result.user)
            return

        if result.is_error:
            self._password_error.set_label(result.error or "Unknown error")
            self._password_error.set_visible(True)
            return

    def _on_password_error(self, error: Exception) -> None:
        """Handle password submission error."""
        self._set_loading("password", False)
        self._password_error.set_label(f"Error: {error}")
        self._password_error.set_visible(True)
        logger.exception("Password submission failed: %s", error)

    # =========================================================================
    # Authorization Complete
    # =========================================================================

    def _on_authorized(self, user) -> None:
        """Called when authorization is successful."""
        logger.info("Authorization successful for user: %s", user)
        if self._authorized_callback:
            self._authorized_callback(user)
