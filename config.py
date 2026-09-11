import json
import os
import random
import streamlit as st


def get_secret(key: str, default: str = "") -> str:
  try:
    if key in st.secrets:
      return str(st.secrets[key]).strip()
  except Exception:
    pass
  return os.environ.get(key, default).strip()


API_ID_RAW = get_secret("API_ID")
API_ID = int(API_ID_RAW) if API_ID_RAW else None
API_HASH = get_secret("API_HASH")
BOT_TOKEN = get_secret("BOT_TOKEN")
BOT_SESSION = get_secret("BOT_SESSION")

TARGET_CHANNEL_ID_RAW = get_secret("TARGET_CHANNEL_ID", "-1004495069376")
TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID_RAW)

OWNER_IDS_RAW = get_secret("OWNER_IDS", "6219290068,5295973607")
OWNER_IDS = [int(x.strip()) for x in OWNER_IDS_RAW.split(",") if x.strip()]

DOWNLOAD_DIR = os.path.abspath("downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

FONT_PATH = os.path.abspath("THUMBA-Bold.ttf")

MAX_PAGES_PER_RUN = 250
EXTRA_MCQS = 4

# UPDATED: Increased delay to 12 seconds to prevent quota bans
DELAY_BETWEEN_PAGES = 12


def get_gemini_credentials() -> tuple[str, str, dict[str, str]]:
  """Extracts PSID, optional PSIDTS, and full cookies by randomly rotating accounts."""
  accounts = []

  # 1. Gather all accounts matching GEMINI_COOKIES_
  try:
    for key in st.secrets:
      if key.startswith("GEMINI_COOKIES_") and st.secrets[key]:
        accounts.append(str(st.secrets[key]).strip())
  except Exception:
    pass

  # Fallback to the old single JSON key if the numbered ones are missing
  if not accounts:
    legacy_cookie = get_secret("GEMINI_COOKIES_JSON")
    if legacy_cookie:
      accounts.append(legacy_cookie)

  if not accounts:
    raise ValueError("Missing 'GEMINI_COOKIES_...' in Streamlit secrets.")

  # 2. Randomly select one Google account for this run
  selected_raw_cookies = random.choice(accounts)

  try:
    data = json.loads(selected_raw_cookies)
  except json.JSONDecodeError as e:
    raise ValueError(f"Selected 'GEMINI_COOKIES' contains invalid JSON: {e}")

  cookie_dict = {}
  if isinstance(data, list):
    for c in data:
      if "name" in c and "value" in c:
        cookie_dict[c["name"]] = str(c["value"])
  elif isinstance(data, dict):
    cookie_dict = {k: str(v) for k, v in data.items()}

  psid = cookie_dict.get("__Secure-1PSID", "")
  psidts = cookie_dict.get("__Secure-1PSIDTS", "")

  if not psid:
    raise ValueError("Missing required '__Secure-1PSID' in selected cookies.")

  return psid, psidts, cookie_dict
