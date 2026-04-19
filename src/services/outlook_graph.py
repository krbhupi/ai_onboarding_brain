"""Microsoft Graph API email service for Outlook.com."""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import httpx
import base64

from config.settings import get_settings
from config.logging import logger

settings = get_settings()

# Microsoft Graph API endpoints
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Required scopes
SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
    "offline_access"
]


class OutlookGraphService:
    """Email service using Microsoft Graph API."""

    def __init__(self):
        self.client_id = settings.OUTLOOK_CLIENT_ID
        self.client_secret = settings.OUTLOOK_CLIENT_SECRET
        self.email = settings.SMTP_FROM_EMAIL
        self._access_token = None
        self._refresh_token = None
        self._http_client = httpx.AsyncClient()

    def get_auth_url(self, redirect_uri: str, state: str = "random_state") -> str:
        """Get authorization URL for OAuth2 flow."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "response_mode": "query",
            "state": state
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{AUTH_URL}?{query}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access token."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(SCOPES)
        }

        response = await self._http_client.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()

        token_data = response.json()
        self._access_token = token_data["access_token"]
        self._refresh_token = token_data.get("refresh_token")

        return token_data

    async def refresh_access_token(self) -> str:
        """Refresh the access token."""
        if not self._refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(SCOPES)
        }

        response = await self._http_client.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()

        token_data = response.json()
        self._access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            self._refresh_token = token_data["refresh_token"]

        return self._access_token

    def set_tokens(self, access_token: str, refresh_token: str = None):
        """Set tokens directly."""
        self._access_token = access_token
        self._refresh_token = refresh_token

    def _get_headers(self) -> dict:
        """Get authorization headers."""
        if not self._access_token:
            raise ValueError("Not authenticated. Please complete OAuth2 flow first.")
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }

    async def read_inbox(
        self,
        folder: str = "inbox",
        unread_only: bool = True,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Read emails from inbox using Graph API."""
        url = f"{GRAPH_API_BASE}/me/mailFolders/{folder}/messages"

        params = {
            "$top": limit,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,toRecipients,body,hasAttachments,receivedDateTime,isRead"
        }

        if unread_only:
            params["$filter"] = "isRead eq false"

        response = await self._http_client.get(
            url,
            headers=self._get_headers(),
            params=params
        )

        if response.status_code == 401:
            # Token expired, try refresh
            await self.refresh_access_token()
            response = await self._http_client.get(
                url,
                headers=self._get_headers(),
                params=params
            )

        response.raise_for_status()
        data = response.json()

        emails = []
        for msg in data.get("value", []):
            email_data = {
                "message_id": msg.get("id"),
                "from_address": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                "from_name": msg.get("from", {}).get("emailAddress", {}).get("name", ""),
                "subject": msg.get("subject", ""),
                "body": msg.get("body", {}).get("content", ""),
                "received_on": msg.get("receivedDateTime"),
                "is_read": msg.get("isRead", True),
                "has_attachments": msg.get("hasAttachments", False)
            }
            emails.append(email_data)

        return emails

    async def get_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """Get attachments for a message."""
        url = f"{GRAPH_API_BASE}/me/messages/{message_id}/attachments"

        response = await self._http_client.get(
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()
        data = response.json()

        attachments = []
        for att in data.get("value", []):
            attachments.append({
                "id": att.get("id"),
                "name": att.get("name"),
                "content_type": att.get("contentType"),
                "size": att.get("size"),
                "content_bytes": att.get("contentBytes")  # Base64 encoded
            })

        return attachments

    async def save_attachment(self, attachment: Dict[str, Any], save_path: str) -> str:
        """Save attachment to disk."""
        from pathlib import Path

        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        content = base64.b64decode(attachment["content_bytes"])
        with open(path, "wb") as f:
            f.write(content)

        return str(path)

    async def send_email(
        self,
        to_address: str,
        subject: str,
        body: str,
        content_type: str = "Text"
    ) -> bool:
        """Send email using Graph API."""
        url = f"{GRAPH_API_BASE}/me/sendMail"

        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": content_type,
                    "content": body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_address
                        }
                    }
                ]
            }
        }

        response = await self._http_client.post(
            url,
            headers=self._get_headers(),
            json=email_data
        )

        if response.status_code == 401:
            await self.refresh_access_token()
            response = await self._http_client.post(
                url,
                headers=self._get_headers(),
                json=email_data
            )

        return response.status_code == 202

    async def close(self):
        """Close HTTP client."""
        await self._http_client.aclose()


def print_oauth_instructions():
    """Print instructions for setting up OAuth2."""
    print("""
========================================
Microsoft Graph API OAuth2 Setup Guide
========================================

Since Microsoft has disabled basic authentication for Outlook.com,
you need to register an app in Azure to use OAuth2.

Step 1: Register App in Azure
-----------------------------
1. Go to: https://portal.azure.com/
2. Navigate to: Azure Active Directory > App registrations
3. Click "New registration"
4. Name: "HR Automation"
5. Supported account types: "Accounts in any organizational directory and personal Microsoft accounts"
6. Redirect URI: Web - http://localhost:8000/auth/callback
7. Click "Register"

Step 2: Get Client ID and Secret
---------------------------------
1. Copy the "Application (client) ID"
2. Go to "Certificates & secrets"
3. Click "New client secret"
4. Add description and expiry
5. Copy the secret value immediately

Step 3: Add Permissions
-----------------------
1. Go to "API permissions"
2. Click "Add a permission"
3. Select "Microsoft Graph"
4. Select "Delegated permissions"
5. Add these permissions:
   - Mail.Read
   - Mail.Send
   - User.Read
   - offline_access

Step 4: Update .env file
------------------------
OUTLOOK_CLIENT_ID=your-client-id-here
OUTLOOK_CLIENT_SECRET=your-client-secret-here
USE_OAUTH2=true

Step 5: Authorize
-----------------
1. Start the application
2. Visit: http://localhost:8000/auth/outlook
3. Sign in with your Outlook account
4. Grant permissions
5. You'll be redirected back with tokens stored automatically

========================================
""")


if __name__ == "__main__":
    print_oauth_instructions()