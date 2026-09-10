import json
import os
import pathlib
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
DELAY_BETWEEN_PAGES = 3


def get_gemini_credentials() -> tuple[str, str | None]:
  """Extracts __Secure-1PSID and optionally __Secure-1PSIDTS if present."""
  raw_cookies = get_secret("GEMINI_COOKIES_JSON")
  if not raw_cookies:
    raise ValueError("Missing 'GEMINI_COOKIES_JSON' in Streamlit secrets.")

  try:
    data = json.loads(raw_cookies)
  except json.JSONDecodeError as e:
    raise ValueError(f"'GEMINI_COOKIES_JSON' contains invalid JSON: {e}")

  psid = ""
  psidts = None

  if isinstance(data, list):
    for c in data:
      name = c.get("name", "")
      if name in ["__Secure-1PSID", "_Secure-1PSID", "Secure-1PSID"]:
        psid = c.get("value", "")
      elif name in ["__Secure-1PSIDTS", "_Secure-1PSIDTS", "Secure-1PSIDTS"]:
        psidts = c.get("value", "")
  elif isinstance(data, dict):
    psid = data.get("__Secure-1PSID", data.get("_Secure-1PSID", ""))
    psidts = data.get("__Secure-1PSIDTS", data.get("_Secure-1PSIDTS", None))

  if not psid:
    raise ValueError("Missing mandatory '__Secure-1PSID' inside cookies.")

  # If psidts is empty string, convert to None
  if not psidts:
    psidts = None

  return psid, psidts
