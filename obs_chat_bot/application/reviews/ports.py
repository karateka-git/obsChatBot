"""Ports подготовки типизированного Obsidian-предложения."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from obs_chat_bot.application.search.models import VaultSearchResult
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.reviews.entities import ObsidianReviewPlan
from obs_chat_bot.domain.search.entities import ArticleSearchQuery
from obs_chat_bot.domain.vaults.entities import VaultInstruction, VaultNote


@dataclass(frozen=True, slots=True)
class ObsidianPlanningContext:
    """Контекст выбора действия и целевого раздела vault."""

    article: Article
    analysis: ArticleAnalysisResult
    instructions: tuple[VaultInstruction, ...]
    search_result: VaultSearchResult
    note_catalog: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True, slots=True)
class ObsidianWritingContext:
    """Контекст генерации Markdown после чтения целевой и соседних заметок."""

    article: Article
    analysis: ArticleAnalysisResult
    instructions: tuple[VaultInstruction, ...]
    plan: ObsidianReviewPlan
    target_note: VaultNote | None
    neighboring_notes: tuple[VaultNote, ...]
    relevant_notes: tuple[VaultNote, ...]


class VaultArticleSearch(Protocol):
    """Описывает hybrid retrieval для одной проанализированной статьи."""

    def search(
        self,
        *,
        query: ArticleSearchQuery,
        vault_id: int,
        candidate_limit: int = 20,
        result_limit: int = 10,
    ) -> VaultSearchResult:
        """Возвращает релевантные chunks активного vault."""


class ObsidianProposalGenerator(Protocol):
    """Описывает двухфазную LLM-подготовку изменения vault."""

    def plan(self, context: ObsidianPlanningContext) -> ObsidianReviewPlan:
        """Выбирает `add`, `update` или `skip` и безопасный целевой путь."""

    def write_markdown(self, context: ObsidianWritingContext) -> str:
        """Генерирует полный Markdown после загрузки соседних заметок."""
