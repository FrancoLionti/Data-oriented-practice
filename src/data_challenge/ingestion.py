"""Tolerant source ingestion with record-level quality isolation."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
import re
from typing import Any, TypeVar

from data_challenge.models import (
    CRMRecord,
    IngestedData,
    InteractionRecord,
    MarketRecord,
    RawRecord,
    RejectedRecord,
    SourceName,
    SourceReadResult,
)
from data_challenge.normalization import (
    normalize_domain,
    parse_founded_year,
    parse_integer,
    parse_timestamp,
    parse_usd_amount,
)


class InputFormatError(ValueError):
    """Raised when an entire input cannot be interpreted safely."""


_CRM_COLUMNS = {
    "crm_id",
    "name",
    "domain",
    "website",
    "founded_year",
    "hq_country",
    "last_updated",
    "status",
}
_INTERACTION_COLUMNS = {
    "interaction_id",
    "company_ref",
    "company_name",
    "email_domain",
    "occurred_at",
    "type",
}
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_RESERVED_COUNTRY_CODES = {"XX", "ZZ"}
_VALID_CRM_STATUSES = {"active", "prospect", "inactive", "acquired", "closed"}


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _is_present(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _safe_raw_record(record: Mapping[object, Any]) -> RawRecord:
    result: RawRecord = {}
    for key, value in record.items():
        safe_key = "__extra_fields__" if key is None else str(key)
        result[safe_key] = value
    return result


def _reject(
    source: SourceName,
    source_record_id: str,
    reason: str,
    raw_record: RawRecord,
) -> RejectedRecord:
    return RejectedRecord(source, source_record_id, reason, raw_record)


def _resolve_crm_domain(raw: RawRecord, flags: set[str]) -> str | None:
    raw_domain = raw.get("domain")
    raw_website = raw.get("website")
    domain = normalize_domain(raw_domain)
    website_domain = normalize_domain(raw_website)

    if _is_present(raw_domain) and domain is None:
        flags.add("invalid_domain")
    if _is_present(raw_website) and website_domain is None:
        flags.add("invalid_website")
    if domain and website_domain and domain != website_domain:
        flags.add("conflicting_domain_fields")

    return domain or website_domain


def _parse_crm_record(
    record: Mapping[object, Any], row_number: int
) -> CRMRecord | RejectedRecord:
    raw = _safe_raw_record(record)
    fallback_id = f"row:{row_number}"
    crm_id = _clean_text(raw.get("crm_id"))
    if crm_id is None:
        return _reject("crm", fallback_id, "missing_crm_id", raw)

    flags: set[str] = set()
    name = _clean_text(raw.get("name"))
    domain = _resolve_crm_domain(raw, flags)
    if name is None and domain is None:
        return _reject("crm", crm_id, "missing_company_identity", raw)
    if name is None:
        flags.add("missing_name")

    founded_year = parse_founded_year(raw.get("founded_year"))
    if _is_present(raw.get("founded_year")) and founded_year is None:
        flags.add("invalid_founded_year")

    country_text = _clean_text(raw.get("hq_country"))
    hq_country = country_text.upper() if country_text else None
    if hq_country and (
        not _COUNTRY_CODE.fullmatch(hq_country)
        or hq_country in _RESERVED_COUNTRY_CODES
    ):
        hq_country = None
        flags.add("invalid_hq_country")

    updated_value = raw.get("last_updated")
    last_updated = parse_timestamp(updated_value)
    if last_updated is None:
        flags.add("invalid_last_updated" if _is_present(updated_value) else "missing_last_updated")

    status_text = _clean_text(raw.get("status"))
    status = status_text.casefold() if status_text else None
    if status and status not in _VALID_CRM_STATUSES:
        status = None
        flags.add("invalid_status")

    return CRMRecord(
        crm_id=crm_id,
        name=name,
        domain=domain,
        founded_year=founded_year,
        hq_country=hq_country,
        last_updated=last_updated,
        status=status,
        quality_flags=tuple(sorted(flags)),
        raw_record=raw,
    )


def _parse_market_record(
    record: Mapping[object, Any], item_number: int
) -> MarketRecord | RejectedRecord:
    raw = _safe_raw_record(record)
    fallback_id = f"item:{item_number}"
    market_id = _clean_text(raw.get("market_id"))
    if market_id is None:
        return _reject("market", fallback_id, "missing_market_id", raw)

    flags: set[str] = set()
    company_name = _clean_text(raw.get("company_name"))
    domain_value = raw.get("domain")
    domain = normalize_domain(domain_value)
    if _is_present(domain_value) and domain is None:
        flags.add("invalid_domain")
    if company_name is None and domain is None:
        return _reject("market", market_id, "missing_company_identity", raw)

    funding_value = raw.get("funding_total_usd")
    funding_total_usd = parse_usd_amount(funding_value)
    if _is_present(funding_value) and funding_total_usd is None:
        flags.add("invalid_funding_total_usd")

    employee_value = raw.get("employee_count")
    employee_count = parse_integer(employee_value, minimum=0)
    if _is_present(employee_value) and employee_count is None:
        flags.add("invalid_employee_count")

    observed_value = raw.get("observed_at")
    observed_at = parse_timestamp(observed_value)
    if observed_at is None:
        flags.add("invalid_observed_at" if _is_present(observed_value) else "missing_observed_at")

    return MarketRecord(
        market_id=market_id,
        company_name=company_name,
        domain=domain,
        legal_name=_clean_text(raw.get("legal_name")),
        funding_total_usd=funding_total_usd,
        employee_count=employee_count,
        observed_at=observed_at,
        quality_flags=tuple(sorted(flags)),
        raw_record=raw,
    )


def _parse_interaction_record(
    record: Mapping[object, Any], row_number: int
) -> InteractionRecord | RejectedRecord:
    raw = _safe_raw_record(record)
    fallback_id = f"row:{row_number}"
    interaction_id = _clean_text(raw.get("interaction_id"))
    if interaction_id is None:
        return _reject("interactions", fallback_id, "missing_interaction_id", raw)

    flags: set[str] = set()
    company_ref = _clean_text(raw.get("company_ref"))
    company_name = _clean_text(raw.get("company_name"))
    domain_value = raw.get("email_domain")
    email_domain = normalize_domain(domain_value)
    if _is_present(domain_value) and email_domain is None:
        flags.add("invalid_email_domain")
    if company_ref is None and company_name is None and email_domain is None:
        return _reject("interactions", interaction_id, "missing_company_identity", raw)

    occurred_value = raw.get("occurred_at")
    occurred_at = parse_timestamp(occurred_value)
    if occurred_at is None:
        flags.add("invalid_occurred_at" if _is_present(occurred_value) else "missing_occurred_at")

    return InteractionRecord(
        interaction_id=interaction_id,
        company_ref=company_ref,
        company_name=company_name,
        email_domain=email_domain,
        occurred_at=occurred_at,
        interaction_type=_clean_text(raw.get("type")),
        quality_flags=tuple(sorted(flags)),
        raw_record=raw,
    )


def _read_csv_rows(path: Path, required_columns: set[str]) -> Iterator[tuple[int, RawRecord]]:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise InputFormatError(f"Cannot open {path}: {error}") from error

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputFormatError(f"CSV input {path} has no header")
        missing_columns = required_columns.difference(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise InputFormatError(f"CSV input {path} is missing columns: {missing}")

        try:
            for row_number, row in enumerate(reader, start=2):
                yield row_number, _safe_raw_record(row)
        except csv.Error as error:
            raise InputFormatError(f"Malformed CSV input {path}: {error}") from error


ParsedT = TypeVar("ParsedT", CRMRecord, InteractionRecord)


def _read_csv_source(
    path: str | Path,
    required_columns: set[str],
    parser: Callable[[Mapping[object, Any], int], ParsedT | RejectedRecord],
) -> SourceReadResult[ParsedT]:
    records: list[ParsedT] = []
    rejects: list[RejectedRecord] = []
    for row_number, raw in _read_csv_rows(Path(path), required_columns):
        parsed = parser(raw, row_number)
        if isinstance(parsed, RejectedRecord):
            rejects.append(parsed)
        else:
            records.append(parsed)
    return SourceReadResult(tuple(records), tuple(rejects))


def read_crm(path: str | Path) -> SourceReadResult[CRMRecord]:
    return _read_csv_source(path, _CRM_COLUMNS, _parse_crm_record)


def read_interactions(path: str | Path) -> SourceReadResult[InteractionRecord]:
    return _read_csv_source(path, _INTERACTION_COLUMNS, _parse_interaction_record)


def read_market(path: str | Path) -> SourceReadResult[MarketRecord]:
    source_path = Path(path)
    try:
        with source_path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except OSError as error:
        raise InputFormatError(f"Cannot open {source_path}: {error}") from error
    except json.JSONDecodeError as error:
        raise InputFormatError(f"Malformed JSON input {source_path}: {error}") from error

    if not isinstance(payload, list):
        raise InputFormatError(f"Market input {source_path} must contain a JSON array")

    records: list[MarketRecord] = []
    rejects: list[RejectedRecord] = []
    for item_number, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            rejects.append(
                _reject(
                    "market",
                    f"item:{item_number}",
                    "record_is_not_an_object",
                    {"value": item},
                )
            )
            continue
        parsed = _parse_market_record(item, item_number)
        if isinstance(parsed, RejectedRecord):
            rejects.append(parsed)
        else:
            records.append(parsed)
    return SourceReadResult(tuple(records), tuple(rejects))


def load_inputs(
    crm_path: str | Path,
    market_path: str | Path,
    interactions_path: str | Path,
) -> IngestedData:
    """Read all sources; source-level failures remain fatal to the complete job."""

    crm = read_crm(crm_path)
    market = read_market(market_path)
    interactions = read_interactions(interactions_path)
    return IngestedData(
        crm_records=crm.records,
        market_records=market.records,
        interaction_records=interactions.records,
        rejects=crm.rejects + market.rejects + interactions.rejects,
    )
