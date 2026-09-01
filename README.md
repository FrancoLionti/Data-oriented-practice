# Data Platform Engineering Live Exercise

## Scenario

You are joining a team that builds decision-making infrastructure for venture-capital investors. The team receives company information from a CRM, a market-data provider, and an interaction-tracking system.

The sources are useful but inconsistent:

- the same company may have different names in different systems;
- domains and URLs use inconsistent formats;
- some records are duplicated, incomplete, stale, or malformed;
- sources may disagree about company attributes;
- interactions may refer to a CRM identifier, a domain, or only a company name.

Your task is to build a small, production-minded data integration program that creates a deterministic canonical view of these companies.

## Timebox

Target: **90 minutes**.

You may use any AI assistant, documentation, library, or search engine. Be prepared to explain what you delegated, what you verified yourself, and how you detected incorrect suggestions.

## Required command

Implement this command:

```powershell
python -m data_challenge build `
  --crm data/crm_companies.csv `
  --market data/market_data.json `
  --interactions data/interactions.csv `
  --output artifacts/companies.jsonl `
  --rejects artifacts/rejects.jsonl
```

The command must return exit code `0` on valid input and create both JSON Lines files.

## Canonical company output

Every line in `companies.jsonl` must be a JSON object with these fields:

```json
{
  "company_id": "stable deterministic identifier",
  "canonical_name": "Acme AI",
  "domain": "acme.example",
  "legal_name": "Acme Artificial Intelligence Inc.",
  "founded_year": 2019,
  "hq_country": "US",
  "status": "active",
  "funding_total_usd": 25000000,
  "employee_count": 85,
  "aliases": ["Acme AI", "AcmeAI Inc."],
  "source_ids": {
    "crm": ["CRM-001"],
    "market": ["MKT-001"]
  },
  "last_activity_at": "2026-08-19T14:30:00Z",
  "interaction_count": 2,
  "quality_flags": []
}
```

Nullable attributes may be `null`. Arrays must always be present. Output objects must be sorted by `company_id`, and arrays such as aliases, identifiers, and flags must have deterministic ordering.

## Rejected-record output

Do not crash the complete run because one record is unusable. Write records that cannot be assigned safely to a company to `rejects.jsonl`:

```json
{
  "source": "interactions",
  "source_record_id": "INT-999",
  "reason": "clear machine-readable or human-readable reason",
  "raw_record": {}
}
```

Malformed optional attributes do not necessarily require rejecting the complete record. You may preserve the entity, set the attribute to `null`, and add an appropriate `quality_flags` entry.

## Matching requirements

Your matching strategy must be deterministic and must follow these minimum safety rules:

1. Normalize usable domains by removing schemes, credentials, `www.`, ports, paths, query strings, fragments, case differences, surrounding whitespace, and a trailing dot.
2. Prefer a normalized domain as the strongest cross-source identity signal.
3. A valid CRM reference is stronger than an inferred match.
4. Name-based matching is allowed only when a domain is unavailable and the normalized name identifies exactly one candidate.
5. Do **not** merge two records that contain different non-empty valid domains solely because their names are similar.
6. Common legal suffixes, punctuation, whitespace, and case should not prevent otherwise safe name matching.
7. If a match is ambiguous, reject it rather than choosing arbitrarily.

You may document additional assumptions in `SUBMISSION.md`.

## Source precedence and history

- CRM owns `status`, `hq_country`, and `founded_year` when those values are valid.
- Market data owns `legal_name`, `funding_total_usd`, and `employee_count`.
- When multiple market observations resolve to the same company, use the newest valid `observed_at` for mutable market metrics.
- Preserve every distinct observed name in `aliases`.
- Duplicate interaction identifiers must count only once.
- Invalid interaction timestamps must not become `last_activity_at`.
- `last_activity_at` is the newest valid matched interaction timestamp.

## Reliability requirements

- Running the command twice with identical inputs must produce byte-identical outputs.
- The program must not depend on the current working directory beyond the paths supplied as arguments.
- Bad rows must not prevent valid companies from being emitted.
- Errors that prevent the complete job from running should produce a non-zero exit code and a useful message.
- Include automated tests for the behavior you consider most important.

## What to explain afterward

Be ready to discuss:

- the identity and matching strategy;
- complexity and expected bottlenecks at 10 million records;
- how you would make ingestion incremental and idempotent;
- how you would persist canonical identities over time;
- how late-arriving updates would be handled;
- observability, quality metrics, and alerting;
- what would change if the output served an API or an AI agent;
- what you would improve with another half day.

## Optional stretch work

Only attempt these after the core requirements work:

- add a `query --domain ...` command;
- persist results in SQLite or DuckDB;
- expose a small read-only HTTP API;
- add structured logging and run-level metrics;
- process inputs without loading every record into memory.

Start by running:

```powershell
python -m pip install -e ".[dev]"
pytest -q
```

The public tests validate the external contract, not the full business logic.
The starter repository is expected to report one passing test and one failing test until you implement `build`.
