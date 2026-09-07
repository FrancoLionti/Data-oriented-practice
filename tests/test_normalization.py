from __future__ import annotations

from datetime import UTC, datetime

import pytest

from data_challenge.normalization import (
    format_timestamp,
    normalize_domain,
    normalize_name,
    parse_founded_year,
    parse_integer,
    parse_timestamp,
    parse_usd_amount,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" acme.ai.example ", "acme.ai.example"),
        ("HTTPS://ACME.AI.EXAMPLE/company", "acme.ai.example"),
        ("www.acme.ai.example.", "acme.ai.example"),
        ("cloudsmithlabs.example:443", "cloudsmithlabs.example"),
        (
            "https://user:secret@www.novarobotics.example:443/team?x=1#people",
            "novarobotics.example",
        ),
        ("https://atlasclimate.example/contact", "atlasclimate.example"),
    ],
)
def test_normalize_domain_removes_url_decoration(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "not a domain", "localhost", "bad_label.example", "x.example:99999"],
)
def test_normalize_domain_rejects_unusable_values(raw: object) -> None:
    assert normalize_domain(raw) is None


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("Vector Pay", "VectorPay S.A.", "vectorpay"),
        ("Quantum Foods", "Quantum Foods LLC", "quantumfoods"),
        ("AcmeAI Inc.", "  ACME-AI incorporated ", "acmeai"),
        ("Compañía Única GmbH", "COMPANIA UNICA", "companiaunica"),
    ],
)
def test_normalize_name_ignores_formatting_and_legal_suffixes(
    left: str, right: str, expected: str
) -> None:
    assert normalize_name(left) == expected
    assert normalize_name(right) == expected


def test_normalize_name_does_not_expand_abbreviations() -> None:
    assert normalize_name("Northstar Bio") != normalize_name("Northstar Biosciences")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,234", 1234), (12, 12), ("12.0", 12), ("12.5", None), (True, None)],
)
def test_parse_integer_is_strict(raw: object, expected: int | None) -> None:
    assert parse_integer(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$20,000,000", 20_000_000), (0, 0), ("-$500", None), ("unknown", None)],
)
def test_parse_usd_amount_requires_non_negative_whole_dollars(
    raw: object, expected: int | None
) -> None:
    assert parse_usd_amount(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(2019, 2019), ("2021", 2021), (1799, None), (3026, None)],
)
def test_parse_founded_year_uses_fixed_deterministic_bounds(
    raw: object, expected: int | None
) -> None:
    assert parse_founded_year(raw) == expected


def test_parse_timestamp_converts_offsets_to_utc() -> None:
    parsed = parse_timestamp("2026-08-20T08:00:00-03:00")

    assert parsed == datetime(2026, 8, 20, 11, 0, tzinfo=UTC)
    assert format_timestamp(parsed) == "2026-08-20T11:00:00Z"


@pytest.mark.parametrize("raw", [None, "", "not-a-date", "2026-08-20T11:00:00"])
def test_parse_timestamp_rejects_invalid_or_naive_values(raw: object) -> None:
    assert parse_timestamp(raw) is None
