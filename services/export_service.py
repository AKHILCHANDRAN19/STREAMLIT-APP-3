import html
import os
import pathlib
from config import FONT_PATH
from utils.text_cleaner import format_bot_txt_output

try:
  from weasyprint import HTML

  WEASYPRINT_AVAILABLE = True
except ImportError:
  WEASYPRINT_AVAILABLE = False


def save_bot_txt(mcq_list: list[dict], output_txt_path: str) -> str:
  """Writes structured MCQs into the standard bot-ready text format."""
  formatted_text = format_bot_txt_output(mcq_list)
  with open(output_txt_path, "w", encoding="utf-8") as f:
    f.write(formatted_text)
  return output_txt_path


def compile_pdf_with_weasyprint(
    mcq_list: list[dict],
    title: str,
    output_pdf_path: str,
    output_html_path: str,
) -> bool:
  """Compiles high-visibility PDFs styled via THUMBA-Bold.ttf with +10pt scaling."""
  clean_title = title.replace("_", " ")
  font_uri = pathlib.Path(os.path.abspath(FONT_PATH)).as_uri()

  html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
    @font-face {{ 
        font-family: 'ThumbaCustom'; 
        src: url('{font_uri}'); 
    }}
    body {{ 
        font-family: 'ThumbaCustom', sans-serif; 
        padding: 40px; 
        background-color: #f8fafc;
        color: #1e293b;
        font-size: 25px;
    }}
    h1 {{ 
        text-align: center; 
        color: #1a73e8; 
        font-size: 34px;
        margin-bottom: 35px;
    }}
    .container {{ 
        background: white; 
        border-radius: 12px; 
        padding: 24px 28px; 
        margin-bottom: 24px; 
        border-left: 8px solid #1a73e8; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }}
    .question {{ 
        font-size: 27px; 
        font-weight: bold; 
        margin-bottom: 16px; 
        line-height: 1.5;
        color: #0f172a;
    }}
    .options {{ 
        font-size: 25px; 
        line-height: 1.8; 
        margin-bottom: 14px;
        color: #334155;
    }}
    .answer {{ 
        margin-top: 10px; 
        color: #15803d; 
        font-weight: bold; 
        font-size: 25px; 
        background-color: #dcfce7; 
        padding: 8px 16px; 
        border-radius: 6px; 
        display: inline-block; 
    }}
    .source {{ 
        margin-top: 16px; 
        font-size: 24px; 
        color: #475569; 
        background-color: #f1f5f9;
        padding: 12px 16px;
        border-left: 4px solid #94a3b8;
        border-radius: 4px;
        line-height: 1.5;
    }}
</style></head><body><h1>{html.escape(clean_title)}</h1>
"""

  for i, mcq in enumerate(mcq_list, 1):
    q_text = html.escape(mcq.get("question", "").strip())
    p_num = mcq.get("page_number", 1)
    ans_letter = html.escape(str(mcq.get("answer_letter", "A")))
    ans_text = html.escape(mcq.get("answer_text", "").strip())
    sentence = html.escape(mcq.get("source_sentence", "").strip())

    oa = html.escape(mcq.get("option_A", "").strip())
    ob = html.escape(mcq.get("option_B", "").strip())
    oc = html.escape(mcq.get("option_C", "").strip())
    od = html.escape(mcq.get("option_D", "").strip())

    html_content += f"""
    <div class="container">
        <div class="question">{i}. {q_text} (പേജ് നമ്പർ: {p_num})</div>
        <div class="options">
            A) {oa}<br>B) {ob}<br>C) {oc}<br>D) {od}
        </div>
        <div class="answer">ഉത്തരം: {ans_letter}) {ans_text}</div>
        <div class="source">Sentence : ({sentence})</div>
    </div>"""

  html_content += "</body></html>"

  if WEASYPRINT_AVAILABLE:
    try:
      HTML(string=html_content).write_pdf(output_pdf_path)
      return True
    except Exception:
      with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
      return False
  else:
    with open(output_html_path, "w", encoding="utf-8") as f:
      f.write(html_content)
    return False

