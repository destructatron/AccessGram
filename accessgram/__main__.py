"""AccessGram - An accessible Telegram client for Linux.

Entry point for running the application with: python -m accessgram
"""

import sys


def main() -> int:
    """Main entry point for AccessGram."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gst", "1.0")

    from gi.repository import Gst

    # Initialize GStreamer
    Gst.init(None)

    # Set up asyncio-GLib integration
    from accessgram.utils.async_bridge import setup_async_glib

    setup_async_glib()

    # Import and run the application
    from accessgram.app import AccessGramApplication

    app = AccessGramApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
