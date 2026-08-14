# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""LocalRedact's intentionally small public API."""

from .errors import (
    EncryptedPDFError,
    ImageOnlyPageError,
    InstructionError,
    LocalRedactError,
    PDFError,
    VerificationError,
)
from .instructions import parse_instruction, supported_targets
from .models import InstructionPlan, RedactionResult
from .service import redact

__all__ = [
    "EncryptedPDFError",
    "ImageOnlyPageError",
    "InstructionError",
    "InstructionPlan",
    "LocalRedactError",
    "PDFError",
    "RedactionResult",
    "VerificationError",
    "parse_instruction",
    "redact",
    "supported_targets",
]

__version__ = "0.1.1"
