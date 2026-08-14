# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""Public exception hierarchy for LocalRedact."""


class LocalRedactError(Exception):
    """Base class for expected LocalRedact failures."""


class InstructionError(LocalRedactError):
    """The instruction could not be interpreted safely."""


class PDFError(LocalRedactError):
    """The input PDF could not be processed safely."""


class EncryptedPDFError(PDFError):
    """The PDF is encrypted and needs a valid password."""


class ImageOnlyPageError(PDFError):
    """A selected page appears to need OCR."""


class VerificationError(PDFError):
    """Post-redaction verification found content that should be gone."""
