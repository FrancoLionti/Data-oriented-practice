from __future__ import annotations

from pathlib import Path

from data_challenge.ingestion import load_inputs
from data_challenge.pipeline import build_dataset


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _build():
    ingested = load_inputs(
        DATA / "crm_companies.csv",
        DATA / "market_data.json",
        DATA / "interactions.csv",
    )
    return build_dataset(ingested)


def test_fixture_builds_expected_number_of_safe_companies() -> None:
    result = _build()

    assert len(result.companies) == 14
    assert len({company.company_id for company in result.companies}) == 14
    assert [company.company_id for company in result.companies] == sorted(
        company.company_id for company in result.companies
    )


def test_domain_matching_merges_duplicates_and_applies_source_precedence() -> None:
    companies = {company.domain: company for company in _build().companies}

    acme = companies["acme.ai.example"]
    assert acme.canonical_name == "Acme AI"
    assert acme.crm_source_ids == ("CRM-001", "CRM-009")
    assert acme.market_source_ids == ("MKT-001", "MKT-002")
    assert acme.status == "prospect"
    assert acme.funding_total_usd == 25_000_000
    assert acme.employee_count == 85


def test_different_valid_domains_keep_same_named_companies_separate() -> None:
    companies = {company.domain: company for company in _build().companies}

    primary = companies["acme.ai.example"]
    alternate = companies["acme-alt.example"]
    assert primary.company_id != alternate.company_id
    assert alternate.crm_source_ids == ()
    assert alternate.market_source_ids == ("MKT-015",)
    assert alternate.interaction_count == 1


def test_domain_can_enrich_a_unique_domainless_crm_match() -> None:
    companies = {company.domain: company for company in _build().companies}

    helio = companies["heliogrid.example"]
    assert helio.crm_source_ids == ("CRM-010",)
    assert helio.market_source_ids == ("MKT-010",)


def test_ambiguous_name_only_records_are_rejected() -> None:
    result = _build()
    rejected = {
        (reject.source, reject.source_record_id, reject.reason)
        for reject in result.rejects
    }

    assert ("market", "MKT-016", "ambiguous_company_name") in rejected
    assert ("interactions", "INT-006", "ambiguous_company_name") in rejected


def test_valid_crm_reference_wins_over_conflicting_interaction_domain() -> None:
    companies = {company.domain: company for company in _build().companies}

    beacon_labs = companies["beaconlabs.example"]
    beacon_vc = companies["beaconvc.example"]
    assert beacon_labs.interaction_count == 1
    assert beacon_labs.last_activity_at == "2026-08-23T09:30:00Z"
    assert "interaction_identity_conflict" in beacon_labs.quality_flags
    assert beacon_vc.interaction_count == 0


def test_duplicate_interaction_id_counts_once_and_latest_activity_is_valid() -> None:
    companies = {company.domain: company for company in _build().companies}

    vector = companies["vectorpay.example"]
    assert vector.interaction_count == 2
    assert vector.last_activity_at == "2026-08-21T09:00:00Z"
    assert "duplicate_interaction_id" in vector.quality_flags

    quantum = companies["quantumfoods.example"]
    assert quantum.interaction_count == 1
    assert quantum.last_activity_at is None
    assert "invalid_occurred_at" in quantum.quality_flags


def test_build_result_is_deterministic() -> None:
    first = _build()
    second = _build()

    assert first == second
