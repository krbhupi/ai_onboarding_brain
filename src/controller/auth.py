"""OAuth2 authentication controller for Outlook."""
from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import os

from config.settings import get_settings
from src.services.outlook_graph import OutlookGraphService

settings = get_settings()
router = APIRouter()

# Store tokens temporarily (in production, use database)
_token_store = {}


@router.get("/outlook")
async def outlook_auth():
    """Redirect to Microsoft OAuth2 authorization."""
    graph_service = OutlookGraphService()

    # Check if credentials are configured
    if not graph_service.client_id:
        return HTMLResponse(content="""
        <html>
        <body>
        <h1>OAuth2 Not Configured</h1>
        <p>Please add OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET to your .env file.</p>
        <p>Visit <a href="https://portal.azure.com/">Azure Portal</a> to register your app.</p>
        </body>
        </html>
        """)

    redirect_uri = "http://localhost:8000/auth/callback"
    auth_url = graph_service.get_auth_url(redirect_uri)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def outlook_callback(
    code: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
    state: str = Query(None)
):
    """Handle OAuth2 callback from Microsoft."""
    if error:
        return HTMLResponse(content=f"""
        <html>
        <body>
        <h1>Authentication Failed</h1>
        <p>Error: {error}</p>
        <p>Description: {error_description}</p>
        <a href="/">Go back</a>
        </body>
        </html>
        """)

    if not code:
        return HTMLResponse(content="""
        <html>
        <body>
        <h1>Authentication Failed</h1>
        <p>No authorization code received.</p>
        </body>
        </html>
        """)

    try:
        graph_service = OutlookGraphService()
        redirect_uri = "http://localhost:8000/auth/callback"

        token_data = await graph_service.exchange_code_for_token(code, redirect_uri)

        # Store tokens
        _token_store["access_token"] = token_data["access_token"]
        _token_store["refresh_token"] = token_data.get("refresh_token")

        # Save to file for persistence
        token_file = os.path.join(os.path.dirname(__file__), "..", "..", ".tokens")
        with open(token_file, "w") as f:
            f.write(f"ACCESS_TOKEN={token_data['access_token']}\n")
            if token_data.get("refresh_token"):
                f.write(f"REFRESH_TOKEN={token_data['refresh_token']}\n")

        return HTMLResponse(content="""
        <html>
        <body>
        <h1>Authentication Successful!</h1>
        <p>Your Outlook account is now connected.</p>
        <p>You can close this window and return to the application.</p>
        <a href="/">Go to API</a>
        </body>
        </html>
        """)

    except Exception as e:
        return HTMLResponse(content=f"""
        <html>
        <body>
        <h1>Authentication Error</h1>
        <p>{str(e)}</p>
        </body>
        </html>
        """)


@router.get("/status")
async def auth_status():
    """Check authentication status."""
    token_file = os.path.join(os.path.dirname(__file__), "..", "..", ".tokens")

    if os.path.exists(token_file):
        return {"authenticated": True, "message": "Outlook is connected"}
    else:
        return {"authenticated": False, "message": "Please visit /auth/outlook to connect your Outlook account"}


@router.get("/disconnect")
async def disconnect():
    """Disconnect Outlook account."""
    token_file = os.path.join(os.path.dirname(__file__), "..", "..", ".tokens")
    if os.path.exists(token_file):
        os.remove(token_file)
    _token_store.clear()

    return {"status": "disconnected", "message": "Outlook account disconnected"}


def get_graph_service() -> OutlookGraphService:
    """Get authenticated Graph service."""
    graph_service = OutlookGraphService()

    # Try to load tokens from file
    token_file = os.path.join(os.path.dirname(__file__), "..", "..", ".tokens")
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            tokens = {}
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    tokens[key] = value

            if "ACCESS_TOKEN" in tokens:
                graph_service.set_tokens(
                    tokens["ACCESS_TOKEN"],
                    tokens.get("REFRESH_TOKEN")
                )

    # Or from memory
    elif "access_token" in _token_store:
        graph_service.set_tokens(
            _token_store["access_token"],
            _token_store.get("refresh_token")
        )

    return graph_service