# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""High-level Python API."""

from __future__ import annotations

import os

from .instructions import parse_instruction
from .models import InstructionPlan, RedactionResult
from .pdf import redact_pdf


def redact(
    source: str | os.PathLike[str],
    instruction: str | InstructionPlan,
    output: str | os.PathLike[str] | None = None,
    *,
    strict: bool = True,
    **options: object,
) -> RedactionResult:
    """Redact a PDF using an English instruction or a precompiled plan.

    Extra keyword options are passed to :func:`redact_pdf`, allowing callers to
    control OCR, verification, overwriting, and other file-level behavior.
    """

    plan = (
        instruction
        if isinstance(instruction, InstructionPlan)
        else parse_instruction(instruction, strict=strict)
    )
    return redact_pdf(source, plan, output, **options)
