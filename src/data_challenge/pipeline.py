"""Deterministic entity resolution, aggregation, and JSONL output."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from data_challenge.ingestion import load_inputs
from data_challenge.models import (
    BuildResult,
    CRMRecord,
    CanonicalCompany,
    IngestedData,
    InteractionRecord,
    MarketRecord,
    RawRecord,
    RejectedRecord,
)
from data_challenge.normalization import format_timestamp, normalize_name


class PipelineError(ValueError):
    """Signal a condition that prevents a safe complete build."""


@dataclass(eq=False, slots=True)
class _Company:
    """Accumulate source observations while a canonical company is resolved.

    The accumulator is mutable only within this module. ``build_dataset``
    converts it into an immutable ``CanonicalCompany`` after matching and
    aggregation complete.
    """

    crm_records: list[CRMRecord] = field(default_factory=list)
    market_records: list[MarketRecord] = field(default_factory=list)
    aliases: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)
    interaction_times: dict[str, datetime | None] = field(default_factory=dict)
    quality_flags: set[str] = field(default_factory=set)

    def add_crm(self, record: CRMRecord) -> None:
        """Add one CRM observation and its directly observed attributes."""

        self.crm_records.append(record)
        if record.name:
            self.aliases.add(record.name)
        if record.domain:
            self.domains.add(record.domain)
        self.quality_flags.update(record.quality_flags)

    def add_market(self, record: MarketRecord) -> None:
        """Add one market-data observation and its directly observed attributes."""

        self.market_records.append(record)
        if record.company_name:
            self.aliases.add(record.company_name)
        if record.domain:
            self.domains.add(record.domain)
        self.quality_flags.update(record.quality_flags)


def _raw_key(raw_record: RawRecord) -> str:
    """Return a stable representation used only to break otherwise equal ties."""

    return json.dumps(raw_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _crm_order(record: CRMRecord) -> tuple[bool, datetime, str, str]:
    """Rank CRM observations by valid update time, then deterministic tie-breakers."""

    return (
        record.last_updated is not None,
        record.last_updated or datetime.min.replace(tzinfo=UTC),
        record.crm_id,
        _raw_key(record.raw_record),
    )


def _market_order(record: MarketRecord) -> tuple[bool, datetime, str, str]:
    """Rank market observations by valid observation time and stable tie-breakers."""

    return (
        record.observed_at is not None,
        record.observed_at or datetime.min.replace(tzinfo=UTC),
        record.market_id,
        _raw_key(record.raw_record),
    )


def _company_order(company: _Company) -> tuple[str, str]:
    """Provide a stable order for choosing a merge target."""

    crm_id = min((record.crm_id for record in company.crm_records), default="~")
    market_id = min((record.market_id for record in company.market_records), default="~")
    return crm_id, market_id


def _company_name_keys(company: _Company) -> set[str]:
    """Return all safe normalized name keys observed for a company."""

    return {
        normalized
        for name in company.aliases
        if (normalized := normalize_name(name)) is not None
    }


def _name_candidates(name: str | None, companies: list[_Company]) -> list[_Company]:
    """Find companies with an exactly matching normalized observed name."""

    normalized = normalize_name(name)
    if normalized is None:
        return []
    return [company for company in companies if normalized in _company_name_keys(company)]


def _rewire_index(index: dict[str, _Company], source: _Company, target: _Company) -> None:
    """Point every index entry that used ``source`` to ``target`` after a merge."""

    for key, company in tuple(index.items()):
        if company is source:
            index[key] = target


def _merge_companies(
    target: _Company,
    source: _Company,
    companies: list[_Company],
    by_crm_id: dict[str, _Company],
    by_domain: dict[str, _Company],
) -> None:
    """Merge two companies linked by strong CRM or domain evidence.

    The caller has already established that the shared CRM identifier or exact
    normalized domain makes the merge safe. All indexes are rewired so later
    records observe the merged entity.
    """

    if target is source:
        return
    target.crm_records.extend(source.crm_records)
    target.market_records.extend(source.market_records)
    target.aliases.update(source.aliases)
    target.domains.update(source.domains)
    target.interaction_times.update(source.interaction_times)
    target.quality_flags.update(source.quality_flags)
    companies.remove(source)
    _rewire_index(by_crm_id, source, target)
    _rewire_index(by_domain, source, target)


def _build_crm_companies(
    records: tuple[CRMRecord, ...],
) -> tuple[list[_Company], dict[str, _Company], dict[str, _Company]]:
    """Create initial companies from CRM records and build identity indexes.

    CRM identifiers and normalized domains are strong identity signals. A name
    can attach a domainless CRM record only when it identifies one candidate;
    records with different valid domains are therefore kept separate.
    """

    companies: list[_Company] = []
    by_crm_id: dict[str, _Company] = {}
    by_domain: dict[str, _Company] = {}

    ordered_records = sorted(
        records,
        key=lambda record: (
            record.domain is None,
            record.crm_id,
            _raw_key(record.raw_record),
        ),
    )
    for record in ordered_records:
        candidates = {
            company
            for company in (
                by_crm_id.get(record.crm_id),
                by_domain.get(record.domain) if record.domain else None,
            )
            if company is not None
        }

        if candidates:
            company = min(candidates, key=_company_order)
            for other in sorted(candidates - {company}, key=_company_order):
                _merge_companies(company, other, companies, by_crm_id, by_domain)
        else:
            name_matches = _name_candidates(record.name, companies)
            if record.domain:
                name_matches = [candidate for candidate in name_matches if not candidate.domains]
            if len(name_matches) == 1:
                company = name_matches[0]
            else:
                company = _Company()
                if len(name_matches) > 1:
                    company.quality_flags.add("ambiguous_crm_name")
                companies.append(company)

        company.add_crm(record)
        by_crm_id[record.crm_id] = company
        if record.domain:
            by_domain[record.domain] = company

    return companies, by_crm_id, by_domain


def _market_reject(record: MarketRecord, reason: str) -> RejectedRecord:
    """Create a consistently shaped rejection for a market observation."""

    return RejectedRecord("market", record.market_id, reason, record.raw_record)


def _attach_market_records(
    records: tuple[MarketRecord, ...],
    companies: list[_Company],
    by_domain: dict[str, _Company],
) -> list[RejectedRecord]:
    """Attach market observations using domain first and safe name fallback.

    A market record with a new domain may enrich one domainless name match. It
    never joins a company that already has a different valid domain merely
    because the names resemble one another.
    """

    rejects: list[RejectedRecord] = []
    for record in sorted(records, key=lambda item: (item.market_id, _raw_key(item.raw_record))):
        company = by_domain.get(record.domain) if record.domain else None

        if company is None and record.domain:
            domainless_matches = [
                candidate
                for candidate in _name_candidates(record.company_name, companies)
                if not candidate.domains
            ]
            if len(domainless_matches) == 1:
                company = domainless_matches[0]

        if company is None and record.domain is None:
            name_matches = _name_candidates(record.company_name, companies)
            if len(name_matches) == 1:
                company = name_matches[0]
            elif len(name_matches) > 1:
                rejects.append(_market_reject(record, "ambiguous_company_name"))
                continue

        if company is None:
            company = _Company()
            if record.domain and _name_candidates(record.company_name, companies):
                company.quality_flags.add("name_collision_different_domain")
            companies.append(company)

        company.add_market(record)
        if record.domain:
            by_domain[record.domain] = company

    return rejects


def _interaction_reject(record: InteractionRecord, reason: str) -> RejectedRecord:
    """Create a consistently shaped rejection for an interaction."""

    return RejectedRecord("interactions", record.interaction_id, reason, record.raw_record)


def _resolve_interaction(
    record: InteractionRecord,
    companies: list[_Company],
    by_crm_id: dict[str, _Company],
    by_domain: dict[str, _Company],
) -> tuple[_Company | None, set[str], RejectedRecord | None]:
    """Resolve one interaction without mutating a company.

    A valid CRM reference takes precedence. Otherwise a known domain is used,
    followed by a name only when no usable domain was supplied and the name has
    exactly one candidate. The returned flags describe data-quality concerns
    that apply if the interaction is ultimately attached.
    """

    flags = set(record.quality_flags)
    referenced = by_crm_id.get(record.company_ref) if record.company_ref else None
    domain_match = by_domain.get(record.email_domain) if record.email_domain else None

    if referenced is not None:
        if record.email_domain and domain_match is not referenced:
            flags.add("interaction_identity_conflict")
        return referenced, flags, None

    if record.company_ref:
        flags.add("invalid_company_ref")

    if record.email_domain:
        if domain_match is not None:
            return domain_match, flags, None
        return None, flags, _interaction_reject(record, "unmatched_domain")

    name_matches = _name_candidates(record.company_name, companies)
    if len(name_matches) == 1:
        return name_matches[0], flags, None
    if len(name_matches) > 1:
        reason = "ambiguous_company_name"
    else:
        reason = "unmatched_company"
    return None, flags, _interaction_reject(record, reason)


def _attach_interactions(
    records: tuple[InteractionRecord, ...],
    companies: list[_Company],
    by_crm_id: dict[str, _Company],
    by_domain: dict[str, _Company],
) -> list[RejectedRecord]:
    """Resolve interactions and count each interaction identifier at most once.

    Duplicate rows that resolve to one company contribute one count and their
    newest valid timestamp. If copies of the same identifier resolve to
    different companies, the group is rejected rather than assigned
    arbitrarily.
    """

    grouped: dict[str, list[InteractionRecord]] = defaultdict(list)
    for record in records:
        grouped[record.interaction_id].append(record)

    rejects: list[RejectedRecord] = []
    for interaction_id in sorted(grouped):
        group = sorted(grouped[interaction_id], key=lambda item: _raw_key(item.raw_record))
        resolved: list[tuple[InteractionRecord, _Company, set[str]]] = []
        for record in group:
            company, flags, reject = _resolve_interaction(
                record, companies, by_crm_id, by_domain
            )
            if reject is not None:
                rejects.append(reject)
            elif company is not None:
                resolved.append((record, company, flags))

        matched_companies = {company for _, company, _ in resolved}
        if len(matched_companies) > 1:
            rejects.append(
                RejectedRecord(
                    "interactions",
                    interaction_id,
                    "conflicting_duplicate_interaction_id",
                    {"records": [record.raw_record for record in group]},
                )
            )
            continue
        if not resolved:
            continue

        company = resolved[0][1]
        valid_times = [
            record.occurred_at for record, _, _ in resolved if record.occurred_at is not None
        ]
        company.interaction_times[interaction_id] = max(valid_times) if valid_times else None
        for record, _, flags in resolved:
            if record.company_name:
                company.aliases.add(record.company_name)
            company.quality_flags.update(flags)
        if len(group) > 1:
            company.quality_flags.add("duplicate_interaction_id")

    return rejects


def _latest_crm_value(company: _Company, attribute: str) -> Any:
    """Return the newest valid CRM value for one CRM-owned attribute."""

    candidates = [
        record for record in company.crm_records if getattr(record, attribute) is not None
    ]
    if not candidates:
        return None
    return getattr(max(candidates, key=_crm_order), attribute)


def _latest_market_record(company: _Company) -> MarketRecord | None:
    """Return the newest market observation with deterministic fallback."""

    if not company.market_records:
        return None
    return max(company.market_records, key=_market_order)


def _latest_market_value(company: _Company, attribute: str) -> Any:
    """Return the newest non-null market-owned value for one attribute."""

    candidates = [
        record for record in company.market_records if getattr(record, attribute) is not None
    ]
    if not candidates:
        return None
    return getattr(max(candidates, key=_market_order), attribute)


def _preferred_domain(company: _Company) -> str | None:
    """Choose the output domain from observed domains using stable precedence."""

    if not company.domains:
        return None
    crm_with_domains = [record for record in company.crm_records if record.domain]
    if crm_with_domains:
        return max(crm_with_domains, key=_crm_order).domain
    market_with_domains = [record for record in company.market_records if record.domain]
    if market_with_domains:
        return max(market_with_domains, key=_market_order).domain
    return min(company.domains)


def _canonical_name(company: _Company) -> str | None:
    """Choose a readable deterministic name, preferring CRM observations."""

    crm_names = {record.name for record in company.crm_records if record.name}
    names = crm_names or {
        record.company_name for record in company.market_records if record.company_name
    }
    if not names:
        names = company.aliases
    return min(names, key=lambda name: (len(name), name.casefold(), name)) if names else None


def _canonical_aliases(company: _Company) -> tuple[str, ...]:
    """Return case-insensitively unique aliases in deterministic display order."""

    by_casefold: dict[str, str] = {}
    for alias in company.aliases:
        key = alias.casefold()
        current = by_casefold.get(key)
        if current is None or alias < current:
            by_casefold[key] = alias
    return tuple(sorted(by_casefold.values(), key=str.casefold))


def _company_id(company: _Company, domain: str | None) -> str:
    """Derive a deterministic batch identifier from the strongest identity key."""

    if domain:
        identity = f"domain:{domain}"
    elif company.crm_records:
        identity = f"crm:{min(record.crm_id for record in company.crm_records)}"
    elif company.market_records:
        identity = f"market:{min(record.market_id for record in company.market_records)}"
    else:
        raise PipelineError("Cannot create an identifier for a company without source records")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"cmp_{digest}"


def _canonicalize(company: _Company) -> CanonicalCompany:
    """Apply source precedence and serialize one accumulated company shape."""

    domain = _preferred_domain(company)
    flags = set(company.quality_flags)
    if len(company.domains) > 1:
        flags.add("multiple_valid_domains")

    latest_market = _latest_market_record(company)
    valid_activity = [value for value in company.interaction_times.values() if value is not None]
    return CanonicalCompany(
        company_id=_company_id(company, domain),
        canonical_name=_canonical_name(company),
        domain=domain,
        legal_name=_latest_market_value(company, "legal_name"),
        founded_year=_latest_crm_value(company, "founded_year"),
        hq_country=_latest_crm_value(company, "hq_country"),
        status=_latest_crm_value(company, "status"),
        funding_total_usd=latest_market.funding_total_usd if latest_market else None,
        employee_count=latest_market.employee_count if latest_market else None,
        aliases=_canonical_aliases(company),
        crm_source_ids=tuple(sorted({record.crm_id for record in company.crm_records})),
        market_source_ids=tuple(
            sorted({record.market_id for record in company.market_records})
        ),
        last_activity_at=format_timestamp(max(valid_activity)) if valid_activity else None,
        interaction_count=len(company.interaction_times),
        quality_flags=tuple(sorted(flags)),
    )


def build_dataset(ingested: IngestedData) -> BuildResult:
    """Resolve all ingested records into sorted canonical companies and rejects.

    The function is pure with respect to files: it accepts an in-memory ingest
    result and returns the complete deterministic build result. File I/O lives
    in ``build_files`` so the resolution logic stays easy to test.
    """

    companies, by_crm_id, by_domain = _build_crm_companies(ingested.crm_records)
    rejects = list(ingested.rejects)
    rejects.extend(_attach_market_records(ingested.market_records, companies, by_domain))
    rejects.extend(
        _attach_interactions(
            ingested.interaction_records,
            companies,
            by_crm_id,
            by_domain,
        )
    )

    canonical = sorted(
        (_canonicalize(company) for company in companies),
        key=lambda company: company.company_id,
    )
    if len({company.company_id for company in canonical}) != len(canonical):
        raise PipelineError("Canonical company identifiers are not unique")
    domains = [company.domain for company in canonical if company.domain is not None]
    if len(set(domains)) != len(domains):
        raise PipelineError("Canonical company domains are not unique")

    ordered_rejects = sorted(
        rejects,
        key=lambda reject: (
            reject.source,
            reject.source_record_id,
            reject.reason,
            _raw_key(reject.raw_record),
        ),
    )
    return BuildResult(tuple(canonical), tuple(ordered_rejects))


def _reject_as_dict(reject: RejectedRecord) -> RawRecord:
    """Convert an internal rejection to the required JSONL contract shape."""

    return {
        "source": reject.source,
        "source_record_id": reject.source_record_id,
        "reason": reject.reason,
        "raw_record": reject.raw_record,
    }


def _write_jsonl(path: Path, records: list[RawRecord]) -> None:
    """Write records as canonical UTF-8 JSON Lines bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    contents = "".join(
        f"{json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
        for record in records
    )
    path.write_bytes(contents.encode("utf-8"))


def build_files(
    crm_path: str | Path,
    market_path: str | Path,
    interactions_path: str | Path,
    output_path: str | Path,
    rejects_path: str | Path,
) -> BuildResult:
    """Ingest source files, build the canonical dataset, and write both outputs.

    Raises ``InputFormatError``, ``PipelineError``, or ``OSError`` when a job
    cannot complete. The CLI translates those failures into a non-zero exit
    code and a concise user-facing message.
    """

    output = Path(output_path)
    rejects_output = Path(rejects_path)
    if output.resolve() == rejects_output.resolve():
        raise PipelineError("Company output and rejects output must be different files")

    result = build_dataset(load_inputs(crm_path, market_path, interactions_path))
    _write_jsonl(output, [company.as_dict() for company in result.companies])
    _write_jsonl(rejects_output, [_reject_as_dict(reject) for reject in result.rejects])
    return result
