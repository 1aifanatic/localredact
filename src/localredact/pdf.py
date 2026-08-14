# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""Coordinate-aware, irreversible PDF redaction."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .errors import (
    EncryptedPDFError,
    ImageOnlyPageError,
    PDFError,
    VerificationError,
)
from .models import Detection, InstructionPlan, RedactionResult
from .patterns import find_pattern_matches


@dataclass(frozen=True)
class _Character:
    value: str
    rect: pymupdf.Rect | None
    line: int


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    category: str
    value: str


@dataclass(frozen=True)
class _LocatedCandidate:
    page_index: int
    category: str
    value: str
    rects: tuple[pymupdf.Rect, ...]


class _PageText:
    def __init__(self, characters: list[_Character]) -> None:
        self.characters = characters
        self.text = "".join(character.value for character in characters)

    @classmethod
    def extract(
        cls,
        page: pymupdf.Page,
        *,
        ocr: bool,
        ocr_language: str,
        ocr_dpi: int,
    ) -> _PageText:
        try:
            if ocr:
                textpage = page.get_textpage_ocr(
                    language=ocr_language,
                    dpi=ocr_dpi,
                    full=True,
                )
                raw = page.get_text("rawdict", textpage=textpage, sort=True)
            else:
                raw = page.get_text("rawdict", sort=True)
        except Exception as error:  # PyMuPDF exposes backend-specific OCR errors.
            if ocr:
                raise PDFError(
                    "Local OCR failed. Install Tesseract with the requested language "
                    "data, then retry with --ocr. No cloud fallback was attempted."
                ) from error
            raise PDFError("Text extraction failed for a PDF page.") from error

        characters: list[_Character] = []
        line_number = 0
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_had_text = False
                for span in line.get("spans", []):
                    for character in span.get("chars", []):
                        value = character.get("c", "")
                        if not value:
                            continue
                        rect = pymupdf.Rect(character["bbox"])
                        characters.append(_Character(value, rect, line_number))
                        line_had_text = True
                if line_had_text:
                    characters.append(_Character("\n", None, line_number))
                    line_number += 1
        return cls(characters)

    def rects_for(self, start: int, end: int) -> tuple[pymupdf.Rect, ...]:
        boxes = [
            character
            for character in self.characters[start:end]
            if character.rect is not None and not character.value.isspace()
        ]
        if not boxes:
            return ()
        merged: list[pymupdf.Rect] = []
        current = pymupdf.Rect(boxes[0].rect)
        current_line = boxes[0].line
        for box in boxes[1:]:
            rect = pymupdf.Rect(box.rect)
            same_run = (
                box.line == current_line
                and rect.x0 <= current.x1 + 2.0
                and rect.y0 <= current.y1
                and rect.y1 >= current.y0
            )
            if same_run:
                current.include_rect(rect)
            else:
                merged.append(_padded(current))
                current = rect
                current_line = box.line
        merged.append(_padded(current))
        return tuple(merged)


def _padded(rect: pymupdf.Rect, amount: float = 0.75) -> pymupdf.Rect:
    return pymupdf.Rect(
        rect.x0 - amount,
        rect.y0 - amount,
        rect.x1 + amount,
        rect.y1 + amount,
    )


_PRIORITY = {
    "literal": 100,
    "labeled_field": 95,
    "bounded_text": 95,
    "credit_card": 90,
    "ssn": 90,
    "iban": 90,
    "api_key": 90,
    "bearer_token": 90,
    "jwt": 90,
    "date_of_birth": 80,
    "account_number": 80,
    "routing_number": 80,
    "passport": 80,
    "driver_license": 80,
    "medical_record": 80,
    "health_insurance": 80,
    "tax_id": 80,
}


def _literal_candidates(text: str, literals: Iterable[str]) -> list[_Candidate]:
    output: list[_Candidate] = []
    for literal in literals:
        # PDF producers often split a visually continuous phrase into separate
        # text runs or lines. Treat whitespace in a quoted literal flexibly.
        pieces = [re.escape(piece) for piece in re.split(r"\s+", literal.strip())]
        expression = r"\s+".join(pieces)
        for match in re.finditer(expression, text, re.IGNORECASE):
            output.append(_Candidate(match.start(), match.end(), "literal", match.group(0)))
    return output


def _directive_candidates(text: str, plan: InstructionPlan) -> list[_Candidate]:
    output: list[_Candidate] = []
    for directive in plan.directives:
        if directive.kind == "after":
            expression = re.compile(
                re.escape(directive.label) + r"[ \t]*(?::|=|-)?[ \t]*(?P<value>[^\r\n;|]{1,200})",
                re.IGNORECASE,
            )
            category = "labeled_field"
        elif directive.kind == "between" and directive.end_label:
            expression = re.compile(
                re.escape(directive.label) + r"(?P<value>.*?)" + re.escape(directive.end_label),
                re.IGNORECASE | re.DOTALL,
            )
            category = "bounded_text"
        else:
            continue
        for match in expression.finditer(text):
            start, end = match.span("value")
            raw = text[start:end]
            leading = len(raw) - len(raw.lstrip())
            trailing = len(raw) - len(raw.rstrip())
            start += leading
            end -= trailing
            if start < end:
                output.append(_Candidate(start, end, category, text[start:end]))
    return output


def _resolve_candidates(
    candidates: Iterable[_Candidate], excluded: Iterable[str]
) -> list[_Candidate]:
    keep = {_normalized(value) for value in excluded}
    usable = [candidate for candidate in candidates if _normalized(candidate.value) not in keep]
    ordered = sorted(
        usable,
        key=lambda candidate: (
            -_PRIORITY.get(candidate.category, 50),
            candidate.start,
            -(candidate.end - candidate.start),
        ),
    )
    selected: list[_Candidate] = []
    for candidate in ordered:
        if any(candidate.start < other.end and other.start < candidate.end for other in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda candidate: (candidate.start, candidate.end))


def _find_candidates(text: str, plan: InstructionPlan) -> list[_Candidate]:
    candidates = [
        _Candidate(item.start, item.end, item.category, item.value)
        for item in find_pattern_matches(text, plan.categories)
    ]
    candidates.extend(_literal_candidates(text, plan.literals))
    candidates.extend(_directive_candidates(text, plan))
    return _resolve_candidates(candidates, plan.exclude_values)


def _digest(value: str, key: bytes) -> str:
    return hmac.new(key, _normalized(value).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _default_output(source: Path) -> Path:
    return source.with_name(f"{source.stem}.redacted.pdf")


def _authenticate(document: pymupdf.Document, password: str | None) -> None:
    if not document.needs_pass:
        return
    if not password or not document.authenticate(password):
        raise EncryptedPDFError(
            "The PDF is encrypted. Supply a valid password; it is used only in memory."
        )


def _selected_pages(plan: InstructionPlan, page_count: int) -> list[int]:
    selected = [
        index for index in range(page_count) if plan.page_scope.includes(index + 1, page_count)
    ]
    requested = set(plan.page_scope.pages or ())
    missing = sorted(page for page in requested if page > page_count)
    if missing:
        raise PDFError(
            f"The instruction selects page {missing[0]}, but the PDF has {page_count} page(s)."
        )
    return selected


def _looks_image_only(page: pymupdf.Page, page_text: _PageText) -> bool:
    visible_characters = len(re.sub(r"\s", "", page_text.text))
    images = page.get_images(full=True)
    if not images:
        return False
    if visible_characters < 20:
        return True
    page_area = max(page.rect.get_area(), 1)
    for image in images:
        try:
            if any(rect.get_area() / page_area >= 0.5 for rect in page.get_image_rects(image[0])):
                return visible_characters < 50
        except RuntimeError:
            continue
    return False


def _sanitize(document: pymupdf.Document) -> None:
    """Remove common non-page payloads without storing their values."""

    document.scrub(
        attached_files=True,
        clean_pages=True,
        embedded_files=True,
        hidden_text=False,
        javascript=True,
        metadata=True,
        redactions=False,
        redact_images=0,
        remove_links=True,
        reset_fields=True,
        reset_responses=True,
        thumbnails=True,
        xml_metadata=True,
    )


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _verify(
    path: Path,
    located: list[_LocatedCandidate],
    *,
    password: str | None,
    ocr: bool,
    ocr_language: str,
    ocr_dpi: int,
    digest_key: bytes,
) -> None:
    by_page: dict[int, list[_LocatedCandidate]] = {}
    for candidate in located:
        by_page.setdefault(candidate.page_index, []).append(candidate)
    with pymupdf.open(path) as document:
        _authenticate(document, password)
        for page_index, candidates in by_page.items():
            extracted = _PageText.extract(
                document[page_index],
                ocr=ocr,
                ocr_language=ocr_language,
                ocr_dpi=ocr_dpi,
            ).text
            normalized_page = _normalized(extracted)
            for candidate in candidates:
                if _normalized(candidate.value) in normalized_page:
                    raise VerificationError(
                        "Verification found a remaining value on "
                        f"page {page_index + 1} for {candidate.category} "
                        f"(digest {_digest(candidate.value, digest_key)})."
                    )


def redact_pdf(
    source: str | os.PathLike[str],
    instruction: InstructionPlan,
    output: str | os.PathLike[str] | None = None,
    *,
    password: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    verify: bool = True,
    sanitize: bool = True,
    ocr: bool = False,
    ocr_language: str = "eng",
    ocr_dpi: int = 150,
    allow_image_only_pages: bool = False,
    max_file_size: int = 250 * 1024 * 1024,
    max_redactions: int = 10_000,
) -> RedactionResult:
    """Detect and irreversibly redact a PDF according to a compiled plan."""

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise PDFError(f"Input PDF does not exist: {source_path}")
    if source_path.suffix.casefold() != ".pdf":
        raise PDFError("Only PDF input is supported by this command.")
    if source_path.stat().st_size > max_file_size:
        raise PDFError(f"Input PDF exceeds the {max_file_size // (1024 * 1024)} MB safety limit.")

    output_path = Path(output).expanduser().resolve() if output else _default_output(source_path)
    if output_path == source_path:
        raise PDFError("Refusing to overwrite the source PDF. Choose a different output path.")
    if output_path.exists() and not overwrite and not dry_run:
        raise PDFError(f"Output already exists: {output_path}. Use overwrite=True to replace it.")

    digest_key = os.urandom(32)
    located: list[_LocatedCandidate] = []
    warnings: list[str] = list(instruction.warnings)
    used_ocr = False
    temp_path: Path | None = None

    try:
        with pymupdf.open(source_path) as document:
            _authenticate(document, password)
            selected = _selected_pages(instruction, document.page_count)
            for page_index in selected:
                page = document[page_index]
                page_text = _PageText.extract(
                    page,
                    ocr=ocr,
                    ocr_language=ocr_language,
                    ocr_dpi=ocr_dpi,
                )
                used_ocr = used_ocr or ocr
                if _looks_image_only(page, page_text):
                    message = (
                        f"Page {page_index + 1} appears image-only and was not safely searchable."
                    )
                    if not allow_image_only_pages:
                        raise ImageOnlyPageError(
                            message
                            + " Retry with --ocr using locally installed Tesseract, or explicitly "
                            "allow image-only pages after manual review."
                        )
                    warnings.append(
                        message + " It was explicitly allowed and may contain unredacted data."
                    )
                    continue

                for candidate in _find_candidates(page_text.text, instruction):
                    rects = page_text.rects_for(candidate.start, candidate.end)
                    if rects:
                        located.append(
                            _LocatedCandidate(
                                page_index,
                                candidate.category,
                                candidate.value,
                                rects,
                            )
                        )
                        if len(located) > max_redactions:
                            raise PDFError(
                                f"Detection count exceeded the {max_redactions} redaction safety limit."
                            )

            detections = tuple(
                Detection(
                    page=item.page_index + 1,
                    category=item.category,
                    digest=_digest(item.value, digest_key),
                    character_count=len(item.value),
                    rectangles=len(item.rects),
                )
                for item in located
            )
            if dry_run:
                return RedactionResult(
                    source_path,
                    None,
                    instruction,
                    detections,
                    len(selected),
                    used_ocr,
                    tuple(warnings),
                    False,
                )

            for page_index in selected:
                page = document[page_index]
                page_items = [item for item in located if item.page_index == page_index]
                for item in page_items:
                    for rect in item.rects:
                        page.add_redact_annot(
                            rect,
                            fill=(0, 0, 0),
                            cross_out=False,
                        )
                if page_items:
                    page.apply_redactions(images=2, graphics=1, text=0)

            if sanitize:
                _sanitize(document)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{output_path.stem}.",
                suffix=".tmp.pdf",
                dir=output_path.parent,
            )
            os.close(file_descriptor)
            temp_path = Path(temporary_name)
            document.save(
                temp_path,
                garbage=4,
                clean=True,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                encryption=pymupdf.PDF_ENCRYPT_KEEP,
                preserve_metadata=False,
            )

        if verify:
            _verify(
                temp_path,
                located,
                password=password,
                ocr=ocr,
                ocr_language=ocr_language,
                ocr_dpi=ocr_dpi,
                digest_key=digest_key,
            )
        os.replace(temp_path, output_path)
        temp_path = None
        return RedactionResult(
            source_path,
            output_path,
            instruction,
            detections,
            len(selected),
            used_ocr,
            tuple(warnings),
            verify,
        )
    except pymupdf.FileDataError as error:
        raise PDFError("The input is not a readable PDF or is damaged.") from error
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
