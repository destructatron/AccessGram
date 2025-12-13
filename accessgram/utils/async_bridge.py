"""Asyncio-GLib event loop integration.

This module sets up the asyncio event loop to work with GTK's GLib main loop,
allowing Telethon's async operations to work seamlessly with GTK4.
"""

import asyncio
from collections.abc import Callable
from typing import Any, Coroutine, TypeVar

import gi

gi.require_version("Gtk", "4.0")

T = TypeVar("T")


def setup_async_glib() -> asyncio.AbstractEventLoop:
    """Configure asyncio to use GLib event loop.

    This must be called before any asyncio operations and before
    creating the Gtk.Application.

    Returns:
        The configured event loop.
    """
    # PyGObject 3.50+ provides native asyncio integration
    from gi.events import GLibEventLoopPolicy

    policy = GLibEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    return policy.get_event_loop()


def run_async(coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    """Run a coroutine from a synchronous GTK callback.

    This schedules the coroutine to run on the GLib event loop.

    Args:
        coro: The coroutine to run.

    Returns:
        An asyncio Task that can be awaited or have callbacks attached.

    Example:
        def on_button_clicked(button):
            task = run_async(self.fetch_messages())
            task.add_done_callback(self.on_messages_fetched)
    """
    loop = asyncio.get_event_loop()
    return loop.create_task(coro)


def create_task_with_callback(
    coro: Coroutine[Any, Any, T],
    callback: Callable[[Any], None],
    error_callback: Callable[[Exception], None] | None = None,
) -> asyncio.Task[T]:
    """Run a coroutine and call a callback when done.

    This is a convenience wrapper for common GTK async patterns.

    Args:
        coro: The coroutine to run.
        callback: Called with the result on success.
        error_callback: Called with the exception on failure. If None,
                       exceptions are logged but not raised.

    Returns:
        The created task.
    """
    import logging

    logger = logging.getLogger(__name__)

    def done_callback(task: asyncio.Task) -> None:
        try:
            result = task.result()
            callback(result)
        except asyncio.CancelledError:
            logger.debug("Task was cancelled")
        except Exception as e:
            if error_callback:
                error_callback(e)
            else:
                logger.exception("Async task failed: %s", e)

    task = run_async(coro)
    task.add_done_callback(done_callback)
    return task
