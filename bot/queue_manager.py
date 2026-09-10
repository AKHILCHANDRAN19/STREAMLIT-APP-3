import os


class QueueManager:

  def __init__(self):
    self.queues: dict[int, dict] = {}

  def init_user(self, user_id: int):
    if user_id not in self.queues:
      self.queues[user_id] = {
          "files": [],
          "is_processing": False,
          "doc_type": None,
      }

  def add_file(self, user_id: int, file_path: str, file_name: str, msg_id: int):
    self.init_user(user_id)
    self.queues[user_id]["files"].append(
        {"path": file_path, "name": file_name, "msg_id": msg_id}
    )

  def get_files(self, user_id: int) -> list[dict]:
    if user_id in self.queues:
      return self.queues[user_id]["files"]
    return []

  def get_doc_type(self, user_id: int) -> str | None:
    return self.queues.get(user_id, {}).get("doc_type")

  def set_doc_type(self, user_id: int, doc_type: str):
    self.init_user(user_id)
    self.queues[user_id]["doc_type"] = doc_type

  def is_processing(self, user_id: int) -> bool:
    return self.queues.get(user_id, {}).get("is_processing", False)

  def set_processing(self, user_id: int, status: bool):
    self.init_user(user_id)
    self.queues[user_id]["is_processing"] = status

  def clear_queue(self, user_id: int):
    if user_id in self.queues:
      for f in self.queues[user_id]["files"]:
        p = f.get("path")
        if p and os.path.exists(p):
          try:
            os.remove(p)
          except Exception:
            pass
      self.queues[user_id] = {
          "files": [],
          "is_processing": False,
          "doc_type": None,
      }


USER_QUEUE = QueueManager()

