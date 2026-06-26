import os
import webbrowser
from dotenv import load_dotenv
from pathlib import Path
from kiteconnect import KiteConnect

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
TOKEN_FILE = "../access_token.txt"

kite = KiteConnect(api_key=API_KEY)
login_url = kite.login_url()

print("=" * 60)
print("MORNING LOGIN")
print("=" * 60)
print("Opening login page in your browser...")
print(f"(If it doesn't open, paste this manually: {login_url})")
print()

try:
    webbrowser.open(login_url)
except Exception:
    pass

print("After logging in, you'll land on a 'Not Found' page.")
print("Copy the FULL URL from your browser's address bar and paste it below.")
print("=" * 60)

full_url = input("\nPaste the full redirect URL here: ").strip()

# Extract request_token from the pasted URL automatically
if "request_token=" in full_url:
    request_token = full_url.split("request_token=")[1].split("&")[0]
else:
    request_token = full_url.strip()  # assume they pasted the bare token

data = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]

with open(TOKEN_FILE, "w") as f:
    f.write(access_token)

print("\nLogin successful! Token cached for today.")
print(f"Logged in as: {data['user_name']} ({data['user_id']})")
