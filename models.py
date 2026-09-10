from pydantic import BaseModel, Field


# ==========================================
# 📝 MCQ GENERATION SCHEMAS
# ==========================================
class BotMCQ(BaseModel):
  question: str = Field(
      default="",
      description=(
          "MCQ question statement in PURE ENGLISH. No numbers at start."
      ),
  )
  option_A: str = Field(default="", description="Option A in PURE ENGLISH")
  option_B: str = Field(default="", description="Option B in PURE ENGLISH")
  option_C: str = Field(default="", description="Option C in PURE ENGLISH")
  option_D: str = Field(default="", description="Option D in PURE ENGLISH")
  answer_letter: str = Field(
      default="A", description="Correct option letter (A, B, C, or D)"
  )
  answer_text: str = Field(
      default="", description="Correct answer text in PURE ENGLISH"
  )
  page_number: int = Field(
      default=1, description="Source page number of the question"
  )
  source_sentence: str = Field(
      default="", description="Contextual explanation sentence in PURE ENGLISH"
  )


class PageMCQOutput(BaseModel):
  page_number: int = Field(default=1, description="Current PDF page number")
  mcqs: list[BotMCQ] = Field(
      default_factory=list, description="List of generated practice MCQs"
  )


# ==========================================
# ✂️ SMART CHAPTER SPLIT SCHEMAS
# ==========================================
class Chapter(BaseModel):
  chapter_number: int = Field(
      default=0, description="Sequential number of the chapter"
  )
  chapter_name: str = Field(
      default="", description="Exact name/title of the chapter"
  )
  printed_page_number: int = Field(
      default=0, description="Page number printed on index"
  )


class PDFAnalysis(BaseModel):
  found_index: bool = Field(
      default=False, description="True if Table of Contents was identified"
  )
  offset: int = Field(
      default=0,
      description="Offset = Physical Image Index - Printed Page Number",
  )
  chapters: list[Chapter] = Field(
      default_factory=list, description="List of all detected chapters"
  )


# ==========================================
# 🌐 WEBAPI TEXT & TABLE EXTRACTION SCHEMAS
# ==========================================
class WebAPITableRow(BaseModel):
  cells: list[str] = Field(
      default_factory=list, description="Values for each column in this row"
  )


class WebAPITableData(BaseModel):
  headers: list[str] = Field(
      default_factory=list, description="Column headers of the table"
  )
  rows: list[WebAPITableRow] = Field(
      default_factory=list, description="Rows of the table"
  )


class WebAPIContentBlock(BaseModel):
  block_type: str = Field(
      default="text", description="Must be 'text' or 'table'"
  )
  text_content: str | None = Field(
      default=None, description="Paragraph text content"
  )
  table_content: WebAPITableData | None = Field(
      default=None, description="Table content structure"
  )


class WebAPIPageExtraction(BaseModel):
  page_number: int = Field(default=1)
  blocks: list[WebAPIContentBlock] = Field(
      default_factory=list, description="Sequential ordered content blocks"
  )

