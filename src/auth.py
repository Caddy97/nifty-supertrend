import os
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
TOKEN_FILE = "access_token.txt"

def get_kite():
    """Returns an authenticated KiteConnect object, using cached token if valid."""
    kite = KiteConnect(api_key=API_KEY)

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        kite.set_access_token(token)
        try:
            # quick check: if this fails, token is expired/invalid
            kite.profile()
            print("Using cached access token - valid.")
            return kite
        except Exception:
            print("Cached token expired or invalid. Need fresh login.")

    print("\n" + "=" * 60)
    print("LOGIN REQUIRED")
    print("=" * 60)
    print("1. Open this URL in your browser:")
    print(kite.login_url())
    print("\n2. Log in with your Zerodha credentials + 2FA")
    print("3. After login, you'll be redirected to a URL like:")
    print("   http://127.0.0.1:5000/kite/callback?request_token=XXXXX&...")
    print("4. Copy the value of 'request_token' from that URL")
    print("=" * 60)

    request_token = input("\nPaste the request_token here: ").strip()

    data = kite.generate_session(request_token, api_secret=API_SECRET)
    access_token = data["access_token"]

    kite.set_access_token(access_token)
    with open(TOKEN_FILE, "w") as f:
        f.write(access_token)

    print("\nLogin successful! Access token saved for today.")
    return kite

if __name__ == "__main__":
    kite = get_kite()
    profile = kite.profile()
    print(f"\nLogged in as: {profile['user_name']} ({profile['user_id']})")
