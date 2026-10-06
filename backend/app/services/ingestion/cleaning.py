import re

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"[ \t]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = CONTROL_CHARS_RE.sub("", normalized)
    normalized = "\n".join(WHITESPACE_RE.sub(" ", line).strip() for line in normalized.split("\n"))
    normalized = BLANK_LINES_RE.sub("\n\n", normalized)
    return normalized.strip()
