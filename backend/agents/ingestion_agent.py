"""
Ingestion Agent — LangGraph node responsible for:
  1. Parsing uploaded PDF or Markdown runbooks
  2. Chunking content (size=512, overlap=64 tokens)
  3. Embedding chunks and storing them in ChromaDB with rich metadata
"""
import logging
import os
import re
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from vector_store import add_documents, COLLECTION_NAME

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


# ── State ──────────────────────────────────────────────────────────────────────

class IngestionState(TypedDict):
    file_path: str
    original_filename: str
    file_type: str          # "pdf" | "md"
    runbook_id: int
    # outputs
    chunks: list[Document]
    chunk_count: int
    error: str | None
    status: str             # "processing" | "indexed" | "failed"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_markdown(file_path: str) -> list[dict]:
    """
    Parse a Markdown file into sections.
    Returns list of {content, section_title, page_number (section index)}.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read()

    sections: list[dict] = []
    current_title = "Introduction"
    current_lines: list[str] = []
    section_idx = 0

    for line in raw.splitlines(keepends=True):
        heading_match = re.match(r"^(#{1,3})\s+(.+)", line)
        if heading_match:
            if current_lines:
                sections.append({
                    "content": "".join(current_lines).strip(),
                    "section_title": current_title,
                    "page_number": section_idx,
                })
                section_idx += 1
                current_lines = []
            current_title = heading_match.group(2).strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "content": "".join(current_lines).strip(),
            "section_title": current_title,
            "page_number": section_idx,
        })

    return [s for s in sections if s["content"]]


def _parse_pdf(file_path: str) -> list[dict]:
    """Parse a PDF into pages using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF is required for PDF parsing. Install with: pip install pymupdf")

    sections: list[dict] = []
    doc = fitz.open(file_path)
    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            sections.append({
                "content": text,
                "section_title": f"Page {page_num + 1}",
                "page_number": page_num + 1,
            })
    doc.close()
    return sections


def _build_documents(
    sections: list[dict],
    source_file: str,
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """Split each section into chunks and attach metadata."""
    docs: list[Document] = []
    for section in sections:
        chunks = splitter.split_text(section["content"])
        for chunk_idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            doc = Document(
                page_content=chunk,
                metadata={
                    "source_file": source_file,
                    "section_title": section["section_title"],
                    "page_number": section["page_number"],
                    "chunk_index": chunk_idx,
                },
            )
            docs.append(doc)
    return docs


# ── LangGraph node function ────────────────────────────────────────────────────

def ingestion_node(state: IngestionState) -> IngestionState:
    """
    LangGraph node: parse → chunk → embed → store runbook.
    Updates state with chunk_count, status, and error.
    """
    file_path = state["file_path"]
    file_type = state["file_type"].lower().lstrip(".")
    source_file = state["original_filename"]

    logger.info("Ingestion agent started for: %s", source_file)

    try:
        # 1. Parse
        if file_type == "md":
            sections = _parse_markdown(file_path)
        elif file_type == "pdf":
            sections = _parse_pdf(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        if not sections:
            raise ValueError("No content could be extracted from the file.")

        # 2. Chunk
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""],
        )
        docs = _build_documents(sections, source_file, splitter)

        if not docs:
            raise ValueError("Chunking produced zero documents.")

        # 3. Embed + store
        add_documents(docs, collection_name=COLLECTION_NAME)

        logger.info("Ingestion complete: %d chunks indexed for %s", len(docs), source_file)

        return {
            **state,
            "chunks": docs,
            "chunk_count": len(docs),
            "status": "indexed",
            "error": None,
        }

    except Exception as exc:
        logger.exception("Ingestion agent failed for %s: %s", source_file, exc)
        return {
            **state,
            "chunks": [],
            "chunk_count": 0,
            "status": "failed",
            "error": str(exc),
        }
