from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArticleStatus(StrEnum):
    NEW = "new"
    FETCHING = "fetching"
    EXTRACTED = "extracted"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    NEEDS_OBSIDIAN_REVIEW = "needs_obsidian_review"
    REVIEWED = "reviewed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Article:
    source_url: str
    normalized_url: str
    id: int | None = None
    title: str | None = None
    cleaned_text: str | None = None
    text_hash: str | None = None
    status: ArticleStatus = ArticleStatus.NEW
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_url.strip():
            raise ValueError("source_url must not be empty")
        if not self.normalized_url.strip():
            raise ValueError("normalized_url must not be empty")
        if not isinstance(self.status, ArticleStatus):
            raise TypeError("status must be an ArticleStatus")
