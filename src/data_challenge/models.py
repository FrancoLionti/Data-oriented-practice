"""Internal data structures shared by ingestion and pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar


SourceName = Literal["crm", "market", "interactions"]
RawRecord = dict[str, Any]


@dataclass(frozen=True, slots=True)
class RejectedRecord:
    source: SourceName
    source_record_id: str
    reason: str
    raw_record: RawRecord


@dataclass(frozen=True, slots=True)
class CRMRecord:
    crm_id: str
    name: str | None
    domain: str | None
    founded_year: int | None
    hq_country: str | None
    last_updated: datetime | None
    status: str | None
    quality_flags: tuple[str, ...]
    raw_record: RawRecord


@dataclass(frozen=True, slots=True)
class MarketRecord:
    market_id: str
    company_name: str | None
    domain: str | None
    legal_name: str | None
    funding_total_usd: int | None
    employee_count: int | None
    observed_at: datetime | None
    quality_flags: tuple[str, ...]
    raw_record: RawRecord


@dataclass(frozen=True, slots=True)
class InteractionRecord:
    interaction_id: str
    company_ref: str | None
    company_name: str | None
    email_domain: str | None
    occurred_at: datetime | None
    interaction_type: str | None
    quality_flags: tuple[str, ...]
    raw_record: RawRecord


RecordT = TypeVar("RecordT")


@dataclass(frozen=True, slots=True)
class SourceReadResult(Generic[RecordT]):
    records: tuple[RecordT, ...]
    rejects: tuple[RejectedRecord, ...]


@dataclass(frozen=True, slots=True)
class IngestedData:
    crm_records: tuple[CRMRecord, ...]
    market_records: tuple[MarketRecord, ...]
    interaction_records: tuple[InteractionRecord, ...]
    rejects: tuple[RejectedRecord, ...]


@dataclass(frozen=True, slots=True)
class CanonicalCompany:
    """Represent one fully resolved company ready for the public JSONL contract."""

    company_id: str
    canonical_name: str | None
    domain: str | None
    legal_name: str | None
    founded_year: int | None
    hq_country: str | None
    status: str | None
    funding_total_usd: int | None
    employee_count: int | None
    aliases: tuple[str, ...]
    crm_source_ids: tuple[str, ...]
    market_source_ids: tuple[str, ...]
    last_activity_at: str | None
    interaction_count: int
    quality_flags: tuple[str, ...]

    def as_dict(self) -> RawRecord:
        return {
            "company_id": self.company_id,
            "canonical_name": self.canonical_name,
            "domain": self.domain,
            "legal_name": self.legal_name,
            "founded_year": self.founded_year,
            "hq_country": self.hq_country,
            "status": self.status,
            "funding_total_usd": self.funding_total_usd,
            "employee_count": self.employee_count,
            "aliases": list(self.aliases),
            "source_ids": {
                "crm": list(self.crm_source_ids),
                "market": list(self.market_source_ids),
            },
            "last_activity_at": self.last_activity_at,
            "interaction_count": self.interaction_count,
            "quality_flags": list(self.quality_flags),
        }


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Contain the canonical companies and rejected records from one build."""

    companies: tuple[CanonicalCompany, ...]
    rejects: tuple[RejectedRecord, ...]
