# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""Auditable, local-only detectors used by the PDF engine.

The expressions intentionally favor high-confidence matches. Ambiguous identifiers
such as account, passport, and medical-record numbers require a nearby label.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

Validator = Callable[[str], bool]


@dataclass(frozen=True)
class PatternSpec:
    category: str
    expression: str
    group: str | int | None = None
    validator: Validator | None = None
    flags: int = re.IGNORECASE | re.MULTILINE


@dataclass(frozen=True)
class PatternMatch:
    start: int
    end: int
    category: str
    value: str


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _luhn(value: str) -> bool:
    digits = _digits(value)
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _valid_ipv4(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def _valid_iban(value: str) -> bool:
    compact = re.sub(r"\s", "", value).upper()
    if not 15 <= len(compact) <= 34 or not compact[:2].isalpha():
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        str(ord(character) - 55) if character.isalpha() else character for character in rearranged
    )
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


DATE_VALUE = (
    r"(?:"
    r"\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})"
    r"|(?:\d{4})[/-]\d{1,2}[/-]\d{1,2}"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r")"
)


PATTERNS: tuple[PatternSpec, ...] = (
    PatternSpec(
        "email",
        r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"(?:[A-Z0-9-]+\.)+[A-Z]{2,63}(?![\w.-])",
    ),
    PatternSpec(
        "phone",
        r"(?<!\w)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]"
        r"\d{3}[ .-]\d{4}(?:\s*(?:x|ext\.?|extension)\s*\d{1,6})?(?!\w)",
    ),
    PatternSpec(
        "phone",
        r"(?<!\w)\+(?:\d[ .-]?){8,14}\d(?!\w)",
    ),
    PatternSpec(
        "ssn",
        r"(?<!\d)(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}(?!\d)",
    ),
    PatternSpec(
        "credit_card",
        r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)",
        validator=_luhn,
    ),
    PatternSpec(
        "ip_address",
        r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])",
        validator=_valid_ipv4,
    ),
    PatternSpec(
        "url",
        r"\b(?:https?://|www\.)[^\s<>\]\[()]+[^\s<>\]\[().,;:!?]",
    ),
    PatternSpec("date", rf"\b{DATE_VALUE}\b"),
    PatternSpec(
        "date_of_birth",
        rf"\b(?:date\s+of\s+birth|d\.?o\.?b\.?|born(?:\s+on)?)"
        rf"\s*(?:is|:|-)\s*(?P<value>{DATE_VALUE})\b",
        group="value",
    ),
    PatternSpec(
        "address",
        r"\b\d{1,6}\s+(?:[\w.'’-]+\s+){0,7}"
        r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|"
        r"lane|ln\.?|drive|dr\.?|court|ct\.?|circle|way|highway|hwy\.?)\b",
    ),
    PatternSpec(
        "address",
        r"\b(?:mailing\s+address|home\s+address|street\s+address|address)"
        r"\s*(?:is|:|-)\s*(?P<value>[^\r\n;|]{4,120})",
        group="value",
    ),
    PatternSpec(
        "name",
        r"\b(?:full\s+name|customer\s+name|patient\s+name|employee\s+name|"
        r"applicant\s+name|client\s+name|account\s+holder|name)"
        r"\s*(?:is|:|-)\s*(?P<value>[^\r\n,;|]{2,80})",
        group="value",
    ),
    PatternSpec(
        "name",
        r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+"
        r"(?P<value>[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){1,3})\b",
        group="value",
        flags=re.MULTILINE,
    ),
    PatternSpec(
        "account_number",
        r"\b(?:bank\s+account|account(?:\s+number|\s+no\.?|\s*#))"
        r"\s*(?:is|:|-)\s*(?P<value>[A-Z0-9][A-Z0-9 -]{3,33})",
        group="value",
    ),
    PatternSpec(
        "routing_number",
        r"\b(?:routing|aba)(?:\s+number|\s+no\.?|\s*#)?"
        r"\s*(?:is|:|-)\s*(?P<value>\d{9})\b",
        group="value",
    ),
    PatternSpec(
        "passport",
        r"\bpassport(?:\s+number|\s+no\.?|\s*#)?"
        r"\s*(?:is|:|-)\s*(?P<value>[A-Z0-9][A-Z0-9 -]{4,19})",
        group="value",
    ),
    PatternSpec(
        "driver_license",
        r"\b(?:driver'?s?\s+licen[cs]e|dl)(?:\s+number|\s+no\.?|\s*#)?"
        r"\s*(?:is|:|-)\s*(?P<value>[A-Z0-9][A-Z0-9 -]{3,19})",
        group="value",
    ),
    PatternSpec(
        "medical_record",
        r"\b(?:medical\s+record|patient)(?:\s+number|\s+no\.?|\s*#|\s+id)"
        r"\s*(?:is|:|-)\s*(?P<value>[A-Z0-9][A-Z0-9 -]{3,24})",
        group="value",
    ),
    PatternSpec(
        "tax_id",
        r"\b(?:tax(?:payer)?\s+(?:id|number)|tin|ein)"
        r"\s*(?:is|:|-)\s*(?P<value>[A-Z0-9][A-Z0-9 -]{4,19})",
        group="value",
    ),
    PatternSpec(
        "health_insurance",
        r"\b(?:health\s+insurance|insurance|member|policy)"
        r"(?:\s+number|\s+no\.?|\s*#|\s+id)"
        r"\s*(?:is|:|-)\s*(?P<value>[A-Z0-9][A-Z0-9 -]{3,24})",
        group="value",
    ),
    PatternSpec(
        "iban",
        r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}(?![A-Z0-9])",
        validator=_valid_iban,
    ),
    PatternSpec(
        "api_key",
        r"\b(?:api[_ -]?key|secret[_ -]?key|access[_ -]?token)"
        r"\s*(?:=|:|is)\s*[\"']?(?P<value>[A-Z0-9_./+\-=]{8,})",
        group="value",
    ),
    PatternSpec(
        "bearer_token",
        r"\bBearer\s+(?P<value>[A-Z0-9._~+/\-=]{12,})",
        group="value",
    ),
    PatternSpec(
        "jwt",
        r"(?<![A-Z0-9_-])eyJ[A-Z0-9_-]{5,}\.[A-Z0-9_-]{5,}\.[A-Z0-9_-]{5,}(?![A-Z0-9_-])",
    ),
)


SUPPORTED_CATEGORIES = frozenset(spec.category for spec in PATTERNS)


def find_pattern_matches(text: str, categories: Iterable[str]) -> list[PatternMatch]:
    """Find built-in matches for the requested categories."""

    wanted = set(categories)
    results: list[PatternMatch] = []
    for spec in PATTERNS:
        if spec.category not in wanted:
            continue
        expression = re.compile(spec.expression, spec.flags)
        for match in expression.finditer(text):
            start, end = match.span(spec.group) if spec.group is not None else match.span()
            value = text[start:end].strip()
            if not value:
                continue
            # Keep coordinate offsets aligned after stripping whitespace.
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            trailing = len(text[start:end]) - len(text[start:end].rstrip())
            start += leading
            end -= trailing
            if spec.validator and not spec.validator(value):
                continue
            results.append(PatternMatch(start, end, spec.category, value))
    return results
