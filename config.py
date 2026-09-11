import json
import os
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
DELAY_BETWEEN_PAGES = 12


def get_all_gemini_accounts() -> list[tuple[str, str]]:
  """Parses all configured GEMINI_COOKIES into a list of (psid, psidts)."""
  accounts_raw = []
  try:
    for key in sorted(st.secrets.keys()):
      if key.startswith("GEMINI_COOKIES_") and st.secrets[key]:
        accounts_raw.append(str(st.secrets[key]).strip())
  except Exception:
    pass

  if not accounts_raw:
    legacy = get_secret("GEMINI_COOKIES_JSON")
    if legacy:
      accounts_raw.append(legacy)

  parsed_accounts = []
  for raw_json in accounts_raw:
    try:
      data = json.loads(raw_json)
      cookie_dict = {}
      if isinstance(data, list):
        for c in data:
          if "name" in c and "value" in c:
            cookie_dict[c["name"]] = str(c["value"])
      elif isinstance(data, dict):
        cookie_dict = {k: str(v) for k, v in data.items()}

      psid = cookie_dict.get("__Secure-1PSID", "")
      psidts = cookie_dict.get("__Secure-1PSIDTS", "")
      if psid:
        parsed_accounts.append((psid, psidts))
    except Exception:
      continue

  if not parsed_accounts:
    raise ValueError("No valid GEMINI_COOKIES found in Streamlit secrets.")

  return parsed_accounts
