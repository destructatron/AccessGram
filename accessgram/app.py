"""AccessGram GTK Application.

Main application class that manages the GTK lifecycle, windows,
and coordinates between the Telegram client and UI.
"""

import asyncio
import logging
import sys

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk

from accessgram.core.auth import AuthManager, AuthState
from accessgram.core.client import AccessGramClient
from accessgram.ui.login import LoginView
from accessgram.ui.window import MainWindow
from accessgram.utils.async_bridge import run_async
from accessgram.utils.config import Config

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class AccessGramApplication(Gtk.Application):
    """Main GTK Application for AccessGram.

    This class manages the application lifecycle, handles authentication,
    and creates the main window.
    """

    def __init__(self) -> None:
        """Initialize the application."""
        super().__init__(
            application_id="org.accessgram.AccessGram",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

        self._config = Config.load()
        self._auth_manager: AuthManager | None = None
        self._client: AccessGramClient | None = None
        self._main_window: MainWindow | None = None
        self._login_window: Gtk.Window | None = None
        self._holding = False

    def do_startup(self) -> None:
        """Called when the application starts."""
        Gtk.Application.do_startup(self)
        self._setup_actions()
        logger.info("AccessGram started")

    def do_activate(self) -> None:
        """Called when the application is activated."""
        # Hold the application to prevent it from quitting
        # before async operations complete and show a window
        self.hold()
        self._holding = True

        # Check if we have API credentials
        if not self._config.has_credentials():
            self._show_credentials_dialog()
            return

        # Start authentication
        run_async(self._start_auth())

    def do_shutdown(self) -> None:
        """Called when the application shuts down."""
        # Disconnect client
        if self._client and self._client.is_connected:
            run_async(self._client.disconnect())

        # Save configuration
        self._config.save()

        Gtk.Application.do_shutdown(self)
        logger.info("AccessGram shut down")

    def _setup_actions(self) -> None:
        """Set up application actions (menu items, shortcuts)."""
        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit)
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        # Preferences action
        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect("activate", self._on_preferences)
        self.add_action(preferences_action)
        self.set_accels_for_action("app.preferences", ["<Control>comma"])

    def _release_hold(self) -> None:
        """Release the application hold if held."""
        if self._holding:
            self.release()
            self._holding = False

    def _on_quit(self, action: Gio.SimpleAction, param: None) -> None:
        """Handle quit action."""
        self.quit()

    def _on_about(self, action: Gio.SimpleAction, param: None) -> None:
        """Show about dialog."""
        about = Gtk.AboutDialog(
            transient_for=self._main_window or self._login_window,
            modal=True,
            program_name="AccessGram",
            version="0.1.0",
            comments="An accessible Telegram client for Linux",
            website="https://github.com/destructatron/AccessGram",
            license_type=Gtk.License.MIT_X11,
            authors=["AccessGram Contributors"],
        )
        about.present()

    def _on_preferences(self, action: Gio.SimpleAction, param: None) -> None:
        """Show preferences dialog."""
        # TODO: Implement preferences dialog
        pass

    def _show_credentials_dialog(self) -> None:
        """Show dialog to enter API credentials."""
        dialog = Gtk.Window(
            title="AccessGram - Setup",
            default_width=500,
            default_height=400,
        )
        dialog.set_application(self)

        # Make it accessible
        dialog.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["AccessGram Setup - Enter your Telegram API credentials"],
        )

        # Main content
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(30)
        box.set_margin_bottom(30)
        box.set_margin_start(30)
        box.set_margin_end(30)

        # Instructions
        instructions = Gtk.Label(
            label=(
                "To use AccessGram, you need Telegram API credentials.\n\n"
                "1. Go to my.telegram.org\n"
                "2. Log in with your phone number\n"
                "3. Go to 'API development tools'\n"
                "4. Create a new application\n"
                "5. Copy the api_id and api_hash below"
            ),
            wrap=True,
            xalign=0,
        )
        instructions.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Instructions for obtaining API credentials"],
        )
        box.append(instructions)

        # API ID entry
        api_id_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        api_id_label = Gtk.Label(label="API ID:")
        api_id_label.set_xalign(0)
        api_id_label.set_size_request(100, -1)
        api_id_entry = Gtk.Entry()
        api_id_entry.set_placeholder_text("Enter your API ID (numbers only)")
        api_id_entry.set_hexpand(True)
        api_id_entry.update_relation(
            [Gtk.AccessibleRelation.LABELLED_BY],
            [api_id_label],
        )
        api_id_box.append(api_id_label)
        api_id_box.append(api_id_entry)
        box.append(api_id_box)

        # API Hash entry
        api_hash_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        api_hash_label = Gtk.Label(label="API Hash:")
        api_hash_label.set_xalign(0)
        api_hash_label.set_size_request(100, -1)
        api_hash_entry = Gtk.Entry()
        api_hash_entry.set_placeholder_text("Enter your API Hash")
        api_hash_entry.set_hexpand(True)
        api_hash_entry.update_relation(
            [Gtk.AccessibleRelation.LABELLED_BY],
            [api_hash_label],
        )
        api_hash_box.append(api_hash_label)
        api_hash_box.append(api_hash_entry)
        box.append(api_hash_box)

        # Error label (hidden initially)
        error_label = Gtk.Label()
        error_label.add_css_class("error")
        error_label.set_visible(False)
        box.append(error_label)

        # Save button
        save_button = Gtk.Button(label="Save and Continue")
        save_button.add_css_class("suggested-action")
        save_button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Save credentials and continue to login"],
        )

        def on_save_clicked(button: Gtk.Button) -> None:
            api_id_text = api_id_entry.get_text().strip()
            api_hash_text = api_hash_entry.get_text().strip()

            # Validate
            if not api_id_text or not api_hash_text:
                error_label.set_label("Please enter both API ID and API Hash")
                error_label.set_visible(True)
                return

            try:
                api_id = int(api_id_text)
            except ValueError:
                error_label.set_label("API ID must be a number")
                error_label.set_visible(True)
                return

            # Save credentials
            self._config.api_id = api_id
            self._config.api_hash = api_hash_text
            self._config.save()

            # Close dialog and start auth
            dialog.close()
            run_async(self._start_auth())

        save_button.connect("clicked", on_save_clicked)
        box.append(save_button)

        dialog.set_child(box)
        dialog.present()

    async def _start_auth(self) -> None:
        """Start the authentication process."""
        self._auth_manager = AuthManager(self._config)
        result = await self._auth_manager.start()

        if result.state == AuthState.AUTHORIZED:
            # Already logged in, show main window
            await self._show_main_window()
        elif result.state == AuthState.ERROR:
            self._show_error_dialog("Authentication Error", result.error or "Unknown error")
        else:
            # Need to log in, show login view
            self._show_login_window()

    def _show_login_window(self) -> None:
        """Show the login window."""
        if self._login_window:
            self._login_window.present()
            return

        self._login_window = Gtk.Window(
            title="AccessGram - Login",
            default_width=400,
            default_height=350,
        )
        self._login_window.set_application(self)

        # Create login view
        login_view = LoginView(self._auth_manager)
        login_view.connect_authorized_callback(self._on_authorized)

        self._login_window.set_child(login_view)
        self._login_window.present()

        # Release the hold now that we have a window
        self._release_hold()

    def _on_authorized(self, user) -> None:
        """Called when user is successfully authorized."""
        # Hold the app while transitioning between windows
        self.hold()
        self._holding = True

        if self._login_window:
            self._login_window.close()
            self._login_window = None

        run_async(self._show_main_window())

    async def _show_main_window(self) -> None:
        """Show the main application window."""
        # Take over the client from auth manager (reuse existing connection)
        if self._auth_manager and self._auth_manager.client:
            self._client = AccessGramClient(self._config, self._auth_manager.client)
        else:
            # Fallback: create new client (shouldn't happen normally)
            self._client = AccessGramClient(self._config)
            await self._client.connect()

        # Get user info
        user = await self._client.get_me()
        user_name = user.first_name if user else "User"

        # Create main window
        self._main_window = MainWindow(
            application=self,
            client=self._client,
            config=self._config,
            user_name=user_name,
        )
        self._main_window.present()

        # Release the hold now that we have a window
        self._release_hold()

        # Load initial data
        await self._main_window.load_dialogs()

    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show an error dialog."""
        # Release hold if we're showing an error during startup
        self._release_hold()

        dialog = Gtk.AlertDialog(
            message=title,
            detail=message,
        )
        dialog.show(self._main_window or self._login_window)

    def get_client(self) -> AccessGramClient | None:
        """Get the Telegram client."""
        return self._client

    def get_config(self) -> Config:
        """Get the application configuration."""
        return self._config
