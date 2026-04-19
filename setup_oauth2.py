#!/usr/bin/env python
"""
OAuth2 Setup Helper for Outlook.com

This script helps you set up OAuth2 authentication for Microsoft Outlook.

Steps:
1. Register an app in Azure Portal
2. Get Client ID and Client Secret
3. Update .env file
4. Run this script to authorize

Run: python setup_oauth2.py
"""

import asyncio
import webbrowser
from urllib.parse import urlencode

# OAuth2 endpoints
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Required scopes for email operations
SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
    "offline_access"
]

REDIRECT_URI = "http://localhost:8000/auth/callback"


def print_setup_instructions():
    """Print detailed setup instructions."""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║           OUTLOOK OAUTH2 SETUP - Microsoft Azure App Registration            ║
╚══════════════════════════════════════════════════════════════════════════════╝

STEP 1: Go to Azure Portal
────────────────────────────
Visit: https://portal.azure.com/
Sign in with your Microsoft account (kr_bhupi@outlook.com)

STEP 2: Register New Application
─────────────────────────────────
1. Navigate to: Azure Active Directory > App registrations
2. Click "+ New registration"
3. Fill in the details:
   ┌─────────────────────────────────────────────────────────┐
   │ Name: HR Automation                                     │
   │ Supported account types:                                │
   │   ☑ Accounts in any organizational directory and        │
   │     personal Microsoft accounts                         │
   │ Redirect URI:                                           │
   │   Platform: Web                                         │
   │   URI: http://localhost:8000/auth/callback              │
   └─────────────────────────────────────────────────────────┘
4. Click "Register"

STEP 3: Get Client ID
──────────────────────
1. On the app overview page, copy the "Application (client) ID"
   Example: 12345678-1234-1234-1234-123456789012

STEP 4: Create Client Secret
─────────────────────────────
1. Go to "Certificates & secrets" in the left menu
2. Click "+ New client secret"
3. Description: "HR Automation Secret"
4. Expires: Choose appropriate duration (730 days recommended)
5. Click "Add"
6. ⚠️ IMPORTANT: Copy the secret VALUE immediately (shown only once!)

STEP 5: Add API Permissions
────────────────────────────
1. Go to "API permissions" in the left menu
2. Click "+ Add a permission"
3. Select "Microsoft Graph"
4. Select "Delegated permissions"
5. Add these permissions:
   ☑ Mail.Read
   ☑ Mail.Send
   ☑ User.Read
   ☑ offline_access (for refresh tokens)
6. Click "Add permissions"

STEP 6: Update .env File
─────────────────────────
Edit your .env file:

    USE_OAUTH2=true
    OUTLOOK_CLIENT_ID=your-client-id-here
    OUTLOOK_CLIENT_SECRET=your-client-secret-here

STEP 7: Run Authorization
─────────────────────────
After updating .env, run the authorization:

    python -c "from src.services.outlook_graph import print_oauth_instructions; print_oauth_instructions()"

Or start the API server and visit:
    http://localhost:8000/auth/outlook

╔══════════════════════════════════════════════════════════════════════════════╗
║                              IMPORTANT NOTES                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

⚠️  Keep your Client Secret secure - never commit it to git!
⚠️  The redirect URI must match exactly: http://localhost:8000/auth/callback
⚠️  For production, use HTTPS redirect URI

""")

def generate_auth_url(client_id: str) -> str:
    """Generate the authorization URL."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "response_mode": "query",
        "state": "hr_automation_auth"
    }
    return f"{AUTH_URL}?{urlencode(params)}"


if __name__ == "__main__":
    print_setup_instructions()

    # Check if credentials are already configured
    try:
        from config.settings import get_settings
        settings = get_settings()

        if settings.OUTLOOK_CLIENT_ID and settings.OUTLOOK_CLIENT_SECRET:
            print("\n✓ OAuth2 credentials found in .env file!")
            print(f"  Client ID: {settings.OUTLOOK_CLIENT_ID[:20]}...")

            auth_url = generate_auth_url(settings.OUTLOOK_CLIENT_ID)
            print(f"\nAuthorization URL:")
            print(f"  {auth_url}")

            print("\nOptions to authorize:")
            print("  1. Open URL in browser (may not work - use Option 2)")
            print("  2. Start API server: python main.py")
            print("     Then visit: http://localhost:8000/auth/outlook")

            open_browser = input("\nOpen authorization URL in browser? (y/n): ").strip().lower()
            if open_browser == 'y':
                webbrowser.open(auth_url)
        else:
            print("\n✗ OAuth2 credentials not configured.")
            print("  Please add OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET to .env")
    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure you have configured OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET in .env")