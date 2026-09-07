"""Pure, deterministic normalization helpers for source data."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from urllib.parse import urlsplit


_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LEGAL_SUFFIXES = (
    ("limited",),
    ("incorporated",),
    ("corporation",),
    ("company",),
    ("gmbh",),
    ("corp",),
    ("inc",),
    ("ltd",),
    ("llc",),
    ("plc",),
    ("srl",),
    ("sa",),
    ("co",),
    ("l", "l", "c"),
    ("s", "a"),
)


def normalize_domain(value: object) -> str | None:
    """Return a lowercase hostname without URL decoration, or ``None``.

    The function accepts both bare hostnames and URLs. It intentionally
    rejects single-label hosts and malformed labels because they are unsafe
    cross-source identity keys for this exercise.
    """

    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    candidate = raw if "://" in raw else f"//{raw}"
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        # Accessing .port validates both its syntax and range.
        _ = parsed.port
    except ValueError:
        return None

    if not hostname:
        return None

    hostname = hostname.rstrip(".").casefold()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return None

    if len(ascii_hostname) > 253 or "." not in ascii_hostname:
        return None

    labels = ascii_hostname.split(".")
    if any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        return None

    return ascii_hostname


def normalize_name(value: object) -> str | None:
    """Create a conservative comparison key for a company name.

    Accents, punctuation, whitespace, case, and common trailing legal suffixes
    are ignored. Remaining tokens are concatenated so variants such as
    ``Vector Pay`` and ``VectorPay`` compare equally.
    """

    if not isinstance(value, str):
        return None

    decomposed = unicodedata.normalize("NFKD", value.casefold().strip())
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    tokens = re.findall(r"[a-z0-9]+", without_accents)

    removed_suffix = True
    while tokens and removed_suffix:
        removed_suffix = False
        for suffix in _LEGAL_SUFFIXES:
            suffix_length = len(suffix)
            if tuple(tokens[-suffix_length:]) == suffix:
                del tokens[-suffix_length:]
                removed_suffix = True
                break

    normalized = "".join(tokens)
    return normalized or None


def parse_integer(
    value: object,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """Parse an integer without silently rounding fractional values."""

    if isinstance(value, bool) or value is None:
        return None

    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None

    if not number.is_finite() or number != number.to_integral_value():
        return None

    result = int(number)
    if minimum is not None and result < minimum:
        return None
    if maximum is not None and result > maximum:
        return None
    return result


def parse_usd_amount(value: object) -> int | None:
    """Parse a non-negative, whole-dollar USD amount."""

    cleaned = value
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
    return parse_integer(cleaned, minimum=0)


def parse_founded_year(value: object) -> int | None:
    """Parse a deterministic, plausible company founding year."""

    return parse_integer(value, minimum=1800, maximum=2100)


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp and normalize it to UTC.

    Naive timestamps are rejected because assuming a timezone would make the
    event instant ambiguous.
    """

    if not isinstance(value, str) or not value.strip():
        return None

    candidate = value.strip()
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def format_timestamp(value: datetime | None) -> str | None:
    """Serialize an aware datetime in a canonical UTC ISO-8601 form."""

    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None

    utc_value = value.astimezone(UTC)
    timespec = "microseconds" if utc_value.microsecond else "seconds"
    return utc_value.isoformat(timespec=timespec).replace("+00:00", "Z")
