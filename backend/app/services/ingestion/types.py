from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    metadata: dict = field(default_factory=dict)
