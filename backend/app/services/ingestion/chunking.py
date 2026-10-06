from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    content: str
    index: int
    start_char: int
    end_char: int


class TextChunker:
    def __init__(self, chunk_size: int = 1200, overlap: int = 150) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be greater than or equal to 0 and smaller than chunk_size.")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[TextChunk]:
        if not text:
            return []

        chunks: list[TextChunk] = []
        start = 0
        text_length = len(text)
        while start < text_length:
            hard_end = min(start + self.chunk_size, text_length)
            end = self._find_boundary(text, start, hard_end)
            content = text[start:end].strip()
            if content:
                chunks.append(
                    TextChunk(
                        content=content,
                        index=len(chunks),
                        start_char=start,
                        end_char=end,
                    )
                )
            if hard_end >= text_length:
                break
            start = max(end - self.overlap, start + 1)
            while start < text_length and text[start].isspace():
                start += 1
        return chunks

    def _find_boundary(self, text: str, start: int, hard_end: int) -> int:
        if hard_end == len(text):
            return hard_end
        window = text[start:hard_end]
        for separator in ("\n\n", "\n", ". ", " "):
            boundary = window.rfind(separator)
            if boundary >= self.chunk_size // 2:
                return start + boundary + len(separator)
        return hard_end
