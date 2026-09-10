import asyncio
import json
import logging
import re
from config import DELAY_BETWEEN_PAGES, EXTRA_MCQS, get_gemini_credentials
from gemini_webapi import GeminiClient
from models import PageMCQOutput, PDFAnalysis, WebAPIPageExtraction
from utils.json_cleaner import robust_json_decode
from utils.text_cleaner import clean_markdown_artifacts

logger = logging.getLogger("Gemini_Service")


async def init_gemini_client() -> GeminiClient:
  """Initializes and returns an authenticated Gemini WebAPI client."""
  psid, psidts = get_gemini_credentials()
  client = GeminiClient(psid, psidts, proxy=None)
  await client.init(
      timeout=45, auto_close=False, close_delay=300, auto_refresh=True
  )
  return client


async def analyze_document_title(chat, first_page_img: str) -> str:
  """Extracts a short 3-4 word title for document naming."""
  prompt = (
      "Analyze this page. Create a very short, catchy title (maximum 3 to 4"
      " words) in English. Do NOT use underscores. Output ONLY the title."
  )
  try:
    resp = await chat.send_message(prompt, files=[first_page_img])
    clean_title = re.sub(r"[^a-zA-Z0-9\s]", "", resp.text.strip())
    return " ".join(clean_title.split()) or "Document_Output"
  except Exception as e:
    logger.warning(f"Title generation failed: {e}. Using fallback.")
    return "Document_Output"


async def extract_table_of_contents(
    chat, image_paths: list[str]
) -> PDFAnalysis:
  """Scans first 15 pages to locate the Index/TOC and compute the mathematical page offset."""
  schema_json = json.dumps(PDFAnalysis.model_json_schema(), indent=2)
  prompt = f"""
    Analyze these uploaded document preview pages.
    Image 0 corresponds to Physical Page Index 0, Image 1 to Index 1, etc.

    TASK:
    1. Locate the Table of Contents (Index).
    2. Extract chapter numbers, chapter names, and their printed page numbers.
    3. Calculate 'offset' = Physical Image Index - Printed Page Number.

    OUTPUT RESTRICTION:
    Return raw JSON matching this schema only:
    {schema_json}
    """
  resp = await chat.send_message(prompt, files=image_paths)
  decoded = robust_json_decode(resp.text)
  return PDFAnalysis.model_validate(decoded)


async def verify_chapter_page(
    chat, img_path: str, chap_num: int, chap_name: str
) -> bool:
  """Performs single-page visual verification before PDF slicing."""
  prompt = f"""
    Look at this single uploaded page.
    Does this page contain the starting title/heading for Chapter {chap_num}: '{chap_name}'?
    Reply STRICTLY with only 'YES' or 'NO'.
    """
  try:
    resp = await chat.send_message(prompt, files=[img_path])
    return "YES" in resp.text.strip().upper()
  except Exception:
    return False


async def generate_mcqs_for_page(
    chat,
    page_img: str,
    page_num: int,
    doc_type: str = "pointwise",
    max_retries: int = 3,
) -> PageMCQOutput:
  """Processes a single page image inside an active chat session to generate MCQs."""
  schema_json = json.dumps(PageMCQOutput.model_json_schema(), indent=2)

  # Phase 1: Count Target Questions
  count_prompt = f"""
    Analyze Page {page_num} attached. 
    Count the distinct factual statements, definitions, vocabulary pairs, or table rows on this page.
    Return ONLY a JSON object: {{"max_potential_mcqs": 0}}
    """
  target_mcqs = EXTRA_MCQS
  try:
    count_resp = await chat.send_message(count_prompt, files=[page_img])
    decoded_count = robust_json_decode(count_resp.text, page_num)
    target_mcqs = decoded_count.get("max_potential_mcqs", 0) + EXTRA_MCQS
  except Exception as e:
    logger.warning(
        f"Counting phase failed on page {page_num}: {e}. Using target"
        f" {target_mcqs}"
    )

  await asyncio.sleep(1)

  # Phase 2: Synthesis
  gen_prompt = f"""
    Generate exactly {target_mcqs} comprehensive MCQs strictly originating from this uploaded page (Page {page_num}).

    RULES:
    1. If words have multiple synonyms/antonyms/facts, test them from different angles without word-for-word duplication.
    2. Write question stems, choices A, B, C, D, answer_text, and source_sentence in the native language of the source text.
    3. Ensure no trailing commas. Set 'page_number' to {page_num}.

    OUTPUT RESTRICTION:
    Return ONLY valid JSON matching this schema:
    {schema_json}
    """

  for attempt in range(1, max_retries + 1):
    try:
      resp = await chat.send_message(gen_prompt)
      decoded = robust_json_decode(resp.text, page_num)
      validated = PageMCQOutput.model_validate(decoded)
      validated.page_number = page_num
      return validated
    except Exception as e:
      logger.warning(
          f"MCQ generation attempt {attempt} failed on page {page_num}: {e}"
      )
      if attempt < max_retries:
        await asyncio.sleep(DELAY_BETWEEN_PAGES)
      else:
        return PageMCQOutput(page_number=page_num, mcqs=[])


async def extract_text_and_tables_webapi(
    client: GeminiClient, img_path: str, page_num: int
) -> WebAPIPageExtraction:
  """Extracts clean text paragraphs and preserves structured table data."""
  schema_json = json.dumps(WebAPIPageExtraction.model_json_schema(), indent=2)
  prompt = f"""
    Analyze this page image (Page {page_num}). Extract all paragraphs and tables.
    Do NOT summarize. Do not use markdown headers (no ###) or asterisks.
    For tables, duplicate merged cells into corresponding rows so data is preserved.
    Set 'page_number' to {page_num}.

    OUTPUT RESTRICTION:
    Return raw JSON matching this schema only:
    {schema_json}
    """
  try:
    resp = await client.generate_content(
        prompt, model="gemini-3-flash", files=[img_path]
    )
    decoded = robust_json_decode(resp.text, page_num)
    return WebAPIPageExtraction.model_validate(decoded)
  except Exception as e:
    logger.error(f"Text/Table extraction error on page {page_num}: {e}")
    return WebAPIPageExtraction(page_number=page_num, blocks=[])

