"""Configuration management for AccessGram.

Handles user configuration, API credentials, and session paths
following XDG Base Directory specification.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Application name for XDG directories
APP_NAME = "accessgram"


def get_data_dir() -> Path:
    """Get XDG data directory for AccessGram.

    Returns:
        Path to ~/.local/share/accessgram/
    """
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data_home:
        base = Path(xdg_data_home)
    else:
        base = Path.home() / ".local" / "share"

    data_dir = base / APP_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_dir() -> Path:
    """Get XDG config directory for AccessGram.

    Returns:
        Path to ~/.config/accessgram/
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg_config_home:
        base = Path(xdg_config_home)
    else:
        base = Path.home() / ".config"

    config_dir = base / APP_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_cache_dir() -> Path:
    """Get XDG cache directory for AccessGram.

    Returns:
        Path to ~/.cache/accessgram/
    """
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "")
    if xdg_cache_home:
        base = Path(xdg_cache_home)
    else:
        base = Path.home() / ".cache"

    cache_dir = base / APP_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_session_path() -> Path:
    """Get path for Telethon session file.

    Returns:
        Path to session file (without .session extension).
    """
    return get_data_dir() / "session"


def get_downloads_dir() -> Path:
    """Get directory for downloaded files.

    Returns:
        Path to downloads directory.
    """
    downloads = get_data_dir() / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


@dataclass
class Config:
    """Application configuration."""

    # Telegram API credentials
    api_id: int = 0
    api_hash: str = ""

    # UI preferences
    message_preview_length: int = 50
    max_messages_to_load: int = 100

    # Accessibility settings
    announce_new_messages: bool = True
    announce_sent_messages: bool = True
    high_contrast: bool = False

    # Audio settings
    voice_message_volume: float = 1.0

    # Internal - not saved
    _config_path: Path = field(default_factory=lambda: get_config_dir() / "config.json")

    def has_credentials(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_id and self.api_hash)

    def save(self) -> None:
        """Save configuration to disk."""
        data = {
            "api_id": self.api_id,
            "api_hash": self.api_hash,
            "message_preview_length": self.message_preview_length,
            "max_messages_to_load": self.max_messages_to_load,
            "announce_new_messages": self.announce_new_messages,
            "announce_sent_messages": self.announce_sent_messages,
            "high_contrast": self.high_contrast,
            "voice_message_volume": self.voice_message_volume,
        }

        try:
            # Write atomically
            tmp_path = self._config_path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            tmp_path.rename(self._config_path)
            logger.debug("Configuration saved to %s", self._config_path)
        except OSError as e:
            logger.error("Failed to save configuration: %s", e)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from disk.

        Returns:
            Config instance with loaded or default values.
        """
        config_path = get_config_dir() / "config.json"
        config = cls(_config_path=config_path)

        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                config._load_from_dict(data)
                logger.debug("Configuration loaded from %s", config_path)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load configuration: %s", e)

        return config

    def _load_from_dict(self, data: dict[str, Any]) -> None:
        """Load values from a dictionary."""
        if "api_id" in data:
            self.api_id = int(data["api_id"])
        if "api_hash" in data:
            self.api_hash = str(data["api_hash"])
        if "message_preview_length" in data:
            self.message_preview_length = int(data["message_preview_length"])
        if "max_messages_to_load" in data:
            self.max_messages_to_load = int(data["max_messages_to_load"])
        if "announce_new_messages" in data:
            self.announce_new_messages = bool(data["announce_new_messages"])
        if "announce_sent_messages" in data:
            self.announce_sent_messages = bool(data["announce_sent_messages"])
        if "high_contrast" in data:
            self.high_contrast = bool(data["high_contrast"])
        if "voice_message_volume" in data:
            self.voice_message_volume = float(data["voice_message_volume"])
