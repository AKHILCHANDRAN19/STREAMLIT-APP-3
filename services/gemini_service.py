import asyncio
import json
import logging
import os
import pathlib
import re
import sys
from config import DELAY_BETWEEN_PAGES, DOWNLOAD_DIR, EXTRA_MCQS, get_all_gemini_accounts
from gemini_webapi import GeminiClient
from models import PageMCQOutput, PDFAnalysis, WebAPIPageExtraction
from pydantic import BaseModel
from utils.json_cleaner import robust_json_decode
from utils.text_cleaner import clean_markdown_artifacts

logger = logging.getLogger("Gemini_Service")


def log_step(msg: str):
  """Forces real-time unbuffered flushing to container logs."""
  print(f"[GEMINI API] {msg}", flush=True)
  logger.info(msg)


class DocumentProfile(BaseModel):
  start_page: int
  language_mode: str  # "english", "malayalam", or "bilingual"
  document_title: str


async def init_gemini_client() -> GeminiClient:
  """Iterates through all configured Gemini accounts until a working one is authenticated."""
  accounts = get_all_gemini_accounts()
  log_step(f"Found {len(accounts)} configured Gemini account(s) to evaluate.")

  last_error = None

  for idx, (psid, psidts) in enumerate(accounts, 1):
    masked_psid = f"{psid[:10]}...{psid[-6:]}" if len(psid) > 16 else "VALID_TOKEN"
    log_step(f"Testing Account {idx}/{len(accounts)} (1PSID: {masked_psid} | 1PSIDTS: {bool(psidts)})...")

    cache_dir = pathlib.Path(DOWNLOAD_DIR) / "gemini_cookie_cache" / f"acc_{idx}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_COOKIE_PATH"] = str(cache_dir)

    client = GeminiClient(psid, psidts or "")

    try:
      await client.init(timeout=45, auto_close=False, close_delay=300, auto_refresh=False)

      status = str(getattr(client, "status", "")).upper()
      if "UNAUTHENTICATED" in status:
        raise ValueError("Google reported status as UNAUTHENTICATED")

      models = client.list_models()
      if not models:
        raise ValueError("No models returned (cookies expired or account restricted)")

      log_step(f"Account {idx} is VALID and AUTHENTICATED! (Available models: {len(models)})")
      return client

    except Exception as e:
      log_step(f"Account {idx} failed validation: {e}. Moving to next account...")
      last_error = e
      try:
        await client.close()
      except Exception:
        pass

  log_step("CRITICAL: All configured Gemini accounts failed authentication!")
  raise RuntimeError(f"All {len(accounts)} Gemini accounts failed authentication: {last_error}")


async def profile_document_preflight(client: GeminiClient, preview_images: list[str]) -> DocumentProfile:
  """Inspects initial preview pages to determine the actual content start, language mode, and title."""
  log_step(f"Analyzing {len(preview_images)} preview page(s) for document structure & language profile...")
  schema_json = json.dumps(DocumentProfile.model_json_schema(), indent=2)
  prompt = f"""
    Analyze these initial preview pages of the document.
    
    TASK:
    1. 'start_page': Determine the 1-based page number where academic study notes / syllabus content begins.
       - If Page 1 contains real study text, background, commissions, or objectives (even if there is a logo or banner), return 1.
       - If Page 1 is purely a greeting, institute welcome screen, tutor bio, or title card, skip to the page where actual study content starts.
    2. 'language_mode': Detect if the notes are 'english', 'malayalam', or 'bilingual' (English bullets with Malayalam translations).
    3. 'document_title': Create a clean 3-4 word title in the document's primary language without special characters.

    OUTPUT RESTRICTION:
    Return ONLY valid JSON matching this schema:
    {schema_json}
    """
  try:
    resp = await client.generate_content(prompt, model="gemini-flash-lite", files=preview_images)
    decoded = robust_json_decode(resp.text)
    profile = DocumentProfile.model_validate(decoded)
    log_step(f"Document Profile: Content starts on Page {profile.start_page} | Mode: {profile.language_mode} | Title: '{profile.document_title}'")
    return profile
  except Exception as e:
    log_step(f"Document profile fallback triggered: {e}")
    return DocumentProfile(start_page=1, language_mode="bilingual", document_title="Document_Output")


async def extract_table_of_contents(chat, image_paths: list[str]) -> PDFAnalysis:
  log_step(f"Extracting Table of Contents from {len(image_paths)} preview pages...")
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
  log_step(f"TOC raw response received ({len(resp.text)} chars). Parsing schema...")

  decoded = robust_json_decode(resp.text)
  analysis = PDFAnalysis.model_validate(decoded)
  log_step(f"TOC Parsed: Found {len(analysis.chapters)} chapters (Offset: {analysis.offset})")
  return analysis


async def verify_chapter_page(chat, img_path: str, chap_num: int, chap_name: str) -> bool:
  log_step(f"Verifying starting page for Chapter {chap_num} ('{chap_name}')...")
  prompt = f"""
    Look at this single uploaded page.
    Does this page contain the starting title/heading for Chapter {chap_num}: '{chap_name}'?
    Reply STRICTLY with only 'YES' or 'NO'.
    """
  try:
    resp = await chat.send_message(prompt, files=[img_path])
    is_start = "YES" in resp.text.strip().upper()
    log_step(f"Chapter {chap_num} verification result: {'CONFIRMED (YES)' if is_start else 'REJECTED (NO)'}")
    return is_start
  except Exception as e:
    log_step(f"Chapter verification error on Chapter {chap_num}: {e}")
    return False


async def generate_mcqs_for_page(
    chat,
    page_img: str,
    page_num: int,
    doc_profile: DocumentProfile,
    doc_type: str = "pointwise",
    max_retries: int = 3
) -> PageMCQOutput:
  schema_json = json.dumps(PageMCQOutput.model_json_schema(), indent=2)

  gen_prompt = f"""
    You are an expert examination paper setter analyzing Page {page_num} of '{doc_profile.document_title}'.
    
    CONTEXT & CONTINUITY:
    - You are reading this document page-by-page. Use context from earlier pages in this chat to complete multi-page sentences, lists, or tables without missing points.

    PHASE 1: PAGE EVALUATION & LANGUAGE
    - Check if this page contains testable study material.
      * If this page is SOLELY an institute branding slide, welcome greeting, instructor bio, or 'Thank You' slide with NO study facts, return IMMEDIATELY:
        {{"page_number": {page_num}, "mcqs": []}}
      * If it has facts (even with headers or decorative graphics), extract all information.
    - Language Enforcement: Match the document's primary syllabus script ({doc_profile.language_mode}).
      * If Malayalam or Bilingual, generate all question stems, choices (A, B, C, D), and answers 100% in Malayalam script.
      * If English, generate 100% in English.

    PHASE 2: EXHAUSTIVE FACT COVERAGE (N + {EXTRA_MCQS} RULE)
    - Identify every distinct factual statement, definition, sub-bullet, article, committee, date, and table cell on this page. Let this count be N.
    - Generate exactly (N + {EXTRA_MCQS}) comprehensive MCQs covering every point from multiple angles.
    - Each question MUST include the exact verbatim 'source_sentence' from the page image.

    PHASE 3: STRICT NEGATIVE CONSTRAINTS
    - Do NOT call python, execute tools, or attempt file generation.
    - Do NOT output preambles or conversational commentary (NEVER say "I will now generate...", "Here is the JSON...").
    - Output ONLY valid JSON inside ```json ... ``` code blocks matching this schema:
    {schema_json}
    """

  for attempt in range(1, max_retries + 1):
    try:
      log_step(f"[Page {page_num}] Generating MCQs in document session (Attempt {attempt}/{max_retries})...")
      resp = await chat.send_message(gen_prompt, files=[page_img])

      decoded = robust_json_decode(resp.text, page_num)
      validated = PageMCQOutput.model_validate(decoded)
      validated.page_number = page_num

      log_step(f"[Page {page_num}] Validated {len(validated.mcqs)} generated MCQs.")
      return validated

    except Exception as e:
      log_step(f"[Page {page_num}] Attempt {attempt} failed: {e}")
      if attempt < max_retries:
        log_step(f"[Page {page_num}] Waiting {DELAY_BETWEEN_PAGES}s before retry...")
        await asyncio.sleep(DELAY_BETWEEN_PAGES)
      else:
        log_step(f"[Page {page_num}] Retries exhausted. Returning empty output.")
        return PageMCQOutput(page_number=page_num, mcqs=[])


async def extract_text_and_tables_webapi(
    client: GeminiClient,
    img_path: str,
    page_num: int
) -> WebAPIPageExtraction:
  log_step(f"[Page {page_num}] Running vision OCR (gemini-flash-lite)...")
  schema_json = json.dumps(WebAPIPageExtraction.model_json_schema(), indent=2)
  prompt = f"""
    Analyze Page {page_num} attached as an image.
    Extract all textual content, hierarchical bullet points, sub-points, and tables exactly as printed.

    RULES:
    1. Do NOT summarize or omit points. Extract all headings, facts, dates, and explanations.
    2. Maintain the exact native language script of the page (do NOT translate Malayalam to English or English to Malayalam).
    3. For tables, extract all headers and rows cleanly without losing cell associations.
    4. Set 'page_number' to {page_num}.

    OUTPUT RESTRICTION:
    Return raw JSON matching this schema only:
    {schema_json}
    """
  try:
    resp = await client.generate_content(prompt, model="gemini-flash-lite", files=[img_path])
    decoded = robust_json_decode(resp.text, page_num)
    data = WebAPIPageExtraction.model_validate(decoded)
    log_step(f"[Page {page_num}] Extracted {len(data.blocks)} blocks.")
    return data
  except Exception as e:
    log_step(f"[Page {page_num}] Vision OCR failed: {e}")
    return WebAPIPageExtraction(page_number=page_num, blocks=[])

