import os
import re
import uuid
from urllib.parse import urlparse, parse_qs


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


def chunk_text(text: str, chunk_size: int = 400, overlap_sentences: int = 2) -> list[str]:
    sentences = re.split(r"(?<=[.!?]) +(?=[A-Z])", text.strip())
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        return [text.strip()] if text.strip() else []

    chunks = []
    current: list[str] = []
    current_words = 0

    for sent in sentences:
        words = len(sent.split())
        if current_words + words > chunk_size and current:
            chunks.append(" ".join(current))
            tail = current[-overlap_sentences:] if len(current) >= overlap_sentences else current[:]
            current = tail[:]
            current_words = sum(len(s.split()) for s in current)
        current.append(sent)
        current_words += words

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]


def extract_pdf(path: str) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    sections = []
    last_chapter = ""
    heading_patterns = [
        # All-caps heading: letters/spaces only, 3–50 chars (filters out long paragraphs and single chars)
        re.compile(r"^[A-Z][A-Z\s]{2,48}[A-Z]$"),
        re.compile(r"^Chapter\s+\d+", re.I),
        re.compile(r"^Section\s+\d+", re.I),
        # Numbered: "1.", "1.1", "1.1.1" followed by a capital word
        re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z][a-z]"),
    ]
    # Lines that look like headings but aren't (page numbers, dates, short noise)
    _noise = re.compile(r"^\d+$|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")

    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        chapter = ""
        for line in text.split("\n")[:10]:  # headings appear near the top of a page
            line = line.strip()
            if not line or _noise.match(line):
                continue
            if any(p.match(line) for p in heading_patterns):
                chapter = line
                break
        if chapter:
            last_chapter = chapter
        sections.append({
            "text": text,
            "chapter": last_chapter,
            "page": i,
            "timestamp_seconds": 0,
        })

    return sections


def extract_epub(path: str) -> list[dict]:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(path)
    sections = []

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        if not text.strip():
            continue
        heading = soup.find(["h1", "h2", "h3"])
        chapter = heading.get_text(strip=True) if heading else ""
        sections.append({
            "text": text,
            "chapter": chapter,
            "page": 0,
            "timestamp_seconds": 0,
        })

    return sections


def _extract_web_title(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else ""


def extract_web(url: str) -> tuple[str, list[dict]]:
    import trafilatura
    from bs4 import BeautifulSoup

    html = trafilatura.fetch_url(url)
    if not html:
        raise ValueError(f"Could not fetch URL: {url}")

    source_title = _extract_web_title(html) or url

    content = trafilatura.extract(html, include_tables=True, include_links=False) or ""

    soup = BeautifulSoup(html, "html.parser")
    headings = soup.find_all(["h2", "h3"])
    heading_texts = [h.get_text(strip=True) for h in headings if h.get_text(strip=True)]

    if not heading_texts:
        return source_title, [{
            "text": content,
            "chapter": "",
            "page": 0,
            "timestamp_seconds": 0,
        }]

    # Split content on heading lines
    sections = []
    current_chapter = ""
    current_lines: list[str] = []

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped in heading_texts:
            if current_lines:
                sections.append({
                    "text": "\n".join(current_lines),
                    "chapter": current_chapter,
                    "page": 0,
                    "timestamp_seconds": 0,
                })
            current_chapter = stripped
            current_lines = []
        elif stripped:
            current_lines.append(stripped)

    if current_lines:
        sections.append({
            "text": "\n".join(current_lines),
            "chapter": current_chapter,
            "page": 0,
            "timestamp_seconds": 0,
        })

    return source_title, sections if sections else [{
        "text": content,
        "chapter": "",
        "page": 0,
        "timestamp_seconds": 0,
    }]


def extract_video(url: str) -> tuple[str, list[dict]]:
    import requests
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )

    if "youtu.be" in url:
        video_id = url.split("/")[-1].split("?")[0]
    else:
        params = parse_qs(urlparse(url).query)
        video_id = params.get("v", [""])[0]

    if not video_id:
        raise ValueError(f"Could not extract video ID from: {url}")

    try:
        resp = requests.get(
            f"https://www.youtube.com/oembed?url={url}&format=json", timeout=10
        )
        source_title = resp.json().get("title", video_id) if resp.ok else video_id
    except Exception:
        source_title = video_id

    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
    except TranscriptsDisabled:
        raise ValueError(f"Transcripts disabled for video: {video_id}")
    except NoTranscriptFound:
        raise ValueError(f"No transcript found for video: {video_id}")
    except VideoUnavailable:
        raise ValueError(f"Video unavailable: {video_id}")

    sections = []
    current_texts: list[str] = []
    section_start = 0.0
    section_duration = 0.0

    for snippet in transcript:
        if not current_texts:
            section_start = snippet.start
        current_texts.append(snippet.text)
        section_duration += snippet.duration

        if section_duration >= 180:
            t = int(section_start)
            sections.append({
                "text": " ".join(current_texts),
                "chapter": f"{t // 60}:{t % 60:02d}",
                "page": 0,
                "timestamp_seconds": t,
            })
            current_texts = []
            section_start = snippet.start + snippet.duration
            section_duration = 0.0

    if current_texts:
        t = int(section_start)
        sections.append({
            "text": " ".join(current_texts),
            "chapter": f"{t // 60}:{t % 60:02d}",
            "page": 0,
            "timestamp_seconds": t,
        })

    return source_title, sections


def extract_text(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    is_md = path.endswith(".md")
    sections = []
    current_chapter = ""

    for para in content.split("\n\n"):
        stripped = para.strip()
        if not stripped:
            continue
        if is_md:
            for line in stripped.split("\n"):
                if line.startswith("## ") or line.startswith("### "):
                    current_chapter = line.lstrip("#").strip()
                    break
        sections.append({
            "text": stripped,
            "chapter": current_chapter,
            "page": 0,
            "timestamp_seconds": 0,
        })

    return sections


def ingest_source(path_or_url: str, topic_slug: str, source_id: int) -> tuple[str, list[dict]]:
    lower = path_or_url.lower()

    if lower.startswith("http://") or lower.startswith("https://"):
        if "youtube.com" in lower or "youtu.be" in lower:
            source_title, sections = extract_video(path_or_url)
            source_type = "video"
        else:
            source_title, sections = extract_web(path_or_url)
            source_type = "web"
    elif lower.endswith(".pdf"):
        sections = extract_pdf(path_or_url)
        source_title = os.path.splitext(os.path.basename(path_or_url))[0]
        source_type = "pdf"
    elif lower.endswith(".epub"):
        sections = extract_epub(path_or_url)
        source_title = os.path.splitext(os.path.basename(path_or_url))[0]
        source_type = "epub"
    elif lower.endswith(".txt") or lower.endswith(".md"):
        sections = extract_text(path_or_url)
        source_title = os.path.splitext(os.path.basename(path_or_url))[0]
        source_type = "text"
    else:
        raise ValueError(f"Unsupported source: {path_or_url}")

    chunks = []
    chapter_index = -1
    last_chapter = None

    for section in sections:
        chapter = section["chapter"]
        if chapter != last_chapter:
            chapter_index += 1
            last_chapter = chapter

        for chunk_idx, text in enumerate(chunk_text(section["text"])):
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": text,
                "metadata": {
                    "topic": topic_slug,
                    "source_id": source_id,
                    "source_ref": path_or_url,
                    "source_title": source_title,
                    "source_type": source_type,
                    "kind": "chunk",
                    "chapter": chapter,
                    "chapter_index": chapter_index,
                    "chunk_index": chunk_idx,
                    "page": section["page"],
                    "timestamp_seconds": section["timestamp_seconds"],
                },
            })

    return source_title, chunks
