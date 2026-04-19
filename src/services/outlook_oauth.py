"""Outlook OAuth2 authentication for personal accounts."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
import httpx
from config.settings import get_settings
from config.logging import logger

settings = get_settings()

# Microsoft OAuth2 endpoints
MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Required scopes for IMAP/SMTP access
SCOPES = [
    "https://outlook.office.com/IMAP.AccessAsUser.All",
    "https://outlook.office.com/SMTP.Send",
    "offline_access"  # For refresh token
]


@dataclass
class OutlookTokens:
    """Store OAuth2 tokens."""
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "Bearer"


class OutlookOAuth2:
    """Handle Outlook OAuth2 authentication for personal accounts."""

    def __init__(self):
        self.client_id = settings.OUTLOOK_CLIENT_ID  # Need to add to settings
        self.client_secret = settings.OUTLOOK_CLIENT_SECRET  # Need to add to settings
        self.redirect_uri = "http://localhost:8000/auth/callback"
        self._tokens: Optional[OutlookTokens] = None
        self._http_client = httpx.AsyncClient()

    def get_authorization_url(self, state: str = "random_state") -> str:
        """Generate the authorization URL for user consent."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(SCOPES),
            "response_mode": "query",
            "state": state
        }

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{MICROSOFT_AUTH_URL}?{query}"

    async def exchange_code_for_token(self, code: str) -> OutlookTokens:
        """Exchange authorization code for access token."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(SCOPES)
        }

        response = await self._http_client.post(
            MICROSOFT_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()

        token_data = response.json()
        self._tokens = OutlookTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=datetime.utcnow() + timedelta(seconds=token_data["expires_in"]),
            token_type=token_data.get("token_type", "Bearer")
        )

        return self._tokens

    async def refresh_access_token(self) -> OutlookTokens:
        """Refresh the access token using refresh token."""
        if not self._tokens or not self._tokens.refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self._tokens.refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(SCOPES)
        }

        response = await self._http_client.post(
            MICROSOFT_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()

        token_data = response.json()
        self._tokens = OutlookTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", self._tokens.refresh_token),
            expires_at=datetime.utcnow() + timedelta(seconds=token_data["expires_in"]),
            token_type=token_data.get("token_type", "Bearer")
        )

        return self._tokens

    async def get_valid_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if not self._tokens:
            raise ValueError("No tokens available. Please authenticate first.")

        # Refresh if token expires in next 5 minutes
        if datetime.utcnow() + timedelta(minutes=5) >= self._tokens.expires_at:
            await self.refresh_access_token()

        return self._tokens.access_token

    def generate_auth_string(self) -> str:
        """Generate XOAUTH2 authentication string for IMAP."""
        if not self._tokens:
            raise ValueError("No tokens available")

        auth_string = f"user={settings.SMTP_FROM_EMAIL}\x01auth=Bearer {self._tokens.access_token}\x01\x01"
        return auth_string

    async def close(self):
        """Close HTTP client."""
        await self._http_client.aclose()


# For app password authentication (simpler)
class OutlookAppPasswordAuth:
    """Simple app password authentication for Outlook."""

    def __init__(self):
        self.email = settings.IMAP_USERNAME
        self.password = settings.IMAP_PASSWORD

    def get_imap_credentials(self) -> tuple:
        """Get IMAP credentials."""
        return (self.email, self.password)

    def get_smtp_credentials(self) -> tuple:
        """Get SMTP credentials."""
        return (self.email, self.password)


async def get_outlook_auth():
    """
    Setup guide for Outlook personal accounts.

    For personal Outlook.com accounts, you need to:
    1. Enable two-factor authentication
    2. Generate an app password

    Steps:
    1. Go to https://account.microsoft.com/security
    2. Enable Two-step verification if not already enabled
    3. Under "App passwords", create a new password
       - If you don't see "App passwords", try:
         https://account.live.com/proofs/Manage
       - Or: https://mysignins.microsoft.com/security-info

    4. Use the generated app password in your .env file:
       IMAP_PASSWORD=your-app-password
       SMTP_PASSWORD=your-app-password

    Alternative: Use OAuth2 by registering an app in Azure AD:
    1. Go to https://portal.azure.com/
    2. Navigate to Azure Active Directory > App registrations
    3. Create a new registration (personal accounts)
    4. Add redirect URI: http://localhost:8000/auth/callback
    5. Get client_id and client_secret
    6. Add to .env:
       OUTLOOK_CLIENT_ID=your-client-id
       OUTLOOK_CLIENT_SECRET=your-client-secret
    """
    pass


if __name__ == "__main__":
    # Quick test for app password auth
    import asyncio

    async def test_connection():
        from src.services.email_service import EmailService

        email_service = EmailService()
        try:
            # Test IMAP connection
            imap = email_service._connect_imap()
            print("IMAP connection successful!")
            email_service._disconnect_imap(imap)
        except Exception as e:
            print(f"IMAP connection failed: {e}")

    asyncio.run(test_connection())