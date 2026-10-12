"""Change-log contract models (``docs/inventory/inventory-http-contract.md`` section 2.7)."""

from __future__ import annotations

from uuid import UUID

from ...domain.tenancy import HistoryPage as HistoryPageRecord
from .common import ApiModel, Instant


class HistoryEntry(ApiModel):
    """``before`` and ``after`` are JSON text exactly as the change log stores them."""

    version: int
    section: str
    entity_id: UUID
    reason: str
    occurred_at: Instant
    actor_id: UUID
    actor_name: str
    before: str | None
    after: str | None


class HistoryPage(ApiModel):
    """``total`` is ``null`` only when the caller asked to skip the count; ``nextBefore`` is
    the last returned version when more rows follow."""

    items: list[HistoryEntry]
    page_number: int
    page_size: int
    total: int | None
    has_more: bool
    next_before: int | None

    @classmethod
    def from_page(cls, page: HistoryPageRecord, page_number: int, page_size: int) -> HistoryPage:
        return cls(
            items=[HistoryEntry.from_record(entry) for entry in page.items],
            page_number=page_number,
            page_size=page_size,
            total=page.total,
            has_more=page.has_more,
            next_before=page.next_before,
        )
