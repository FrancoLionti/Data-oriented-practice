# Submission notes

## Status at the end of the timebox

- Completed: deterministic normalization helpers for domains, company names,
  integers, USD amounts, founded years, and ISO-8601 timestamps; focused unit
  tests for those helpers; typed internal source models; tolerant CSV and JSON
  ingestion with record-level rejects and quality flags; safe entity resolution;
  source precedence; interaction aggregation and deduplication; deterministic
  JSONL output; and the `build` CLI.
- Partially completed: none in the required scope.
- Not attempted: optional stretch work.

## Design summary

The pipeline has five stages: normalize values, ingest source records, resolve
companies, aggregate interactions, and write JSONL. Source readers return typed
immutable record snapshots and retain raw records for diagnostic rejects. Domains
are the primary identity key; normalized names are used only for an unambiguous
fallback. The resolver accumulates source observations in an internal mutable
company and then applies precedence to create immutable canonical output. CRM
owns company status, country, and founding year; market data owns legal name and
market metrics. The command layer handles arguments and converts fatal input or
pipeline errors into a useful message and non-zero process status.

## Assumptions

- A usable identity domain must contain at least two valid DNS-style labels.
- A leading `www.` is not part of company identity; other subdomains are kept.
- Unicode domains are converted to IDNA ASCII before validation.
- Name comparison ignores accents, punctuation, whitespace, case, and a small
  explicit set of trailing legal suffixes. It does not perform fuzzy matching
  or expand abbreviations.
- Funding and employee counts must be non-negative whole numbers.
- Founded years outside the fixed range 1800–2100 are treated as invalid. A
  fixed bound avoids making identical inputs change meaning with the system date.
- Timestamps without an explicit timezone are considered invalid unless the
  source contract defines a default timezone. Assuming the machine's local
  timezone would make the result environment-dependent. An invalid timestamp
  degrades only the temporal attribute: it does not automatically reject the
  complete record. Valid timestamps are converted to UTC and emitted with `Z`.
- Source record identifiers are required. A record without its source ID is
  rejected because it cannot be safely deduplicated or traced later.
- A record with either a usable domain or a non-empty company name is retained
  for entity resolution. Whether a name-only record is unique or ambiguous is
  deliberately decided in the matching stage, not during ingestion.
- CRM status is accepted from an explicit allowlist. Country codes require the
  two-letter shape and reject the common unknown sentinels `XX` and `ZZ`; full
  ISO-3166 membership validation would be a production follow-up.
- A valid normalized domain is the strongest cross-source identity signal. A
  market record with a new domain may enrich exactly one domainless candidate,
  but it never joins a company that already has a different valid domain.
- A name-only market record or interaction is attached only when its normalized
  name identifies exactly one company. Ambiguous and unmatched records are
  rejected with their raw source row.
- A valid CRM reference wins when an interaction's reference and domain disagree.
  The interaction is attached to the CRM company and adds an identity-conflict
  quality flag.
- When CRM observations disagree, each CRM-owned field uses its newest valid
  `last_updated` value. Market funding and employee metrics use the newest valid
  `observed_at` observation; legal names use the newest non-null market value.
- Batch company IDs derive from a normalized domain when present, then from the
  lexicographically smallest available source ID for domainless companies. They
  are deterministic for the same inputs but would be replaced by a persistent
  identity registry over time.

## Important trade-offs

- Name normalization concatenates tokens so `Vector Pay` and `VectorPay` match.
  This improves intended matches but is safe only alongside uniqueness and
  domain-conflict checks in the entity-resolution stage.
- Domain validation is deliberately conservative; internal single-label hosts
  are rejected rather than used as cross-source company identifiers.
- Parsers use the standard library only, keeping the timeboxed solution small
  and avoiding a validation-framework dependency.
- Ingestion preserves duplicate interaction rows. Deduplicating them here could
  hide conflicting copies; the aggregation stage will choose deterministically
  and ensure that each interaction ID contributes at most once.
- Missing required columns, malformed JSON, and unreadable files are job-level
  errors because continuing would make the source incomplete without a reliable
  record boundary. Bad optional values inside a readable record are isolated.
- Company assembly uses mutable lists, sets, and dictionaries internally. The
  final arrays and output lines are explicitly sorted, so the public result is
  deterministic despite using unordered sets during accumulation.
- The implementation uses standard-library validation rather than adding a
  runtime dependency. A schema library such as Pydantic could improve structured
  field errors in a larger ingestion system, but domain safety and matching rules
  would still require explicit business logic.

## Tests executed

```text
56 passed in 1.65s

Command:
python -m pytest -q -p no:cacheprovider
```

## AI usage

- Assistant/tool used: Codex.
- Tasks delegated: repository inspection; normalization helpers; typed source
  models; tolerant ingestion; entity resolution; source precedence;
  interaction aggregation; deterministic JSONL output; tests; documentation.
- Important output I verified manually: domain safety rules, exact name
  normalization behavior, numeric bounds, timezone conversion, fixture record
  counts, error classification, source precedence, rejection cases, output
  ordering, byte-identical reruns, and test results.
- Suggestion I rejected or changed: the first generated test expected 18
  interaction rows by looking at the ID range. The test run exposed 19 physical
  rows because `INT-004` is duplicated. I kept both rows at ingestion and left
  ID-based deduplication for the aggregation stage.

## Production follow-up

With another half day, I would:

1. Persist canonical identities and source-record lineage in SQLite or a
   warehouse, then make ingestion incremental and idempotent with upserts.
2. Add run-level structured logs, quality metrics, and alerts for rejection rate,
   domain conflicts, schema drift, and late-arriving observations.
3. Stream or batch large inputs instead of loading every source into memory, and
   add a read-only query interface for canonical companies.
