from __future__ import annotations

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from data_challenge.ingestion import (
    InputFormatError,
    load_inputs,
    read_crm,
    read_interactions,
    read_market,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_load_inputs_keeps_valid_records_and_isolates_unusable_records() -> None:
    loaded = load_inputs(
        DATA / "crm_companies.csv",
        DATA / "market_data.json",
        DATA / "interactions.csv",
    )

    assert len(loaded.crm_records) == 15
    assert len(loaded.market_records) == 16
    assert len(loaded.interaction_records) == 19
    assert [(item.source, item.source_record_id, item.reason) for item in loaded.rejects] == [
        ("market", "MKT-017", "missing_company_identity")
    ]


def test_crm_domain_falls_back_to_website() -> None:
    records = {record.crm_id: record for record in read_crm(DATA / "crm_companies.csv").records}

    northstar = records["CRM-002"]
    assert northstar.domain == "northstarbio.example"
    assert northstar.quality_flags == ()


def test_crm_record_with_bad_optional_values_is_preserved_with_flags() -> None:
    records = {record.crm_id: record for record in read_crm(DATA / "crm_companies.csv").records}

    broken = records["CRM-014"]
    assert broken.name == "Broken Record"
    assert broken.domain is None
    assert broken.founded_year is None
    assert broken.hq_country is None
    assert broken.last_updated is None
    assert broken.status is None
    assert broken.quality_flags == (
        "invalid_domain",
        "invalid_founded_year",
        "invalid_hq_country",
        "invalid_last_updated",
        "invalid_status",
    )


def test_market_record_with_bad_optional_values_is_preserved_with_flags() -> None:
    result = read_market(DATA / "market_data.json")
    records = {record.market_id: record for record in result.records}

    broken = records["MKT-014"]
    assert broken.company_name == "Broken Record"
    assert broken.funding_total_usd is None
    assert broken.employee_count is None
    assert broken.observed_at is None
    assert broken.quality_flags == (
        "invalid_employee_count",
        "invalid_funding_total_usd",
        "invalid_observed_at",
    )

    assert result.rejects[0].source_record_id == "MKT-017"


def test_name_only_market_record_is_deferred_to_entity_resolution() -> None:
    records = {record.market_id: record for record in read_market(DATA / "market_data.json").records}

    beacon = records["MKT-016"]
    assert beacon.company_name == "Beacon"
    assert beacon.domain is None


def test_invalid_interaction_timestamp_does_not_reject_interaction() -> None:
    records = read_interactions(DATA / "interactions.csv").records
    by_id = {record.interaction_id: record for record in records}

    malformed_time = by_id["INT-008"]
    assert malformed_time.occurred_at is None
    assert malformed_time.quality_flags == ("invalid_occurred_at",)


def test_ingestion_does_not_prematurely_deduplicate_interactions() -> None:
    records = read_interactions(DATA / "interactions.csv").records

    assert [record.interaction_id for record in records].count("INT-004") == 2


def test_market_reader_rejects_individual_non_object_items() -> None:
    contents = '[{"market_id": "MKT-1", "company_name": "Acme"}, 42]'

    with patch.object(Path, "open", mock_open(read_data=contents)):
        result = read_market("market.json")

    assert [record.market_id for record in result.records] == ["MKT-1"]
    assert len(result.rejects) == 1
    assert result.rejects[0].source_record_id == "item:2"
    assert result.rejects[0].reason == "record_is_not_an_object"
    assert result.rejects[0].raw_record == {"value": 42}


def test_missing_csv_schema_is_a_fatal_input_error() -> None:
    contents = "crm_id,name\nCRM-1,Acme\n"

    with patch.object(Path, "open", mock_open(read_data=contents)):
        with pytest.raises(InputFormatError, match="missing columns"):
            read_crm("crm.csv")


def test_malformed_json_is_a_fatal_input_error() -> None:
    with patch.object(Path, "open", mock_open(read_data="[invalid")):
        with pytest.raises(InputFormatError, match="Malformed JSON"):
            read_market("market.json")
