# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""A tiny deterministic compiler from plain English to redaction policy.

This is deliberately not a chatbot or model. It recognizes a documented,
auditable vocabulary and refuses instructions it cannot safely understand.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .errors import InstructionError
from .models import FieldDirective, InstructionPlan, PageScope
from .patterns import SUPPORTED_CATEGORIES

CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "email": ("email addresses", "email address", "e-mail addresses", "emails", "email"),
    "phone": (
        "telephone numbers",
        "telephone number",
        "mobile numbers",
        "phone numbers",
        "phone number",
        "telephones",
        "phones",
    ),
    "ssn": ("social security numbers", "social security number", "ssns", "ssn"),
    "credit_card": (
        "credit card numbers",
        "credit card number",
        "debit card numbers",
        "payment card numbers",
        "card numbers",
        "credit cards",
    ),
    "ip_address": ("ip addresses", "ip address", "ipv4 addresses", "ipv4 address"),
    "url": ("web addresses", "website addresses", "urls", "url"),
    "date_of_birth": (
        "dates of birth",
        "date of birth",
        "birth dates",
        "birth date",
        "dobs",
        "dob",
    ),
    "date": ("calendar dates", "all dates", "dates", "date"),
    "address": (
        "mailing addresses",
        "street addresses",
        "home addresses",
        "postal addresses",
        "addresses",
        "address",
    ),
    "name": (
        "customer names",
        "customer name",
        "patient names",
        "patient name",
        "employee names",
        "employee name",
        "full names",
        "people's names",
        "person names",
        "names",
        "name",
    ),
    "account_number": (
        "bank account numbers",
        "bank account number",
        "account numbers",
        "account number",
    ),
    "routing_number": ("routing numbers", "routing number", "aba numbers", "aba number"),
    "passport": ("passport numbers", "passport number", "passports", "passport"),
    "driver_license": (
        "driver's license numbers",
        "drivers license numbers",
        "driving licence numbers",
        "driver's licenses",
        "drivers licenses",
        "driving licences",
    ),
    "medical_record": (
        "medical record numbers",
        "medical record number",
        "patient ids",
        "patient id",
        "mrns",
        "mrn",
    ),
    "tax_id": (
        "tax identification numbers",
        "tax identification number",
        "tax ids",
        "tax id",
        "eins",
        "ein",
        "tins",
        "tin",
    ),
    "health_insurance": (
        "health insurance numbers",
        "health insurance number",
        "insurance member ids",
        "insurance member id",
        "policy numbers",
        "policy number",
    ),
    "iban": ("international bank account numbers", "iban numbers", "ibans", "iban"),
    "api_key": (
        "api keys",
        "api key",
        "access tokens",
        "access token",
        "secret keys",
        "secret key",
    ),
    "bearer_token": ("bearer tokens", "bearer token"),
    "jwt": ("json web tokens", "json web token", "jwts", "jwt"),
}

GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    "pii": (
        "personally identifiable information",
        "personal identifying information",
        "personal information",
        "sensitive personal information",
        "all sensitive information",
        "all personal data",
        "personal data",
        "pii",
    ),
    "contact": ("contact information", "contact details", "contact data"),
    "financial": (
        "financial information",
        "financial details",
        "payment information",
        "banking information",
    ),
    "identity": (
        "government ids",
        "government identification",
        "identity documents",
        "identification numbers",
    ),
    "health": ("protected health information", "health information", "medical information", "phi"),
    "credentials": ("credentials", "authentication secrets", "secrets"),
}

GROUP_CATEGORIES: dict[str, set[str]] = {
    "pii": {
        "email",
        "phone",
        "ssn",
        "credit_card",
        "ip_address",
        "date_of_birth",
        "address",
        "name",
        "account_number",
        "routing_number",
        "passport",
        "driver_license",
        "medical_record",
        "tax_id",
        "health_insurance",
        "iban",
    },
    "contact": {"email", "phone", "address"},
    "financial": {"credit_card", "account_number", "routing_number", "iban", "tax_id"},
    "identity": {"ssn", "passport", "driver_license", "tax_id"},
    "health": {"medical_record", "health_insurance", "date_of_birth", "name", "address"},
    "credentials": {"api_key", "bearer_token", "jwt"},
}

_ACTION = re.compile(r"\b(?:redact|hide|remove|mask|black\s*out|obscure|erase)\b", re.IGNORECASE)
_EXCEPTION = re.compile(
    r"\b(?:except(?:\s+for)?|excluding|but\s+not|but\s+keep|leave)\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"(?P<quote>['\"])(?P<value>.+?)(?P=quote)")
_CURLY_QUOTED = re.compile(r"[‘“](?P<value>.+?)[’”]")
_AFTER = re.compile(
    r"\b(?:(?:everything|text|content|value|field)\s+)?(?:after|following)\s+"
    r"(?P<quote>['\"])(?P<label>.+?)(?P=quote)",
    re.IGNORECASE,
)
_NAMED_FIELD = re.compile(
    r"\b(?:field|value)\s+(?:named|labelled|labeled|called)\s+"
    r"(?P<quote>['\"])(?P<label>.+?)(?P=quote)",
    re.IGNORECASE,
)
_BETWEEN = re.compile(
    r"\b(?:(?:everything|text|content)\s+)?between\s+"
    r"(?P<q1>['\"])(?P<start>.+?)(?P=q1)\s+and\s+"
    r"(?P<q2>['\"])(?P<end>.+?)(?P=q2)",
    re.IGNORECASE,
)
_PAGE_SCOPE = re.compile(
    r"\bpages?\s+(?P<pages>\d+(?:\s*(?:-|–|—|to|through)\s*\d+)?"
    r"(?:\s*(?:,|and)\s*\d+)*)",
    re.IGNORECASE,
)

_IGNORED_WORDS = {
    "a",
    "absolutely",
    "all",
    "an",
    "and",
    "any",
    "as",
    "black",
    "document",
    "each",
    "end",
    "every",
    "everywhere",
    "everything",
    "field",
    "fields",
    "file",
    "from",
    "hide",
    "in",
    "information",
    "it",
    "line",
    "mask",
    "of",
    "on",
    "only",
    "or",
    "out",
    "pdf",
    "please",
    "redact",
    "remove",
    "sensitive",
    "that",
    "the",
    "these",
    "this",
    "throughout",
    "until",
    "values",
    "visible",
    "well",
}


def _alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE)


def _collect_aliases(
    text: str, aliases: dict[str, tuple[str, ...]]
) -> tuple[set[str], list[tuple[int, int]]]:
    candidates: list[tuple[int, int, str]] = []
    for name, phrases in aliases.items():
        for phrase in phrases:
            candidates.extend(
                (match.start(), match.end(), name)
                for match in _alias_pattern(phrase).finditer(text)
            )
    found: set[str] = set()
    spans: list[tuple[int, int]] = []
    for start, end, name in sorted(
        candidates,
        key=lambda item: (-(item[1] - item[0]), item[0], item[2]),
    ):
        if any(start < used_end and used_start < end for used_start, used_end in spans):
            continue
        found.add(name)
        spans.append((start, end))
    return found, spans


def _quoted_values(
    text: str, consumed: Iterable[tuple[int, int]] = ()
) -> tuple[list[str], list[tuple[int, int]]]:
    blocked = list(consumed)
    values: list[str] = []
    spans: list[tuple[int, int]] = []
    for expression in (_QUOTED, _CURLY_QUOTED):
        for match in expression.finditer(text):
            if any(start <= match.start() and match.end() <= end for start, end in blocked):
                continue
            value = match.group("value").strip()
            if value:
                values.append(value)
                spans.append(match.span())
    return values, spans


def _directives(text: str) -> tuple[list[FieldDirective], list[tuple[int, int]]]:
    directives: list[FieldDirective] = []
    spans: list[tuple[int, int]] = []
    for expression in (_AFTER, _NAMED_FIELD):
        for match in expression.finditer(text):
            directives.append(FieldDirective("after", match.group("label").strip()))
            spans.append(match.span())
    for match in _BETWEEN.finditer(text):
        directives.append(
            FieldDirective(
                "between",
                match.group("start").strip(),
                match.group("end").strip(),
            )
        )
        spans.append(match.span())
    return directives, spans


def _parse_pages(text: str) -> tuple[PageScope, list[tuple[int, int]]]:
    selected: set[int] = set()
    spans: list[tuple[int, int]] = []
    for match in _PAGE_SCOPE.finditer(text):
        spans.append(match.span())
        expression = match.group("pages")
        consumed: list[tuple[int, int]] = []
        for range_match in re.finditer(
            r"(\d+)\s*(?:-|–|—|to|through)\s*(\d+)", expression, re.IGNORECASE
        ):
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start < 1 or end < start or end - start > 10_000:
                raise InstructionError(f"Invalid page range: {range_match.group(0)!r}")
            selected.update(range(start, end + 1))
            consumed.append(range_match.span())
        masked = list(expression)
        for start, end in consumed:
            masked[start:end] = " " * (end - start)
        selected.update(int(number) for number in re.findall(r"\d+", "".join(masked)))
    lowered = text.casefold()
    if "first page" in lowered:
        selected.add(1)
        first = re.search(r"\bfirst\s+page\b", text, re.IGNORECASE)
        if first:
            spans.append(first.span())
    include_last = bool(re.search(r"\blast\s+page\b", text, re.IGNORECASE))
    if include_last:
        last = re.search(r"\blast\s+page\b", text, re.IGNORECASE)
        if last:
            spans.append(last.span())
    if not selected and not include_last:
        return PageScope(), spans
    if any(page < 1 for page in selected):
        raise InstructionError("PDF page numbers start at 1.")
    return PageScope(tuple(sorted(selected)), include_last), spans


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return tuple(output)


def _unknown_words(text: str, known_spans: Iterable[tuple[int, int]]) -> list[str]:
    masked = list(text)
    for start, end in known_spans:
        masked[start:end] = " " * (end - start)
    words = re.findall(r"[A-Za-z][A-Za-z0-9'_-]*", "".join(masked))
    return sorted(
        {word for word in words if word.casefold() not in _IGNORED_WORDS}, key=str.casefold
    )


def parse_instruction(instruction: str, *, strict: bool = True) -> InstructionPlan:
    """Compile a documented subset of plain English into a safe policy.

    Strict mode rejects partially understood instructions. Callers can opt into
    lenient mode, but warnings remain attached to the returned plan.
    """

    instruction = instruction.strip()
    if not instruction:
        raise InstructionError("The redaction instruction is empty.")
    if not _ACTION.search(instruction):
        raise InstructionError(
            "Start the instruction with an action such as 'redact', 'hide', or 'remove'."
        )

    exception = _EXCEPTION.search(instruction)
    main = instruction[: exception.start()] if exception else instruction
    excluded = instruction[exception.end() :] if exception else ""

    categories, category_spans = _collect_aliases(main, CATEGORY_ALIASES)
    groups, group_spans = _collect_aliases(main, GROUP_ALIASES)
    for group in groups:
        categories.update(GROUP_CATEGORIES[group])

    if re.search(
        r"\b(?:redact|hide|remove|mask)\s+(?:absolutely\s+)?(?:all|everything)"
        r"(?=\s+(?:in|from|on|throughout)\b|\s*[.!]?$)",
        main,
        re.IGNORECASE,
    ):
        # "everything after 'Label'" is a field directive, not the global preset.
        if not re.search(r"\beverything\s+(?:after|between|following)\b", main, re.IGNORECASE):
            categories.update(SUPPORTED_CATEGORIES)

    excluded_categories, excluded_category_spans = _collect_aliases(excluded, CATEGORY_ALIASES)
    excluded_groups, excluded_group_spans = _collect_aliases(excluded, GROUP_ALIASES)
    for group in excluded_groups:
        excluded_categories.update(GROUP_CATEGORIES[group])
    categories.difference_update(excluded_categories)

    directives, directive_spans = _directives(main)
    literals, literal_spans = _quoted_values(main, directive_spans)
    exclude_values, excluded_literal_spans = _quoted_values(excluded)
    page_scope, page_spans = _parse_pages(main)

    known_spans = category_spans + group_spans + directive_spans + literal_spans + page_spans
    known_spans.extend(match.span() for match in _ACTION.finditer(main))
    warnings: list[str] = []
    unknown = _unknown_words(main, known_spans)
    if unknown:
        warnings.append("Unrecognized instruction word(s): " + ", ".join(unknown))
    unknown_exclusions = _unknown_words(
        excluded,
        excluded_category_spans + excluded_group_spans + excluded_literal_spans,
    )
    if unknown_exclusions:
        warnings.append("Unrecognized exception word(s): " + ", ".join(unknown_exclusions))

    categories.intersection_update(SUPPORTED_CATEGORIES)
    if not categories and not literals and not directives:
        examples = (
            "Try: redact email addresses and phone numbers; "
            "redact the field labeled 'Employee ID'; or redact 'Project Falcon'."
        )
        raise InstructionError(f"No supported redaction target was found. {examples}")
    if warnings and strict:
        raise InstructionError(
            warnings[0] + ". Rephrase using supported field names, quote an exact value, "
            "or use strict=False after reviewing the plan."
        )

    return InstructionPlan(
        original=instruction,
        categories=tuple(sorted(categories)),
        literals=_dedupe(literals),
        directives=tuple(directives),
        exclude_values=_dedupe(exclude_values),
        page_scope=page_scope,
        warnings=tuple(warnings),
    )


def supported_targets() -> dict[str, list[str]]:
    """Return the public vocabulary for help screens and integrations."""

    return {
        "categories": sorted(SUPPORTED_CATEGORIES),
        "groups": sorted(GROUP_CATEGORIES),
    }
