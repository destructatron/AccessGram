"""Authentication flow for AccessGram.

Handles the Telegram authentication process including phone number,
verification code, and two-factor authentication.
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from accessgram.utils.config import Config, get_session_path

logger = logging.getLogger(__name__)


class AuthState(Enum):
    """Authentication state machine states."""

    NOT_STARTED = auto()
    AWAITING_PHONE = auto()
    AWAITING_CODE = auto()
    AWAITING_PASSWORD = auto()  # 2FA
    AUTHORIZED = auto()
    ERROR = auto()


@dataclass
class AuthResult:
    """Result of an authentication step."""

    state: AuthState
    error: str | None = None
    user: Any = None

    @property
    def is_error(self) -> bool:
        """Check if this result represents an error."""
        return self.state == AuthState.ERROR or self.error is not None


class AuthManager:
    """Manages the Telegram authentication flow.

    This class handles the multi-step authentication process:
    1. Phone number submission
    2. Verification code entry
    3. Optional 2FA password

    Attributes:
        state: Current authentication state.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the auth manager.

        Args:
            config: Application configuration with API credentials.
        """
        self._config = config
        self._client: TelegramClient | None = None
        self._phone: str = ""
        self._phone_code_hash: str = ""
        self.state = AuthState.NOT_STARTED

    @property
    def client(self) -> TelegramClient | None:
        """Get the underlying Telethon client."""
        return self._client

    async def start(self) -> AuthResult:
        """Start the authentication process.

        Creates and connects the Telethon client.

        Returns:
            AuthResult indicating next state.
        """
        if not self._config.has_credentials():
            return AuthResult(
                state=AuthState.ERROR,
                error="API credentials not configured. Please set api_id and api_hash.",
            )

        try:
            session_path = get_session_path()
            self._client = TelegramClient(
                str(session_path),
                self._config.api_id,
                self._config.api_hash,
            )
            await self._client.connect()

            # Check if already authorized
            if await self._client.is_user_authorized():
                user = await self._client.get_me()
                self.state = AuthState.AUTHORIZED
                logger.info("Already authorized as %s", user.first_name if user else "Unknown")
                return AuthResult(state=AuthState.AUTHORIZED, user=user)

            self.state = AuthState.AWAITING_PHONE
            return AuthResult(state=AuthState.AWAITING_PHONE)

        except Exception as e:
            logger.exception("Failed to start authentication: %s", e)
            self.state = AuthState.ERROR
            return AuthResult(state=AuthState.ERROR, error=str(e))

    async def submit_phone(self, phone: str) -> AuthResult:
        """Submit phone number for verification.

        Args:
            phone: Phone number in international format (e.g., +1234567890).

        Returns:
            AuthResult indicating next state.
        """
        if not self._client:
            return AuthResult(state=AuthState.ERROR, error="Client not initialized")

        # Normalize phone number
        phone = phone.strip()
        if not phone.startswith("+"):
            phone = "+" + phone

        try:
            result = await self._client.send_code_request(phone)
            self._phone = phone
            self._phone_code_hash = result.phone_code_hash
            self.state = AuthState.AWAITING_CODE
            logger.info("Verification code sent to %s", phone)
            return AuthResult(state=AuthState.AWAITING_CODE)

        except PhoneNumberInvalidError:
            logger.warning("Invalid phone number: %s", phone)
            return AuthResult(
                state=AuthState.AWAITING_PHONE,
                error="Invalid phone number. Please use international format (e.g., +1234567890).",
            )
        except Exception as e:
            logger.exception("Failed to send verification code: %s", e)
            return AuthResult(state=AuthState.ERROR, error=str(e))

    async def submit_code(self, code: str) -> AuthResult:
        """Submit verification code.

        Args:
            code: The verification code received via SMS/Telegram.

        Returns:
            AuthResult indicating next state.
        """
        if not self._client:
            return AuthResult(state=AuthState.ERROR, error="Client not initialized")

        if not self._phone or not self._phone_code_hash:
            return AuthResult(
                state=AuthState.ERROR,
                error="Phone number not submitted. Please start over.",
            )

        # Clean up the code (remove spaces, dashes)
        code = "".join(c for c in code if c.isdigit())

        try:
            user = await self._client.sign_in(
                phone=self._phone,
                code=code,
                phone_code_hash=self._phone_code_hash,
            )
            self.state = AuthState.AUTHORIZED
            logger.info("Successfully signed in as %s", user.first_name if user else "Unknown")
            return AuthResult(state=AuthState.AUTHORIZED, user=user)

        except SessionPasswordNeededError:
            # 2FA is enabled
            self.state = AuthState.AWAITING_PASSWORD
            logger.info("Two-factor authentication required")
            return AuthResult(state=AuthState.AWAITING_PASSWORD)

        except PhoneCodeInvalidError:
            logger.warning("Invalid verification code")
            return AuthResult(
                state=AuthState.AWAITING_CODE,
                error="Invalid verification code. Please try again.",
            )
        except PhoneCodeExpiredError:
            logger.warning("Verification code expired")
            self.state = AuthState.AWAITING_PHONE
            return AuthResult(
                state=AuthState.AWAITING_PHONE,
                error="Verification code expired. Please request a new code.",
            )
        except Exception as e:
            logger.exception("Failed to verify code: %s", e)
            return AuthResult(state=AuthState.ERROR, error=str(e))

    async def submit_password(self, password: str) -> AuthResult:
        """Submit two-factor authentication password.

        Args:
            password: The 2FA password.

        Returns:
            AuthResult indicating next state.
        """
        if not self._client:
            return AuthResult(state=AuthState.ERROR, error="Client not initialized")

        try:
            user = await self._client.sign_in(password=password)
            self.state = AuthState.AUTHORIZED
            logger.info("Successfully signed in with 2FA as %s", user.first_name if user else "Unknown")
            return AuthResult(state=AuthState.AUTHORIZED, user=user)

        except Exception as e:
            # Check for wrong password error
            error_str = str(e).lower()
            if "password" in error_str or "invalid" in error_str:
                logger.warning("Invalid 2FA password")
                return AuthResult(
                    state=AuthState.AWAITING_PASSWORD,
                    error="Invalid password. Please try again.",
                )
            logger.exception("Failed to verify 2FA password: %s", e)
            return AuthResult(state=AuthState.ERROR, error=str(e))

    async def logout(self) -> bool:
        """Log out and delete session.

        Returns:
            True if successful.
        """
        if not self._client:
            return False

        try:
            await self._client.log_out()
            self.state = AuthState.NOT_STARTED
            self._phone = ""
            self._phone_code_hash = ""
            logger.info("Logged out successfully")
            return True
        except Exception as e:
            logger.exception("Failed to log out: %s", e)
            return False

    async def disconnect(self) -> None:
        """Disconnect the client."""
        if self._client:
            await self._client.disconnect()
            self._client = None
