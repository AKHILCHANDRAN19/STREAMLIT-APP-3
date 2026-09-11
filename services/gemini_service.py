import asyncio
import json
import logging
import os
import pathlib
import re
import sys
from config import DELAY_BETWEEN_PAGES, DOWNLOAD_DIR, EXTRA_MCQS, get_gemini_credentials
from gemini_webapi import GeminiClient
from models import PageMCQOutput, PDFAnalysis, WebAPIPageExtraction
from utils.json_cleaner import robust_json_decode
from utils.text_cleaner import clean_markdown_artifacts

logger = logging.getLogger("Gemini_Service")


def log_step(msg: str):
  """Forces real-time flushing directly to Streamlit Cloud container logs."""
  print(f"[GEMINI API] {msg}", flush=True)
  logger.info(msg)


async def init_gemini_client() -> GeminiClient:
  """Initializes GeminiClient with real-time handshake logging."""
  psid, psidts, _ = get_gemini_credentials()

  cache_dir = pathlib.Path(DOWNLOAD_DIR) / "gemini_cookie_cache"
  cache_dir.mkdir(parents=True, exist_ok=True)
  os.environ["GEMINI_COOKIE_PATH"] = str(cache_dir)

  masked_psid = (
      f"{psid[:10]}...{psid[-6:]}" if len(psid) > 16 else "VALID_TOKEN"
  )
  log_step(
      f"Connecting session with 1PSID: {masked_psid} | 1PSIDTS Present:"
      f" {bool(psidts)}"
  )

  client = GeminiClient(psid, psidts or "")
  await client.init(
      timeout=45, auto_close=False, close_delay=300, auto_refresh=False
  )
  log_step("Handshake successful. Gemini WebAPI session is online.")
  return client


async def analyze_document_title(chat, first_page_img: str) -> str:
  log_step(f"Analyzing title from page preview: {first_page_img}")
  prompt = (
      "Analyze this page. Create a very short, catchy title (maximum 3 to 4"
      " words) in the primary language of the document. Do NOT use underscores."
      " Output ONLY the title."
  )
  try:
    resp = await chat.send_message(prompt, files=[first_page_img])
    clean_title = re.sub(r"[^\w\s]", "", resp.text.strip())
    final_title = " ".join(clean_title.split()) or "Document_Output"
    log_step(f"Document title detected: '{final_title}'")
    return final_title
  except Exception as e:
    log_step(f"Title fallback triggered due to: {e}")
    return "Document_Output"


async def extract_table_of_contents(
    chat, image_paths: list[str]
) -> PDFAnalysis:
  log_step(
      f"Extracting Table of Contents from {len(image_paths)} preview pages..."
  )
  schema_json = json.dumps(PDFAnalysis.model_json_schema(), indent=2)
  prompt = f"""
    Analyze these uploaded document preview pages.
    Image 0 corresponds to Physical Page Index 0, Image 1 to Index 1, etc.

    TASK:
    1. Locate the Table of Contents (Index).
    2. Extract chapter numbers, chapter names (in original script/language), and their printed page numbers.
    3. Calculate 'offset' = Physical Image Index - Printed Page Number.

    OUTPUT RESTRICTION:
    Return raw JSON matching this schema only:
    {schema_json}
    """
  resp = await chat.send_message(prompt, files=image_paths)
  log_step(
      f"TOC raw response received ({len(resp.text)} chars). Parsing schema..."
  )

  decoded = robust_json_decode(resp.text)
  analysis = PDFAnalysis.model_validate(decoded)
  log_step(
      f"TOC Parsed: Found {len(analysis.chapters)} chapters (Offset:"
      f" {analysis.offset})"
  )
  return analysis


async def verify_chapter_page(
    chat, img_path: str, chap_num: int, chap_name: str
) -> bool:
  log_step(
      f"Verifying starting page for Chapter {chap_num} ('{chap_name}')..."
  )
  prompt = f"""
    Look at this single uploaded page.
    Does this page contain the starting title/heading for Chapter {chap_num}: '{chap_name}'?
    Reply STRICTLY with only 'YES' or 'NO'.
    """
  try:
    resp = await chat.send_message(prompt, files=[img_path])
    is_start = "YES" in resp.text.strip().upper()
    log_step(
        f"Chapter {chap_num} verification result: {'CONFIRMED (YES)' if is_start else 'REJECTED (NO)'}"
    )
    return is_start
  except Exception as e:
    log_step(f"Chapter verification error on Chapter {chap_num}: {e}")
    return False


async def generate_mcqs_for_page(
    chat,
    page_img: str,
    page_num: int,
    doc_type: str = "pointwise",
    max_retries: int = 3,
) -> PageMCQOutput:
  schema_json = json.dumps(PageMCQOutput.model_json_schema(), indent=2)

  # Phase 1: Fact Counting
  count_prompt = f"""
    Analyze Page {page_num} attached. 
    Count the distinct factual statements, definitions, vocabulary pairs, or table rows on this page.
    Return ONLY a JSON object: {{"max_potential_mcqs": 0}}
    """
  target_mcqs = EXTRA_MCQS
  log_step(f"[Page {page_num}] Scanning facts for question estimation...")

  try:
    count_resp = await chat.send_message(count_prompt, files=[page_img])
    decoded_count = robust_json_decode(count_resp.text, page_num)
    target_mcqs = decoded_count.get("max_potential_mcqs", 0) + EXTRA_MCQS
    log_step(
        f"[Page {page_num}] Potential facts detected. Target MCQs set to:"
        f" {target_mcqs}"
    )
  except Exception as e:
    log_step(
        f"[Page {page_num}] Fact estimation fallback: {e}. Defaulting to"
        f" {target_mcqs} MCQs"
    )

  await asyncio.sleep(1)

  # Phase 2: Synthesis with strict language lock
  gen_prompt = f"""
    CRITICAL LANGUAGE INSTRUCTION:
    1. Detect the primary language of the uploaded document page (e.g., Malayalam, Tamil, Hindi, English).
    2. You MUST write all question stems, choices (A, B, C, D), answer_text, and source_sentence STRICTLY in the EXACT SAME LANGUAGE as the source text on this page.
    3. STRICT FORBIDDEN: DO NOT TRANSLATE INTO ENGLISH if the page is in Malayalam or another non-English language.
       - If the document is in Malayalam, generate all questions and options 100% in Malayalam script (മലയാളത്തിൽ മാത്രം).
       - If the document is in English, generate in English.

    TASK:
    Generate exactly {target_mcqs} comprehensive MCQs strictly originating from this uploaded page (Page {page_num}).

    RULES:
    1. If concepts, vocabulary, or relations have multiple variants, test them from different angles without word-for-word duplication.
    2. Maintain strict factual fidelity to the source page.
    3. Ensure no trailing commas. Set 'page_number' to {page_num}.

    OUTPUT RESTRICTION:
    Return ONLY valid JSON matching this schema:
    {schema_json}
    """

  for attempt in range(1, max_retries + 1):
    try:
      log_step(
          f"[Page {page_num}] Generating MCQs (Attempt {attempt}/{max_retries})..."
      )
      resp = await chat.send_message(gen_prompt)
      decoded = robust_json_decode(resp.text, page_num)
      validated = PageMCQOutput.model_validate(decoded)
      validated.page_number = page_num

      log_step(
          f"[Page {page_num}] Successfully validated {len(validated.mcqs)} MCQs"
          " from response."
      )
      return validated
    except Exception as e:
      log_step(f"[Page {page_num}] Attempt {attempt} failed: {e}")
      if attempt < max_retries:
        log_step(f"[Page {page_num}] Sleeping {DELAY_BETWEEN_PAGES}s before retry...")
        await asyncio.sleep(DELAY_BETWEEN_PAGES)
      else:
        log_step(f"[Page {page_num}] Retries exhausted. Returning empty set.")
        return PageMCQOutput(page_number=page_num, mcqs=[])


async def extract_text_and_tables_webapi(
    client: GeminiClient, img_path: str, page_num: int
) -> WebAPIPageExtraction:
  log_step(f"[Page {page_num}] Running vision OCR (gemini-flash-lite)...")[span_1](start_span)[span_1](end_span)
  schema_json = json.dumps(WebAPIPageExtraction.model_json_schema(), indent=2)
  prompt = f"""
    Analyze this page image (Page {page_num}). Extract all paragraphs and tables.
    Do NOT translate. Keep the exact native language script of the document as shown in the image.
    Do NOT summarize. Do not use markdown headers (no ###) or asterisks.
    For tables, duplicate merged cells into corresponding rows so data is preserved.
    Set 'page_number' to {page_num}.

    OUTPUT RESTRICTION:
    Return raw JSON matching this schema only:
    {schema_json}
    """
  try:
    resp = await client.generate_content(
        prompt, model="gemini-flash-lite", files=[img_path]
    )
    decoded = robust_json_decode(resp.text, page_num)
    data = WebAPIPageExtraction.model_validate(decoded)
    log_step(f"[Page {page_num}] Extracted {len(data.blocks)} text/table blocks.")
    return data
  except Exception as e:
    log_step(f"[Page {page_num}] Vision OCR error: {e}")
    return WebAPIPageExtraction(page_number=page_num, blocks=[])

