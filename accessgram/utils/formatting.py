"""Text formatting utilities for AccessGram.

Provides utilities for formatting messages, timestamps, and other
text content for display.
"""

from datetime import datetime, timedelta
from typing import Any


def format_timestamp(dt: datetime, include_date: bool = False) -> str:
    """Format a datetime for display.

    Args:
        dt: The datetime to format.
        include_date: If True, always include the date.

    Returns:
        Formatted time string.
    """
    if dt is None:
        return ""

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt

    if include_date:
        return dt.strftime("%d %b %Y, %H:%M")

    if delta.days == 0:
        return dt.strftime("%H:%M")
    elif delta.days == 1:
        return f"Yesterday {dt.strftime('%H:%M')}"
    elif delta.days < 7:
        return dt.strftime("%a %H:%M")
    elif dt.year == now.year:
        return dt.strftime("%d %b, %H:%M")
    else:
        return dt.strftime("%d %b %Y, %H:%M")


def format_relative_time(dt: datetime) -> str:
    """Format a datetime as relative time (e.g., "5 minutes ago").

    Args:
        dt: The datetime to format.

    Returns:
        Relative time string.
    """
    if dt is None:
        return ""

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt

    if delta < timedelta(seconds=60):
        return "just now"
    elif delta < timedelta(minutes=60):
        mins = int(delta.total_seconds() / 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    elif delta < timedelta(hours=24):
        hours = int(delta.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif delta < timedelta(days=7):
        days = delta.days
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif delta < timedelta(days=30):
        weeks = delta.days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif delta < timedelta(days=365):
        months = delta.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = delta.days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Truncate text to a maximum length.

    Args:
        text: The text to truncate.
        max_length: Maximum length including suffix.
        suffix: Suffix to add when truncating.

    Returns:
        Truncated text.
    """
    if not text:
        return ""

    # Remove newlines for preview
    text = text.replace("\n", " ").strip()

    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def format_message_preview(message: Any) -> str:
    """Format a message for preview display.

    Args:
        message: Telethon Message object.

    Returns:
        Preview text.
    """
    if message.text:
        return truncate_text(message.text)

    if message.photo:
        return "Photo"

    if message.video:
        return "Video"

    if message.voice:
        duration = ""
        if message.voice.attributes:
            for attr in message.voice.attributes:
                if hasattr(attr, "duration"):
                    duration = format_duration(attr.duration)
                    break
        return f"Voice message {duration}".strip()

    if message.audio:
        return "Audio"

    if message.document:
        filename = "Document"
        if message.document.attributes:
            for attr in message.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    filename = attr.file_name
                    break
        return truncate_text(filename)

    if message.sticker:
        emoji = ""
        if message.sticker.attributes:
            for attr in message.sticker.attributes:
                if hasattr(attr, "alt"):
                    emoji = attr.alt
                    break
        return f"Sticker {emoji}".strip()

    if message.gif:
        return "GIF"

    if message.poll:
        return "Poll"

    if message.contact:
        return "Contact"

    if message.geo:
        return "Location"

    return "Message"


def format_duration(seconds: int) -> str:
    """Format a duration in seconds.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string (e.g., "1:23" or "1:02:03").
    """
    if seconds < 0:
        return "0:00"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_count(count: int, singular: str, plural: str | None = None) -> str:
    """Format a count with appropriate singular/plural form.

    Args:
        count: The count.
        singular: Singular form (e.g., "message").
        plural: Plural form. If None, adds "s" to singular.

    Returns:
        Formatted string (e.g., "1 message" or "5 messages").
    """
    if plural is None:
        plural = singular + "s"

    if count == 1:
        return f"1 {singular}"
    else:
        return f"{count} {plural}"


def format_user_name(user: Any) -> str:
    """Format a user's display name.

    Args:
        user: Telethon User object.

    Returns:
        Display name.
    """
    if not user:
        return "Unknown"

    if hasattr(user, "first_name"):
        name = user.first_name or ""
        if user.last_name:
            name += " " + user.last_name
        return name.strip() or "Unknown"

    if hasattr(user, "title"):
        return user.title or "Unknown"

    return "Unknown"


def format_chat_name(chat: Any) -> str:
    """Format a chat's display name.

    Args:
        chat: Telethon Chat/Channel/User object.

    Returns:
        Display name.
    """
    if not chat:
        return "Unknown"

    if hasattr(chat, "title"):
        return chat.title or "Unknown"

    if hasattr(chat, "first_name"):
        return format_user_name(chat)

    return "Unknown"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe file system use.

    Args:
        filename: The filename to sanitize.

    Returns:
        Sanitized filename.
    """
    # Remove or replace problematic characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Remove leading/trailing spaces and dots
    filename = filename.strip(" .")

    # Limit length
    if len(filename) > 200:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        max_name_len = 200 - len(ext) - 1 if ext else 200
        filename = name[:max_name_len] + ("." + ext if ext else "")

    return filename or "unnamed"
