from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DATA = ROOT / "data"

REQUIRED_COMPANY_FIELDS = {
    "company_id",
    "canonical_name",
    "domain",
    "legal_name",
    "founded_year",
    "hq_country",
    "status",
    "funding_total_usd",
    "employee_count",
    "aliases",
    "source_ids",
    "last_activity_at",
    "interaction_count",
    "quality_flags",
}

REQUIRED_REJECT_FIELDS = {
    "source",
    "source_record_id",
    "reason",
    "raw_record",
}


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not previous else f"{SRC}{os.pathsep}{previous}"
    return env


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        assert isinstance(value, dict), f"{path.name}:{line_number} is not a JSON object"
        records.append(value)
    return records


def _run_build(output: Path, rejects: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "data_challenge",
            "build",
            "--crm",
            str(DATA / "crm_companies.csv"),
            "--market",
            str(DATA / "market_data.json"),
            "--interactions",
            str(DATA / "interactions.csv"),
            "--output",
            str(output),
            "--rejects",
            str(rejects),
        ],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "data_challenge", "--help"],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "build" in result.stdout


def test_build_contract_and_determinism(tmp_path: Path) -> None:
    output_one = tmp_path / "companies-one.jsonl"
    rejects_one = tmp_path / "rejects-one.jsonl"
    output_two = tmp_path / "companies-two.jsonl"
    rejects_two = tmp_path / "rejects-two.jsonl"

    first = _run_build(output_one, rejects_one)
    second = _run_build(output_two, rejects_two)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert output_one.exists()
    assert rejects_one.exists()
    assert output_one.read_bytes() == output_two.read_bytes()
    assert rejects_one.read_bytes() == rejects_two.read_bytes()

    companies = _read_jsonl(output_one)
    rejects = _read_jsonl(rejects_one)

    assert companies, "Expected at least one canonical company"
    assert rejects, "The fixture intentionally contains rejected records"

    company_ids = [item["company_id"] for item in companies]
    assert company_ids == sorted(company_ids)
    assert len(company_ids) == len(set(company_ids))

    domains = [item["domain"] for item in companies if item["domain"] is not None]
    assert len(domains) == len(set(domains))

    for company in companies:
        assert set(company) == REQUIRED_COMPANY_FIELDS
        assert isinstance(company["aliases"], list)
        assert isinstance(company["source_ids"], dict)
        assert set(company["source_ids"]) == {"crm", "market"}
        assert isinstance(company["interaction_count"], int)
        assert company["interaction_count"] >= 0
        assert isinstance(company["quality_flags"], list)
        assert company["aliases"] == sorted(set(company["aliases"]), key=str.casefold)
        assert company["quality_flags"] == sorted(set(company["quality_flags"]))
        assert company["source_ids"]["crm"] == sorted(set(company["source_ids"]["crm"]))
        assert company["source_ids"]["market"] == sorted(set(company["source_ids"]["market"]))

    for rejected in rejects:
        assert set(rejected) == REQUIRED_REJECT_FIELDS
        assert rejected["source"] in {"crm", "market", "interactions"}
        assert rejected["reason"]
        assert isinstance(rejected["raw_record"], dict)
