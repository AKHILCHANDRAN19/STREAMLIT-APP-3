import json
import re


def repair_and_extract_json(raw_text: str) -> str:
  """Removes markdown code fences and cleans trailing commas."""
  cleaned = raw_text.strip()
  if cleaned.startswith("```json"):
    cleaned = cleaned[7:]
  elif cleaned.startswith("```"):
    cleaned = cleaned[3:]
  if cleaned.endswith("```"):
    cleaned = cleaned[:-3]
  cleaned = cleaned.strip()

  # Remove trailing commas preceding closing braces or brackets
  cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
  return cleaned


def robust_json_decode(raw_text: str, fallback_page_num: int = 1) -> dict:
  """Uses JSONDecoder().raw_decode to stop parsing at the true boundary,

  preventing 'trailing characters' errors from model chatter.
  """
  cleaned = repair_and_extract_json(raw_text)

  idx_brace = cleaned.find("{")
  idx_bracket = cleaned.find("[")

  if idx_brace == -1 and idx_bracket == -1:
    raise ValueError(f"No JSON object or array found in text: {cleaned[:100]}")

  start_idx = (
      idx_brace
      if (idx_bracket == -1 or (idx_brace != -1 and idx_brace < idx_bracket))
      else idx_bracket
  )
  candidate_str = cleaned[start_idx:]

  try:
    decoded_obj, _ = json.JSONDecoder().raw_decode(candidate_str)
  except Exception:
    if candidate_str.startswith("{"):
      end_idx = candidate_str.rfind("}")
    else:
      end_idx = candidate_str.rfind("]")

    if end_idx != -1:
      candidate_str = candidate_str[: end_idx + 1]
    candidate_str = re.sub(r",\s*([\]}])", r"\1", candidate_str)
    decoded_obj = json.loads(candidate_str)

  if isinstance(decoded_obj, list):
    return {"page_number": fallback_page_num, "mcqs": decoded_obj}
  return decoded_obj

