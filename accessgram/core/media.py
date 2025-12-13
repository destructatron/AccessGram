"""Media operations for AccessGram.

Handles file uploads, downloads, and voice message processing.
"""

import asyncio
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from telethon.tl.types import Message

from accessgram.utils.config import get_cache_dir, get_downloads_dir

logger = logging.getLogger(__name__)


class MediaManager:
    """Manages media operations for Telegram messages."""

    def __init__(self, client: Any) -> None:
        """Initialize the media manager.

        Args:
            client: The AccessGramClient instance.
        """
        self._client = client
        self._download_tasks: dict[int, asyncio.Task] = {}
        self._progress_callbacks: dict[int, Callable[[int, int], None]] = {}

    async def download_media(
        self,
        message: Message,
        destination: Path | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path | None:
        """Download media from a message.

        Args:
            message: The message containing media.
            destination: Optional destination path. If None, uses downloads dir.
            progress_callback: Called with (downloaded_bytes, total_bytes).

        Returns:
            Path to downloaded file, or None if no media.
        """
        if not message.media:
            return None

        # Determine filename
        filename = self._get_media_filename(message)
        if not filename:
            return None

        # Set destination
        if destination:
            dest_path = Path(destination)
        else:
            dest_path = get_downloads_dir() / filename

        # Create parent directory
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Downloading media to: %s", dest_path)

        try:
            # Download with progress
            result = await self._client._client.download_media(
                message,
                str(dest_path),
                progress_callback=lambda current, total: self._on_progress(
                    message.id, current, total, progress_callback
                ),
            )

            if result:
                logger.info("Downloaded: %s", result)
                return Path(result)
            return None

        except Exception as e:
            logger.exception("Failed to download media: %s", e)
            raise

    async def download_voice(
        self,
        message: Message,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path | None:
        """Download a voice message to cache for playback.

        Args:
            message: The message containing a voice note.
            progress_callback: Called with (downloaded_bytes, total_bytes).

        Returns:
            Path to downloaded voice file.
        """
        if not message.voice:
            return None

        # Use cache dir for voice messages
        cache_dir = get_cache_dir() / "voice"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Use message ID as filename
        dest_path = cache_dir / f"{message.id}.ogg"

        # Check if already cached
        if dest_path.exists():
            logger.debug("Voice message already cached: %s", dest_path)
            return dest_path

        return await self.download_media(message, dest_path, progress_callback)

    async def upload_file(
        self,
        chat: Any,
        file_path: Path,
        caption: str = "",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Message:
        """Upload a file to a chat.

        Args:
            chat: The chat entity to send to.
            file_path: Path to the file to upload.
            caption: Optional caption for the file.
            progress_callback: Called with (uploaded_bytes, total_bytes).

        Returns:
            The sent Message object.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info("Uploading file: %s", file_path)

        try:
            result = await self._client._client.send_file(
                chat,
                str(file_path),
                caption=caption,
                progress_callback=lambda current, total: self._on_progress(
                    0, current, total, progress_callback
                ),
            )
            logger.info("File uploaded successfully")
            return result

        except Exception as e:
            logger.exception("Failed to upload file: %s", e)
            raise

    async def send_voice(
        self,
        chat: Any,
        voice_path: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Message:
        """Send a voice message.

        Args:
            chat: The chat entity to send to.
            voice_path: Path to the OGG/Opus voice file.
            progress_callback: Called with (uploaded_bytes, total_bytes).

        Returns:
            The sent Message object.
        """
        voice_path = Path(voice_path)
        if not voice_path.exists():
            raise FileNotFoundError(f"Voice file not found: {voice_path}")

        logger.info("Sending voice message: %s", voice_path)

        try:
            result = await self._client._client.send_file(
                chat,
                str(voice_path),
                voice_note=True,
                progress_callback=lambda current, total: self._on_progress(
                    0, current, total, progress_callback
                ),
            )
            logger.info("Voice message sent successfully")
            return result

        except Exception as e:
            logger.exception("Failed to send voice message: %s", e)
            raise

    def _get_media_filename(self, message: Message) -> str | None:
        """Get the filename for a message's media."""
        if message.document:
            # Check for filename attribute
            for attr in message.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    return attr.file_name

            # Generate filename from mime type
            mime = message.document.mime_type or "application/octet-stream"
            ext = self._mime_to_extension(mime)
            return f"{message.id}{ext}"

        elif message.photo:
            return f"{message.id}.jpg"

        elif message.video:
            return f"{message.id}.mp4"

        elif message.voice:
            return f"{message.id}.ogg"

        elif message.audio:
            for attr in message.audio.attributes if hasattr(message, "audio") else []:
                if hasattr(attr, "file_name") and attr.file_name:
                    return attr.file_name
            return f"{message.id}.mp3"

        return None

    def _mime_to_extension(self, mime_type: str) -> str:
        """Convert MIME type to file extension."""
        mime_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
            "application/pdf": ".pdf",
            "application/zip": ".zip",
            "text/plain": ".txt",
        }
        return mime_map.get(mime_type, "")

    def _on_progress(
        self,
        message_id: int,
        current: int,
        total: int,
        callback: Callable[[int, int], None] | None,
    ) -> None:
        """Handle progress update."""
        if callback:
            callback(current, total)

    def clear_cache(self) -> int:
        """Clear cached media files.

        Returns:
            Number of files deleted.
        """
        cache_dir = get_cache_dir()
        count = 0

        for file_path in cache_dir.rglob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    count += 1
                except OSError as e:
                    logger.warning("Failed to delete cache file %s: %s", file_path, e)

        logger.info("Cleared %d cached files", count)
        return count

    def get_cache_size(self) -> int:
        """Get total size of cached files in bytes."""
        cache_dir = get_cache_dir()
        total = 0

        for file_path in cache_dir.rglob("*"):
            if file_path.is_file():
                total += file_path.stat().st_size

        return total


def format_file_size(size_bytes: int) -> str:
    """Format a file size in human-readable form.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string like "1.5 MB".
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
