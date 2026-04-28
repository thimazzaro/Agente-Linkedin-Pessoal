"""
One-time LinkedIn OAuth 2.0 setup.
Run this script ONCE on your local machine to get the access token and person URN.
Then paste the values into your .env (or Railway env vars).

Usage:
  python scripts/setup_linkedin_auth.py

Requirements:
  pip install requests python-dotenv
  Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env first.
"""
import os
import sys
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8888/callback"
SCOPES = "openid profile email w_member_social"

if not CLIENT_ID or not CLIENT_SECRET:
    print(
        "ERROR: Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your .env file first.\n"
        "Get them from: https://www.linkedin.com/developers/apps"
    )
    sys.exit(1)

# Step 1 — Build authorization URL
auth_params = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "state": "linkedin_agent_setup",
}
auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(auth_params)

print("Opening LinkedIn authorization page in your browser…")
print(f"\nIf it doesn't open automatically, go to:\n{auth_url}\n")
webbrowser.open(auth_url)

# Step 2 — Local server catches the callback with the auth code
auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Authorization received! You can close this tab.</h2>")

    def log_message(self, *args):
        pass  # Suppress access log noise

server = HTTPServer(("localhost", 8888), CallbackHandler)
print("Waiting for LinkedIn callback on http://localhost:8888/callback …")
server.handle_request()

if not auth_code:
    print("ERROR: No authorization code received.")
    sys.exit(1)

# Step 3 — Exchange code for access token
token_resp = requests.post(
    "https://www.linkedin.com/oauth/v2/accessToken",
    data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=10,
)

if not token_resp.ok:
    print(f"ERROR getting token: {token_resp.status_code} {token_resp.text}")
    sys.exit(1)

token_data = token_resp.json()
access_token = token_data["access_token"]
expires_in = token_data.get("expires_in", 5184000)  # Default 60 days

# Step 4 — Get person URN via OIDC userinfo endpoint (works with openid+profile scopes)
me_resp = requests.get(
    "https://api.linkedin.com/v2/userinfo",
    headers={"Authorization": f"Bearer {access_token}"},
    timeout=10,
)
me_data = me_resp.json()

# OIDC returns "sub"; legacy /v2/me returns "id" — handle both
person_id = me_data.get("sub") or me_data.get("id")
if not person_id:
    print(f"ERROR: Could not find person ID in response: {me_data}")
    sys.exit(1)

person_urn = f"urn:li:person:{person_id}"
name = me_data.get("name") or f"{me_data.get('given_name', '')} {me_data.get('family_name', '')}".strip()

print("\n" + "=" * 60)
print(f"SUCCESS! Authenticated as: {name}")
print("=" * 60)
print("\nAdd these to your .env file and Railway environment variables:\n")
print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
print(f"LINKEDIN_PERSON_URN={person_urn}")
print(f"\nToken expires in ~{expires_in // 86400} days.")
print("Run this script again before expiry to refresh.\n")
