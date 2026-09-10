import collections
from datetime import datetime


class TelemetryState:

  def __init__(self):
    self.log_history = collections.deque(maxlen=60)
    self.current_status = {
        "task": "Idle",
        "details": "Waiting for PDF uploads or commands...",
    }

  def log(self, text: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {text}"
    self.log_history.append(entry)
    print(entry, flush=True)

  def set_status(self, task: str, details: str):
    self.current_status["task"] = task
    self.current_status["details"] = details


GLOBAL_STATE = TelemetryState()

