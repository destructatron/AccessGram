"""Telegram client wrapper for AccessGram.

This module wraps Telethon's TelegramClient to provide a clean interface
for the UI layer, handling connection management and event dispatching.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events
from telethon.tl.types import Dialog, Message, User

from accessgram.utils.config import Config, get_session_path

logger = logging.getLogger(__name__)


class AccessGramClient:
    """Wrapper around Telethon's TelegramClient.

    Provides async methods for Telegram operations and manages
    event handlers for real-time updates.
    """

    def __init__(self, config: Config, client: TelegramClient | None = None) -> None:
        """Initialize the client with configuration.

        Args:
            config: Application configuration with API credentials.
            client: Optional existing TelegramClient to use (e.g., from auth).
        """
        self._config = config
        self._client: TelegramClient | None = client
        self._connected = client is not None and client.is_connected()

        # Callbacks for events
        self._new_message_callbacks: list[Callable[[events.NewMessage.Event], Any]] = []
        self._message_edited_callbacks: list[Callable[[events.MessageEdited.Event], Any]] = []
        self._message_deleted_callbacks: list[Callable[[events.MessageDeleted.Event], Any]] = []
        self._message_read_callbacks: list[Callable[[events.MessageRead.Event], Any]] = []

        # Register event handlers if we already have a client
        if self._client:
            self._register_event_handlers()

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._client is not None

    async def connect(self) -> None:
        """Connect to Telegram servers.

        Raises:
            ValueError: If API credentials are not configured.
        """
        if not self._config.has_credentials():
            raise ValueError("API credentials not configured")

        session_path = get_session_path()
        logger.info("Connecting with session: %s", session_path)

        self._client = TelegramClient(
            str(session_path),
            self._config.api_id,
            self._config.api_hash,
        )

        # Register event handlers
        self._register_event_handlers()

        await self._client.connect()
        self._connected = True
        logger.info("Connected to Telegram")

    async def disconnect(self) -> None:
        """Disconnect from Telegram servers."""
        if self._client:
            await self._client.disconnect()
            self._connected = False
            logger.info("Disconnected from Telegram")

    async def is_authorized(self) -> bool:
        """Check if user is logged in.

        Returns:
            True if the user is authorized, False otherwise.
        """
        if not self._client:
            return False
        return await self._client.is_user_authorized()

    async def get_me(self) -> User | None:
        """Get the current user.

        Returns:
            The logged-in user, or None if not authorized.
        """
        if not self._client:
            return None
        return await self._client.get_me()

    # =========================================================================
    # Dialog (Chat List) Operations
    # =========================================================================

    async def get_dialogs(self, limit: int = 100) -> list[Dialog]:
        """Get list of all dialogs (chats).

        Args:
            limit: Maximum number of dialogs to fetch.

        Returns:
            List of Dialog objects.
        """
        if not self._client:
            return []
        return await self._client.get_dialogs(limit=limit)

    async def iter_dialogs(self, limit: int | None = None) -> AsyncIterator[Dialog]:
        """Iterate over all dialogs.

        Args:
            limit: Maximum number of dialogs (None for all).

        Yields:
            Dialog objects.
        """
        if not self._client:
            return
        async for dialog in self._client.iter_dialogs(limit=limit):
            yield dialog

    # =========================================================================
    # Message Operations
    # =========================================================================

    async def get_messages(
        self,
        chat: Any,
        limit: int = 50,
        offset_id: int = 0,
    ) -> list[Message]:
        """Get messages from a chat.

        Args:
            chat: The chat entity (dialog, user, chat ID, etc.)
            limit: Maximum number of messages to fetch.
            offset_id: Offset message ID for pagination.

        Returns:
            List of Message objects (newest first).
        """
        if not self._client:
            return []

        messages = await self._client.get_messages(chat, limit=limit, offset_id=offset_id)

        # Fetch reply messages for messages that are replies
        for message in messages:
            if message.reply_to:
                try:
                    reply_msg = await message.get_reply_message()
                    if reply_msg:
                        message.reply_to_msg = reply_msg
                except Exception as e:
                    logger.debug("Could not fetch reply message: %s", e)

        return messages

    async def iter_messages(
        self,
        chat: Any,
        limit: int | None = 50,
        offset_id: int = 0,
        reverse: bool = False,
    ) -> AsyncIterator[Message]:
        """Iterate over messages in a chat.

        Args:
            chat: The chat entity.
            limit: Maximum messages (None for all).
            offset_id: Offset message ID for pagination.
            reverse: If True, iterate oldest first.

        Yields:
            Message objects.
        """
        if not self._client:
            return
        async for message in self._client.iter_messages(
            chat, limit=limit, offset_id=offset_id, reverse=reverse
        ):
            yield message

    async def send_message(self, chat: Any, text: str) -> Message:
        """Send a text message.

        Args:
            chat: The chat entity to send to.
            text: The message text.

        Returns:
            The sent Message object.
        """
        if not self._client:
            raise RuntimeError("Client not connected")
        return await self._client.send_message(chat, text)

    async def send_file(
        self,
        chat: Any,
        file: str | Path,
        caption: str = "",
        voice_note: bool = False,
    ) -> Message:
        """Send a file or voice message.

        Args:
            chat: The chat entity to send to.
            file: Path to the file.
            caption: Optional caption text.
            voice_note: If True, send as voice message.

        Returns:
            The sent Message object.
        """
        if not self._client:
            raise RuntimeError("Client not connected")
        return await self._client.send_file(
            chat,
            str(file),
            caption=caption,
            voice_note=voice_note,
        )

    async def delete_messages(
        self,
        chat: Any,
        message_ids: list[int],
        revoke: bool = True,
    ) -> int:
        """Delete messages.

        Args:
            chat: The chat entity.
            message_ids: List of message IDs to delete.
            revoke: If True, delete for everyone.

        Returns:
            Number of messages deleted.
        """
        if not self._client:
            raise RuntimeError("Client not connected")
        result = await self._client.delete_messages(chat, message_ids, revoke=revoke)
        return result.pts_count if hasattr(result, "pts_count") else len(message_ids)

    # =========================================================================
    # Media Operations
    # =========================================================================

    async def download_media(
        self,
        message: Message,
        path: Path | None = None,
    ) -> Path | None:
        """Download media from a message.

        Args:
            message: The message containing media.
            path: Optional download path. If None, uses cache dir.

        Returns:
            Path to downloaded file, or None if no media.
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        if path:
            result = await self._client.download_media(message, str(path))
        else:
            result = await self._client.download_media(message)

        return Path(result) if result else None

    # =========================================================================
    # Chat Management Operations
    # =========================================================================

    async def delete_dialog(self, chat: Any, revoke: bool = True) -> None:
        """Delete/leave a dialog.

        Args:
            chat: The chat entity to delete/leave.
            revoke: If True, delete for everyone (if applicable).
        """
        if not self._client:
            raise RuntimeError("Client not connected")
        await self._client.delete_dialog(chat, revoke=revoke)

    async def mark_read(self, chat: Any, message: Message | None = None) -> bool:
        """Mark messages as read.

        Args:
            chat: The chat entity.
            message: Mark up to this message. If None, marks all as read.

        Returns:
            True if successful.
        """
        if not self._client:
            raise RuntimeError("Client not connected")
        return await self._client.send_read_acknowledge(chat, message)

    async def mute_chat(self, chat: Any, mute: bool = True) -> bool:
        """Mute or unmute a chat.

        Args:
            chat: The chat entity.
            mute: If True, mute the chat. If False, unmute.

        Returns:
            True if successful.
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        from telethon.tl.functions.account import UpdateNotifySettingsRequest
        from telethon.tl.types import InputNotifyPeer, InputPeerNotifySettings

        try:
            input_peer = await self._client.get_input_entity(chat)
            # mute_until = 2147483647 means mute forever, 0 means unmute
            mute_until = 2147483647 if mute else 0

            await self._client(UpdateNotifySettingsRequest(
                peer=InputNotifyPeer(peer=input_peer),
                settings=InputPeerNotifySettings(
                    mute_until=mute_until,
                    silent=mute,
                ),
            ))
            return True
        except Exception as e:
            logger.exception("Failed to update mute settings: %s", e)
            return False

    async def is_chat_muted(self, chat: Any) -> bool:
        """Check if a chat is muted.

        Args:
            chat: The chat entity.

        Returns:
            True if chat is muted.
        """
        if not self._client:
            return False

        from telethon.tl.functions.account import GetNotifySettingsRequest
        from telethon.tl.types import InputNotifyPeer

        try:
            input_peer = await self._client.get_input_entity(chat)
            settings = await self._client(GetNotifySettingsRequest(
                peer=InputNotifyPeer(peer=input_peer),
            ))
            # Check if mute_until is set to a future time
            import time
            return settings.mute_until is not None and settings.mute_until > int(time.time())
        except Exception as e:
            logger.exception("Failed to get mute settings: %s", e)
            return False

    # =========================================================================
    # Search Operations
    # =========================================================================

    async def search_global(self, query: str, limit: int = 20) -> list[Any]:
        """Search for users, chats, and channels globally.

        Args:
            query: Search query string.
            limit: Maximum results.

        Returns:
            List of search results.
        """
        if not self._client:
            return []

        from telethon.tl.functions.contacts import SearchRequest

        result = await self._client(SearchRequest(q=query, limit=limit))
        return list(result.users) + list(result.chats)

    async def search_messages(
        self,
        chat: Any,
        query: str,
        limit: int = 50,
    ) -> list[Message]:
        """Search messages in a chat.

        Args:
            chat: The chat entity.
            query: Search query string.
            limit: Maximum results.

        Returns:
            List of matching messages.
        """
        if not self._client:
            return []
        return await self._client.get_messages(chat, limit=limit, search=query)

    # =========================================================================
    # Event Handling
    # =========================================================================

    def _register_event_handlers(self) -> None:
        """Register Telethon event handlers."""
        if not self._client:
            return

        @self._client.on(events.NewMessage)
        async def on_new_message(event: events.NewMessage.Event) -> None:
            for callback in self._new_message_callbacks:
                try:
                    result = callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.exception("Error in new message callback: %s", e)

        @self._client.on(events.MessageEdited)
        async def on_message_edited(event: events.MessageEdited.Event) -> None:
            for callback in self._message_edited_callbacks:
                try:
                    result = callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.exception("Error in message edited callback: %s", e)

        @self._client.on(events.MessageDeleted)
        async def on_message_deleted(event: events.MessageDeleted.Event) -> None:
            for callback in self._message_deleted_callbacks:
                try:
                    result = callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.exception("Error in message deleted callback: %s", e)

        @self._client.on(events.MessageRead)
        async def on_message_read(event: events.MessageRead.Event) -> None:
            for callback in self._message_read_callbacks:
                try:
                    result = callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.exception("Error in message read callback: %s", e)

    def on_new_message(self, callback: Callable[[events.NewMessage.Event], Any]) -> None:
        """Register callback for new messages.

        Args:
            callback: Function called with NewMessage event.
        """
        self._new_message_callbacks.append(callback)

    def on_message_edited(self, callback: Callable[[events.MessageEdited.Event], Any]) -> None:
        """Register callback for edited messages.

        Args:
            callback: Function called with MessageEdited event.
        """
        self._message_edited_callbacks.append(callback)

    def on_message_deleted(self, callback: Callable[[events.MessageDeleted.Event], Any]) -> None:
        """Register callback for deleted messages.

        Args:
            callback: Function called with MessageDeleted event.
        """
        self._message_deleted_callbacks.append(callback)

    def on_message_read(self, callback: Callable[[events.MessageRead.Event], Any]) -> None:
        """Register callback for message read events.

        Args:
            callback: Function called with MessageRead event.
        """
        self._message_read_callbacks.append(callback)

    def remove_callback(self, callback: Callable) -> None:
        """Remove a registered callback.

        Args:
            callback: The callback to remove.
        """
        for callback_list in [
            self._new_message_callbacks,
            self._message_edited_callbacks,
            self._message_deleted_callbacks,
            self._message_read_callbacks,
        ]:
            if callback in callback_list:
                callback_list.remove(callback)

    # =========================================================================
    # Run loop
    # =========================================================================

    async def run_until_disconnected(self) -> None:
        """Run the client until disconnected.

        This keeps the client running to receive events.
        """
        if self._client:
            await self._client.run_until_disconnected()
