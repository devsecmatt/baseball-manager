"""Yahoo OAuth2 authentication with automatic token refresh."""
import base64
import json
import time
import webbrowser
from pathlib import Path

import requests

from baseball_manager.config import (
    CLIENT_ID,
    CLIENT_SECRET,
    TOKEN_FILE,
    YAHOO_AUTH_URL,
    YAHOO_TOKEN_URL,
)

REDIRECT_URI = "https://localhost"
SCOPE = "openid fspt-r"


def _b64_credentials() -> str:
    creds = f"{CLIENT_ID}:{CLIENT_SECRET}"
    return base64.b64encode(creds.encode()).decode()


def _save_token(token: dict) -> None:
    token["saved_at"] = time.time()
    TOKEN_FILE.write_text(json.dumps(token, indent=2))
    TOKEN_FILE.chmod(0o600)


def _load_token() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def _is_expired(token: dict) -> bool:
    saved_at = token.get("saved_at", 0)
    expires_in = token.get("expires_in", 3600)
    # Refresh 5 minutes early
    return time.time() > saved_at + expires_in - 300


def refresh_token(token: dict) -> dict:
    """Exchange a refresh token for a new access token."""
    resp = requests.post(
        YAHOO_TOKEN_URL,
        headers={
            "Authorization": f"Basic {_b64_credentials()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "redirect_uri": REDIRECT_URI,
            "refresh_token": token["refresh_token"],
        },
    )
    resp.raise_for_status()
    new_token = resp.json()
    # Preserve refresh_token if not returned
    if "refresh_token" not in new_token:
        new_token["refresh_token"] = token["refresh_token"]
    _save_token(new_token)
    return new_token


def authorize() -> dict:
    """Run the full OAuth2 authorization code flow (interactive, one-time)."""
    from urllib.parse import quote
    auth_url = (
        f"{YAHOO_AUTH_URL}"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&response_type=code"
        f"&scope={quote(SCOPE, safe='')}"
    )

    print("\n=== Yahoo OAuth2 Authorization ===")
    print("Opening browser to authorize access...")
    print(f"\nIf the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("After approving, your browser will redirect to https://localhost")
    print("and show a connection error — that's expected.")
    print("Copy the FULL URL from your browser's address bar and paste it here.\n")
    raw = input("Paste the full redirect URL (or just the code): ").strip()

    # Accept either the full redirect URL or just the code
    if "code=" in raw:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(raw)
        code = parse_qs(parsed.query).get("code", [raw])[0]
    else:
        code = raw

    resp = requests.post(
        YAHOO_TOKEN_URL,
        headers={
            "Authorization": f"Basic {_b64_credentials()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )
    resp.raise_for_status()
    token = resp.json()
    _save_token(token)
    print("Authorization successful. Token saved.")
    return token


def get_valid_token() -> dict:
    """Return a valid (non-expired) token, refreshing or authorizing as needed."""
    token = _load_token()

    if token is None:
        print("No token found. Starting authorization flow...")
        return authorize()

    if _is_expired(token):
        print("Token expired, refreshing...")
        try:
            return refresh_token(token)
        except requests.HTTPError as e:
            print(f"Refresh failed ({e}), re-authorizing...")
            return authorize()

    return token


def get_access_token() -> str:
    """Convenience function: return just the access token string."""
    return get_valid_token()["access_token"]
