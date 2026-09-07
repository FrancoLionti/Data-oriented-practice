"""Independent review tests. These do not change the submitted solution."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import mock_open, patch

import pytest

ROOT = Path(__file__).resolve().parents[1] / "data-platform-mock"
sys.path.insert(0, str(ROOT / "src"))

from data_challenge.ingestion import load_inputs, read_market
from data_challenge.models import CRMRecord, IngestedData, InteractionRecord
from data_challenge.normalization import parse_timestamp, parse_usd_amount
from data_challenge.pipeline import build_dataset


def fixture_inputs():
    return load_inputs(ROOT / "data/crm_companies.csv", ROOT / "data/market_data.json",
                       ROOT / "data/interactions.csv")


def crm(identifier, name, domain):
    return CRMRecord(identifier, name, domain, 2020, "US",
                     parse_timestamp("2026-08-01T00:00:00Z"), "active", (),
                     {"crm_id": identifier, "name": name, "domain": domain})


def interaction(identifier, ref, name, domain, timestamp):
    return InteractionRecord(identifier, ref, name, domain, parse_timestamp(timestamp),
                             "meeting", (), {"interaction_id": identifier,
                             "company_ref": ref, "company_name": name,
                             "email_domain": domain, "occurred_at": timestamp})


def test_name_only_market_record_must_see_all_domain_candidates():
    payload = [
        {"market_id": "M1", "company_name": "Beacon", "domain": "a.example"},
        {"market_id": "M2", "company_name": "Beacon", "domain": None},
        {"market_id": "M3", "company_name": "Beacon", "domain": "b.example"},
    ]
    with patch.object(Path, "open", mock_open(read_data=json.dumps(payload))):
        source = read_market("market.json")
    result = build_dataset(IngestedData((), source.records, (), source.rejects))
    assert len(result.companies) == 2
    assert any(r.source_record_id == "M2" and r.reason == "ambiguous_company_name"
               for r in result.rejects), [c.as_dict() for c in result.companies]


def test_preserve_distinct_observed_case_variants():
    result = build_dataset(fixture_inputs())
    company = next(c for c in result.companies if c.domain == "cloudsmithlabs.example")
    assert {"CloudSmith Labs", "Cloudsmith Labs"} <= set(company.aliases)


@pytest.mark.parametrize("raw", ["12,5", "$1$2"])
def test_malformed_money_is_not_silently_reinterpreted(raw):
    assert parse_usd_amount(raw) is None


@pytest.mark.parametrize("raw", ["0001-01-01T00:00:00+01:00",
                                 "9999-12-31T23:59:59-01:00"])
def test_unrepresentable_utc_timestamp_degrades_without_crashing(raw):
    payload = [{"market_id": "M1", "company_name": "Example",
                "domain": "example.com", "observed_at": raw}]
    with patch.object(Path, "open", mock_open(read_data=json.dumps(payload))):
        result = read_market("market.json")
    assert len(result.records) == 1
    assert result.records[0].observed_at is None


def test_conflicting_duplicate_interaction_is_rejected():
    companies = (crm("C1", "Alpha", "a.example"), crm("C2", "Beta", "b.example"))
    records = (interaction("I1", "C1", "Alpha", "a.example", "2026-08-01T00:00:00Z"),
               interaction("I1", "C2", "Beta", "b.example", "2026-08-02T00:00:00Z"))
    result = build_dataset(IngestedData(companies, (), records, ()))
    assert sum(c.interaction_count for c in result.companies) == 0
    assert any(r.reason == "conflicting_duplicate_interaction_id" for r in result.rejects)


def test_duplicate_interaction_same_company_counts_once_with_latest_time():
    company = crm("C1", "Alpha", "a.example")
    records = (interaction("I1", "C1", "Alpha", "a.example", "2026-08-01T00:00:00Z"),
               interaction("I1", "C1", "Alpha", "a.example", "2026-08-02T00:00:00Z"))
    result = build_dataset(IngestedData((company,), (), records, ()))
    assert result.companies[0].interaction_count == 1
    assert result.companies[0].last_activity_at == "2026-08-02T00:00:00Z"


def test_reversing_all_source_rows_keeps_same_result():
    source = fixture_inputs()
    reversed_source = replace(source, crm_records=source.crm_records[::-1],
                              market_records=source.market_records[::-1],
                              interaction_records=source.interaction_records[::-1])
    assert build_dataset(source) == build_dataset(reversed_source)


def test_cli_different_working_directory_and_hash_seeds(tmp_path):
    generated = []
    for seed in ("1", "42"):
        output = tmp_path / f"companies-{seed}.jsonl"
        rejects = tmp_path / f"rejects-{seed}.jsonl"
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT / "src"))
        run = subprocess.run([sys.executable, "-m", "data_challenge", "build",
            "--crm", str(ROOT / "data/crm_companies.csv"),
            "--market", str(ROOT / "data/market_data.json"),
            "--interactions", str(ROOT / "data/interactions.csv"),
            "--output", str(output), "--rejects", str(rejects)],
            cwd=tmp_path, env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        generated.append((output.read_bytes(), rejects.read_bytes()))
    assert generated[0] == generated[1]


def test_valid_market_observation_beats_undated_observation():
    payload = [
        {"market_id": "M1", "company_name": "Alpha", "domain": "a.example",
         "observed_at": "2026-08-01T00:00:00Z", "funding_total_usd": 100},
        {"market_id": "M2", "company_name": "Alpha", "domain": "a.example",
         "observed_at": "invalid", "funding_total_usd": 999},
    ]
    with patch.object(Path, "open", mock_open(read_data=json.dumps(payload))):
        source = read_market("market.json")
    result = build_dataset(IngestedData((), source.records, (), source.rejects))
    assert result.companies[0].funding_total_usd == 100

