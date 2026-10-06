from __future__ import annotations

import mimetypes
import re
import zlib
from abc import ABC, abstractmethod
from collections.abc import Iterable
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import ClassVar
from zipfile import ZipFile

import httpx

from app.core.errors import AppError
from app.services.ingestion.types import ExtractedDocument


class Extractor(ABC):
    supported_extensions: ClassVar[set[str]] = set()
    supported_mime_types: ClassVar[set[str]] = set()

    def supports(self, filename: str | None, mime_type: str | None) -> bool:
        extension = Path(filename or "").suffix.lower()
        return extension in self.supported_extensions or (mime_type or "") in self.supported_mime_types

    @abstractmethod
    def extract(self, content: bytes, *, filename: str | None, mime_type: str | None) -> ExtractedDocument:
        raise NotImplementedError


class TextExtractor(Extractor):
    supported_extensions: ClassVar[set[str]] = {".txt", ".text"}
    supported_mime_types: ClassVar[set[str]] = {"text/plain"}

    def extract(self, content: bytes, *, filename: str | None, mime_type: str | None) -> ExtractedDocument:
        return ExtractedDocument(
            text=decode_text(content),
            metadata={"extractor": "text", "filename": filename, "mime_type": mime_type},
        )


class MarkdownExtractor(Extractor):
    supported_extensions: ClassVar[set[str]] = {".md", ".markdown", ".mdx"}
    supported_mime_types: ClassVar[set[str]] = {"text/markdown", "text/x-markdown"}

    def extract(self, content: bytes, *, filename: str | None, mime_type: str | None) -> ExtractedDocument:
        return ExtractedDocument(
            text=decode_text(content),
            metadata={"extractor": "markdown", "filename": filename, "mime_type": mime_type},
        )


class CodeExtractor(Extractor):
    supported_extensions: ClassVar[set[str]] = {
        ".c",
        ".cpp",
        ".cs",
        ".css",
        ".go",
        ".html",
        ".java",
        ".js",
        ".jsx",
        ".json",
        ".kt",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".sql",
        ".ts",
        ".tsx",
        ".xml",
        ".yaml",
        ".yml",
    }
    supported_mime_types: ClassVar[set[str]] = {
        "application/json",
        "application/javascript",
        "application/x-python-code",
        "text/css",
        "text/html",
        "text/javascript",
        "text/x-python",
        "text/xml",
    }

    def extract(self, content: bytes, *, filename: str | None, mime_type: str | None) -> ExtractedDocument:
        return ExtractedDocument(
            text=decode_text(content),
            metadata={
                "extractor": "code",
                "filename": filename,
                "mime_type": mime_type,
                "language": Path(filename or "").suffix.lower().lstrip(".") or None,
            },
        )


class DocxExtractor(Extractor):
    supported_extensions: ClassVar[set[str]] = {".docx"}
    supported_mime_types: ClassVar[set[str]] = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    def extract(self, content: bytes, *, filename: str | None, mime_type: str | None) -> ExtractedDocument:
        try:
            with ZipFile(BytesIO(content)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
        except Exception as exc:
            raise AppError("Could not extract text from DOCX file.") from exc

        text = docx_xml_to_text(xml)
        return ExtractedDocument(
            text=text,
            metadata={"extractor": "docx", "filename": filename, "mime_type": mime_type},
        )


class PdfExtractor(Extractor):
    supported_extensions: ClassVar[set[str]] = {".pdf"}
    supported_mime_types: ClassVar[set[str]] = {"application/pdf"}

    def extract(self, content: bytes, *, filename: str | None, mime_type: str | None) -> ExtractedDocument:
        text = self._extract_with_pypdf(content)
        extractor = "pypdf"
        if text is None:
            text = extract_pdf_text_basic(content)
            extractor = "pdf-basic"
        return ExtractedDocument(
            text=text,
            metadata={"extractor": extractor, "filename": filename, "mime_type": mime_type},
        )

    def _extract_with_pypdf(self, content: bytes) -> str | None:
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise AppError("Could not extract text from PDF file.") from exc


class HtmlTextParser(HTMLParser):
    hidden_tags: ClassVar[set[str]] = {"script", "style", "noscript", "svg"}
    block_tags: ClassVar[set[str]] = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0
        self.title: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.hidden_tags:
            self.hidden_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.hidden_tags and self.hidden_depth:
            self.hidden_depth -= 1
        if tag == "title":
            self._in_title = False
            title = " ".join(self._title_parts).strip()
            self.title = title or None
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if not self.hidden_depth and not self._in_title:
            self.parts.append(data)

    @property
    def text(self) -> str:
        return " ".join("".join(self.parts).split())


class UrlExtractor:
    max_response_bytes: int

    def __init__(self, max_response_bytes: int) -> None:
        self.max_response_bytes = max_response_bytes

    def extract(self, url: str) -> ExtractedDocument:
        try:
            with (
                httpx.Client(follow_redirects=True, timeout=15.0) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                final_url = str(response.url)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self.max_response_bytes:
                        raise AppError("URL response exceeds maximum ingestion size.")
        except httpx.HTTPError as exc:
            raise AppError("Could not fetch URL.") from exc

        text = decode_text(bytes(content))
        metadata: dict = {
            "extractor": "url",
            "url": final_url,
            "content_type": content_type or None,
            "bytes": len(content),
        }
        if "html" in content_type:
            parser = HtmlTextParser()
            parser.feed(text)
            text = parser.text
            metadata["title"] = parser.title
        return ExtractedDocument(text=text, metadata=metadata)


class ExtractorRegistry:
    def __init__(self, extractors: Iterable[Extractor] | None = None) -> None:
        self.extractors = list(
            extractors
            or [
                PdfExtractor(),
                DocxExtractor(),
                MarkdownExtractor(),
                CodeExtractor(),
                TextExtractor(),
            ]
        )

    def for_file(self, filename: str | None, mime_type: str | None) -> Extractor:
        guessed_type, _ = mimetypes.guess_type(filename or "")
        for extractor in self.extractors:
            if extractor.supports(filename, mime_type) or extractor.supports(filename, guessed_type):
                return extractor
        raise AppError("Unsupported file type.")


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def docx_xml_to_text(xml: str) -> str:
    xml = re.sub(r"</w:p[^>]*>", "\n", xml)
    xml = re.sub(r"</w:tab[^>]*/?>", "\t", xml)
    values = re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", xml, flags=re.DOTALL)
    return "\n".join(unescape_xml(value) for value in values)


def unescape_xml(value: str) -> str:
    return (
        value.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )


def extract_pdf_text_basic(content: bytes) -> str:
    try:
        raw = content.decode("latin-1")
    except UnicodeDecodeError as exc:
        raise AppError("Could not decode PDF file.") from exc

    streams = re.findall(r"stream\r?\n(.*?)\r?\nendstream", raw, flags=re.DOTALL)
    text_parts: list[str] = []
    for stream in streams:
        stream_bytes = stream.encode("latin-1")
        decoded_streams = [stream]
        try:
            decoded_streams.append(zlib.decompress(stream_bytes).decode("latin-1"))
        except zlib.error:
            pass
        for candidate in decoded_streams:
            text_parts.extend(parse_pdf_text_operators(candidate))
    return "\n".join(text_parts)


def parse_pdf_text_operators(stream: str) -> list[str]:
    parts: list[str] = []
    for value in re.findall(r"\((.*?)\)\s*T[Jj]", stream, flags=re.DOTALL):
        parts.append(unescape_pdf_string(value))
    for array in re.findall(r"\[(.*?)\]\s*TJ", stream, flags=re.DOTALL):
        pieces = re.findall(r"\((.*?)\)", array, flags=re.DOTALL)
        if pieces:
            parts.append("".join(unescape_pdf_string(piece) for piece in pieces))
    return parts


def unescape_pdf_string(value: str) -> str:
    return (
        value.replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
    )
