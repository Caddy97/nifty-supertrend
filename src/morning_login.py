import os
import webbrowser
from dotenv import load_dotenv
from pathlib import Path
from kiteconnect import KiteConnect
from telegram_bot import send_message

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
TOKEN_FILE = BASE_DIR / "access_token.txt"

kite = KiteConnect(api_key=API_KEY)
login_url = kite.login_url()

print("=" * 60)
print("MORNING LOGIN")
print("=" * 60)

# Send login URL to Telegram so you can also click from phone
send_message(
    f"<b>Morning Login</b>\n"
    f"Click below to login to Kite, then paste the redirect URL here:\n\n"
    f"{login_url}"
)
print("Login URL sent to Telegram.")

print("Opening login page in your browser...")
try:
    webbrowser.open(login_url)
except Exception:
    pass

print()
print("After logging in you will land on a blank/error page.")
print("Copy the FULL URL from the address bar and paste it below.")
print("=" * 60)

full_url = input("\nPaste the full redirect URL here: ").strip()

if "request_token=" in full_url:
    request_token = full_url.split("request_token=")[1].split("&")[0]
else:
    request_token = full_url.strip()

data = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]

with open(TOKEN_FILE, "w") as f:
    f.write(access_token)

print(f"\nLogin successful! Logged in as: {data['user_name']} ({data['user_id']})")

send_message(
    f"<b>Login Successful</b>\n"
    f"User : {data['user_name']} ({data['user_id']})\n"
    f"Token is active until midnight tonight.\n"
    f"Candle accumulator and alerts are live."
)
print("Confirmation sent to Telegram.")
