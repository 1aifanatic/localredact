# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""Small immutable value objects shared by the parser and PDF engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FieldDirective:
    """Redact a value located relative to visible labels or markers."""

    kind: str
    label: str
    end_label: str | None = None


@dataclass(frozen=True)
class PageScope:
    """A human-facing, one-based PDF page selection."""

    pages: tuple[int, ...] | None = None
    include_last: bool = False

    def includes(self, page_number: int, page_count: int) -> bool:
        if self.pages is None and not self.include_last:
            return True
        return bool(
            (self.pages and page_number in self.pages)
            or (self.include_last and page_number == page_count)
        )

    def describe(self) -> str:
        if self.pages is None and not self.include_last:
            return "all pages"
        selected = [str(page) for page in self.pages or ()]
        if self.include_last:
            selected.append("last")
        return "pages " + ", ".join(selected)


@dataclass(frozen=True)
class InstructionPlan:
    """Deterministic interpretation of a plain-English instruction."""

    original: str
    categories: tuple[str, ...]
    literals: tuple[str, ...] = ()
    directives: tuple[FieldDirective, ...] = ()
    exclude_values: tuple[str, ...] = ()
    page_scope: PageScope = field(default_factory=PageScope)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "categories": list(self.categories),
            "literal_count": len(self.literals),
            "directives": [asdict(item) for item in self.directives],
            "excluded_value_count": len(self.exclude_values),
            "page_scope": self.page_scope.describe(),
            "warnings": list(self.warnings),
        }

    def describe(self) -> str:
        targets: list[str] = list(self.categories)
        if self.literals:
            targets.append(f"{len(self.literals)} exact phrase(s)")
        if self.directives:
            targets.append(f"{len(self.directives)} labeled field(s)")
        excluded = (
            f"; keeping {len(self.exclude_values)} explicit value(s)" if self.exclude_values else ""
        )
        return f"Redact {', '.join(targets)} on {self.page_scope.describe()}{excluded}."


@dataclass(frozen=True)
class Detection:
    """A privacy-safe description of one redacted text range."""

    page: int
    category: str
    digest: str
    character_count: int
    rectangles: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RedactionResult:
    """Result returned by both dry runs and completed redactions."""

    source: Path
    output: Path | None
    plan: InstructionPlan
    detections: tuple[Detection, ...]
    pages_processed: int
    used_ocr: bool = False
    warnings: tuple[str, ...] = ()
    verified: bool = False

    @property
    def redaction_count(self) -> int:
        return len(self.detections)

    @property
    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for detection in self.detections:
            counts[detection.category] = counts.get(detection.category, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "output": str(self.output) if self.output else None,
            "plan": self.plan.to_dict(),
            "summary": {
                "redactions": self.redaction_count,
                "categories": self.category_counts,
                "pages_processed": self.pages_processed,
                "used_ocr": self.used_ocr,
                "verified": self.verified,
            },
            "detections": [item.to_dict() for item in self.detections],
            "warnings": list(self.warnings),
        }
