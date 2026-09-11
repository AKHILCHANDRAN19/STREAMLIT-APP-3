import asyncio
import logging
import sys
import threading
from bot.client import build_telegram_client
import streamlit as st
from utils.telemetry import GLOBAL_STATE

# 1. Force instant, unbuffered log flushing in Streamlit Cloud
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# 2. Bridge all logger.info/warning calls into GLOBAL_STATE for web display
class TelemetryLogHandler(logging.Handler):

  def emit(self, record):
    try:
      msg = self.format(record)
      GLOBAL_STATE.log(msg)
    except Exception:
      pass


# Configure root logger and guard against duplicate handler stacking on rerun
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

if not any(isinstance(h, TelemetryLogHandler) for h in root_logger.handlers):
  bridge_handler = TelemetryLogHandler()
  bridge_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
  root_logger.addHandler(bridge_handler)


# ==========================================
# 🚀 1. ASYNC BOT RUNNER (SIGNAL BYPASS)
# ==========================================
async def run_pyrofork_bot():
  app = None
  try:
    app = build_telegram_client()
    await app.start()
    GLOBAL_STATE.log("Pyrofork Bot connected and operational.")
    GLOBAL_STATE.set_status("Online", "Listening for Telegram updates...")

    # Bypasses signal handling crashes in secondary threads
    await asyncio.Event().wait()
  except Exception as e:
    GLOBAL_STATE.log(f"CRITICAL: Bot runner stopped: {e}")
  finally:
    if app and app.is_initialized:
      await app.stop()


@st.cache_resource
def start_bot_thread():
  def run_async_loop():
    try:
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      loop.run_until_complete(run_pyrofork_bot())
    except Exception as e:
      GLOBAL_STATE.log(f"Async loop runtime error: {e}")

  thread = threading.Thread(target=run_async_loop, daemon=True)
  thread.start()
  return thread


# Start bot daemon on initial application load
start_bot_thread()

# ==========================================
# 📊 2. STREAMLIT CLOUD DASHBOARD
# ==========================================
st.set_page_config(
    page_title="GenAI Processor Engine", page_icon="⚡", layout="wide"
)

st.title("⚡ GenAI Telegram Engine Dashboard")
st.caption(
    "Active • Pure WebAPI Architecture • PyMuPDF • WeasyPrint • Resumable"
)

col1, col2 = st.columns([1, 2])

with col1:
  st.subheader("📊 Engine Status")
  st.metric(label="Current Task", value=GLOBAL_STATE.current_status["task"])
  st.info(GLOBAL_STATE.current_status["details"])

  if st.button("🔄 Force Refresh"):
    st.rerun()

with col2:
  st.subheader("📜 Live Telemetry Console")

  @st.fragment(run_every="3s")
  def render_telemetry_console():
    history = list(GLOBAL_STATE.log_history) if GLOBAL_STATE.log_history else []
    log_text = (
        "\n".join(history[-40:])
        if history
        else "System ready. Awaiting requests..."
    )
    st.code(log_text, language="text")

  render_telemetry_console()

