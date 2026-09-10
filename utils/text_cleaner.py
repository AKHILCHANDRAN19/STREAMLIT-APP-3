import re


def clean_markdown_artifacts(text: str) -> str:
  """Completely removes markdown hashes, bold/italic asterisks, and tags."""
  if not text:
    return ""
  text = re.sub(r"<[^>]+>", "", text)
  text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
  text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
  text = re.sub(r"^\s*\*\s+", "• ", text, flags=re.MULTILINE)
  return text.strip()


def clean_mcq_data(mcq: dict) -> tuple[str, str]:
  """Strips leading question numbers, trailing page markers, and answer choice prefixes."""
  q_text = mcq.get("question", "")
  a_text = mcq.get("answer_text", "")

  clean_q = re.sub(r"^\d+\.\s*", "", q_text)
  clean_q = re.sub(r"\s*\(പേജ്\s*നമ്പർ:\s*\d+\)\s*$", "", clean_q)
  clean_ans = re.sub(r"^[A-D][\)\.]\s*", "", a_text, flags=re.IGNORECASE)

  return clean_markdown_artifacts(clean_q), clean_markdown_artifacts(clean_ans)


def format_bot_txt_output(mcq_list: list[dict]) -> str:
  """Formats parsed MCQ dictionaries into the exact Telegram Quiz Bot structure."""
  output_lines = []
  for i, mcq in enumerate(mcq_list, 1):
    clean_q, clean_ans = clean_mcq_data(mcq)
    output_lines.append(f"{i}. {clean_q} (പേജ് നമ്പർ: {mcq.get('page_number', 1)})")
    output_lines.append(f"A) {clean_markdown_artifacts(mcq.get('option_A', ''))}")
    output_lines.append(f"B) {clean_markdown_artifacts(mcq.get('option_B', ''))}")
    output_lines.append(f"C) {clean_markdown_artifacts(mcq.get('option_C', ''))}")
    output_lines.append(f"D) {clean_markdown_artifacts(mcq.get('option_D', ''))}")
    output_lines.append(f"ഉത്തരം: {mcq.get('answer_letter', 'A')}) {clean_ans}")
    output_lines.append(
        f"Sentence : ({clean_markdown_artifacts(mcq.get('source_sentence', ''))})\n"
    )
  return "\n".join(output_lines).strip()

