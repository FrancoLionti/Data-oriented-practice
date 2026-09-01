# Evaluation rubric

## 1. Correctness and data quality — 30 points

- Safe entity resolution and deduplication.
- Correct source precedence.
- Correct handling of timestamps and mutable observations.
- Accurate interaction counts and latest activity.
- Malformed and ambiguous records handled deliberately.
- Deterministic identifiers and outputs.

## 2. Reliability and system design — 25 points

- Idempotent reruns.
- Failure isolation and useful rejection records.
- Clear boundaries between parsing, normalization, matching, and output.
- Reasonable path toward incremental processing and persistent identity.
- Awareness of scale, late-arriving data, and concurrency concerns.

## 3. Code quality and testing — 20 points

- Readable structure and naming.
- Focused functions or components.
- Useful type hints or data models where they improve clarity.
- Tests cover business behavior and edge cases, not only happy paths.
- No unnecessary framework or abstraction overhead.

## 4. Communication and trade-offs — 15 points

- Assumptions are explicit.
- Decisions can be defended in plain language.
- Candidate distinguishes the timeboxed implementation from a production design.
- Candidate can explain what was intentionally omitted.
- Technical discussion works in both Spanish and English.

## 5. Use of AI — 10 points

- Work is decomposed into clear requests.
- Generated code is inspected and tested.
- Incorrect or overcomplicated suggestions are challenged.
- Candidate remains able to explain every important part of the submitted solution.

## Major warning signs

- Different valid domains silently merged because names looked similar.
- Non-deterministic output or identifiers.
- A single malformed row crashes the complete run.
- Large framework added while the core pipeline remains incomplete.
- Tests generated but never executed or understood.
- Candidate cannot explain code produced by the AI assistant.
