"""Generate and evaluate a synthetic before/after PDF redaction corpus.

All names, identifiers, addresses, and secrets in this suite are fictitious and
exist only to exercise LocalRedact. The script creates final user artifacts in
``output/pdf`` and keeps render intermediates under ``tmp/pdfs`` for visual QA.
"""

from __future__ import annotations

import json
import os
import shutil
import textwrap
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from localredact import ImageOnlyPageError, redact

REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = REPO_ROOT / "tmp" / "pdfs" / "synthetic-redaction-suite"
BEFORE_ROOT = WORK_ROOT / "before"
AFTER_ROOT = WORK_ROOT / "after"
RENDER_ROOT = WORK_ROOT / "renders"
OUTPUT_ROOT = REPO_ROOT / "output" / "pdf"

FINAL_REPORT = OUTPUT_ROOT / "localredact-synthetic-before-after-report.pdf"
FINAL_ARCHIVE = OUTPUT_ROOT / "localredact-synthetic-before-after-suite.zip"
FINAL_JSON = OUTPUT_ROOT / "localredact-synthetic-results.json"
FINAL_MARKDOWN = OUTPUT_ROOT / "localredact-synthetic-results.md"


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    tier: str
    title: str
    instruction: str
    pages: tuple[tuple[str, ...], ...]
    removed: dict[int, tuple[str, ...]]
    retained: dict[int, tuple[str, ...]]
    layout: str = "standard"
    password: str | None = None
    metadata_and_attachment: bool = False
    expected_error: str | None = None
    notes: str = ""


@dataclass
class CaseResult:
    case_id: str
    tier: str
    title: str
    instruction: str
    status: str
    passed: bool
    pages: int
    redactions: int
    category_counts: dict[str, int]
    elapsed_ms: float
    removed_assertions: int
    retained_assertions: int
    before_file: str
    after_file: str | None
    notes: str
    checks: list[str] = field(default_factory=list)
    error: str | None = None


def _values(*items: str) -> tuple[str, ...]:
    return items


def build_cases() -> list[SyntheticCase]:
    """Return 24 successful cases plus one expected fail-closed scan."""

    cases = [
        SyntheticCase(
            "E01",
            "Easy",
            "Single email address",
            "Redact email addresses",
            ((_values("Contact email: alice@example.com", "Public note: approved for release")),),
            {1: _values("alice@example.com")},
            {1: _values("Public note: approved for release")},
        ),
        SyntheticCase(
            "E02",
            "Easy",
            "US phone number",
            "Hide phone numbers",
            ((_values("Direct line: (312) 555-0187", "Office hours: 9 AM to 5 PM")),),
            {1: _values("(312) 555-0187")},
            {1: _values("Office hours: 9 AM to 5 PM")},
        ),
        SyntheticCase(
            "E03",
            "Easy",
            "Social Security number",
            "Remove SSNs",
            ((_values("SSN: 123-45-6789", "Application status: pending")),),
            {1: _values("123-45-6789")},
            {1: _values("Application status: pending")},
        ),
        SyntheticCase(
            "E04",
            "Easy",
            "Luhn-valid payment card",
            "Redact credit card numbers",
            ((_values("Payment card: 4111 1111 1111 1111", "Invoice total: USD 125.00")),),
            {1: _values("4111 1111 1111 1111")},
            {1: _values("Invoice total: USD 125.00")},
        ),
        SyntheticCase(
            "E05",
            "Easy",
            "Exact quoted person name",
            "Redact 'Jane Avery Doe'",
            ((_values("Authorized signer: Jane Avery Doe", "Role: project reviewer")),),
            {1: _values("Jane Avery Doe")},
            {1: _values("Role: project reviewer")},
        ),
        SyntheticCase(
            "E06",
            "Easy",
            "IPv4 address",
            "Obscure IP addresses",
            ((_values("Last login IP: 192.168.10.42", "Environment: quality assurance")),),
            {1: _values("192.168.10.42")},
            {1: _values("Environment: quality assurance")},
        ),
        SyntheticCase(
            "E07",
            "Easy",
            "Private URL",
            "Redact URLs",
            (
                (
                    "Private reset URL: https://reset.example.test/token/ABC123",
                    "Link expires after one use",
                ),
            ),
            {1: _values("https://reset.example.test/token/ABC123")},
            {1: _values("Link expires after one use")},
        ),
        SyntheticCase(
            "E08",
            "Easy",
            "Context-labeled date of birth",
            "Redact dates of birth",
            ((_values("Date of Birth: 04/17/1988", "Enrollment year: 2026")),),
            {1: _values("04/17/1988")},
            {1: _values("Enrollment year: 2026")},
        ),
        SyntheticCase(
            "M01",
            "Medium",
            "Contact bundle with exception",
            "Hide contact information except 'support@example.com'",
            (
                (
                    "Private email: marina@example.com",
                    "Public help desk: support@example.com",
                    "Mobile: 312-555-0116",
                    "Home Address: 742 Evergreen Road",
                    "Public department: Customer Success",
                ),
            ),
            {1: _values("marina@example.com", "312-555-0116", "742 Evergreen Road")},
            {1: _values("support@example.com", "Public department: Customer Success")},
        ),
        SyntheticCase(
            "M02",
            "Medium",
            "Financial identifiers",
            "Remove financial information",
            (
                (
                    "Payment Card: 4111 1111 1111 1111",
                    "Account Number: ACCT-998877",
                    "Routing Number: 021000021",
                    "IBAN: GB82 WEST 1234 5698 7654 32",
                    "Public invoice total: USD 940.00",
                ),
            ),
            {
                1: _values(
                    "4111 1111 1111 1111",
                    "ACCT-998877",
                    "021000021",
                    "GB82 WEST 1234 5698 7654 32",
                )
            },
            {1: _values("Public invoice total: USD 940.00")},
        ),
        SyntheticCase(
            "M03",
            "Medium",
            "Government identity documents",
            "Redact government IDs",
            (
                (
                    "SSN: 219-09-9999",
                    "Passport Number: X12345678",
                    "Driver's License Number: D123-4567",
                    "Citizenship review: complete",
                ),
            ),
            {1: _values("219-09-9999", "X12345678", "D123-4567")},
            {1: _values("Citizenship review: complete")},
        ),
        SyntheticCase(
            "M04",
            "Medium",
            "Protected health information",
            "Redact health information",
            (
                (
                    "Patient Name: Olivia Hart",
                    "Date of Birth: 09/02/1976",
                    "Medical Record Number: MRN-2026-441",
                    "Policy Number: HLTH-88320",
                    "Public clinic: Lakeside Health Center",
                ),
            ),
            {
                1: _values(
                    "Olivia Hart",
                    "09/02/1976",
                    "MRN-2026-441",
                    "HLTH-88320",
                )
            },
            {1: _values("Public clinic: Lakeside Health Center")},
        ),
        SyntheticCase(
            "M05",
            "Medium",
            "Application credentials",
            "Redact credentials",
            (
                (
                    "API Key: sk_live_QAONLY_8f77d2ab",
                    "Authorization: Bearer QAONLYTOKEN1234567890",
                    "JWT: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJxYS11c2VyIn0.c2lnbmF0dXJl",
                    "Environment: local test only",
                ),
            ),
            {
                1: _values(
                    "sk_live_QAONLY_8f77d2ab",
                    "QAONLYTOKEN1234567890",
                    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJxYS11c2VyIn0.c2lnbmF0dXJl",
                )
            },
            {1: _values("Environment: local test only")},
        ),
        SyntheticCase(
            "M06",
            "Medium",
            "Non-contiguous page scope",
            "Redact email addresses on pages 1 and 3",
            (
                _values("Email shared@example.com", "Page one decision: internal"),
                _values("Email shared@example.com", "Page two decision: publish"),
                _values("Email shared@example.com", "Page three decision: internal"),
            ),
            {1: _values("shared@example.com"), 3: _values("shared@example.com")},
            {
                1: _values("Page one decision: internal"),
                2: _values("shared@example.com", "Page two decision: publish"),
                3: _values("Page three decision: internal"),
            },
        ),
        SyntheticCase(
            "M07",
            "Medium",
            "Custom labeled field",
            "Redact the field labeled 'Employee ID'",
            ((_values("Employee ID: EMP-2048-Z", "Department: Applied Research")),),
            {1: _values("EMP-2048-Z")},
            {1: _values("Employee ID", "Department: Applied Research")},
        ),
        SyntheticCase(
            "M08",
            "Medium",
            "Bounded multi-line secret block",
            "Remove text between 'PRIVATE START' and 'PRIVATE END'",
            (
                (
                    "Release summary: approved",
                    "PRIVATE START",
                    "Acquisition target: Northstar Labs",
                    "Budget code: BUD-7744",
                    "PRIVATE END",
                    "Public owner: Strategy Office",
                ),
            ),
            {1: _values("Acquisition target: Northstar Labs", "Budget code: BUD-7744")},
            {1: _values("PRIVATE START", "PRIVATE END", "Public owner: Strategy Office")},
        ),
        SyntheticCase(
            "C01",
            "Complex",
            "Three-page mixed PII dossier",
            "Redact PII except 'support@example.com'",
            (
                (
                    "Customer Name: Jane Doe",
                    "Private email: jane.doe@example.com",
                    "Public support: support@example.com",
                    "Phone: 312-555-0144",
                    "Home Address: 1450 Market Street",
                ),
                (
                    "SSN: 321-54-9876",
                    "Payment Card: 4111 1111 1111 1111",
                    "Account Number: ACCT-550011",
                    "Public risk band: medium",
                ),
                (
                    "Patient Name: Jane Doe",
                    "Date of Birth: 11/30/1984",
                    "Medical Record Number: MRN-66420",
                    "Last login IP: 10.20.30.40",
                    "Public disposition: review complete",
                ),
            ),
            {
                1: _values(
                    "Jane Doe",
                    "jane.doe@example.com",
                    "312-555-0144",
                    "1450 Market Street",
                ),
                2: _values("321-54-9876", "4111 1111 1111 1111", "ACCT-550011"),
                3: _values("Jane Doe", "11/30/1984", "MRN-66420", "10.20.30.40"),
            },
            {
                1: _values("support@example.com"),
                2: _values("Public risk band: medium"),
                3: _values("Public disposition: review complete"),
            },
        ),
        SyntheticCase(
            "C02",
            "Complex",
            "Rotated text and split text runs",
            "Redact email addresses and 'Project Falcon'",
            (
                (
                    "ROTATED_EMAIL=rotated@example.com",
                    "SPLIT_PHRASE=Project|Falcon",
                    "Visible heading: Geometry stress test",
                ),
            ),
            {1: _values("rotated@example.com", "Project Falcon")},
            {1: _values("Visible heading: Geometry stress test")},
            layout="rotated",
        ),
        SyntheticCase(
            "C03",
            "Complex",
            "Metadata and embedded attachment sanitization",
            "Redact email addresses and SSNs",
            (
                (
                    _values(
                        "Owner email: metadata.owner@example.com",
                        "SSN: 231-45-6789",
                        "Public status: draft",
                    )
                ),
            ),
            {1: _values("metadata.owner@example.com", "231-45-6789")},
            {1: _values("Public status: draft")},
            metadata_and_attachment=True,
            notes="Also verifies metadata and embedded files are stripped.",
        ),
        SyntheticCase(
            "C04",
            "Complex",
            "Encrypted two-page PDF",
            "Redact email addresses and card numbers",
            (
                _values("Encrypted email: encrypted@example.com", "Public section: one"),
                _values("Payment Card: 4111 1111 1111 1111", "Public section: two"),
            ),
            {1: _values("encrypted@example.com"), 2: _values("4111 1111 1111 1111")},
            {1: _values("Public section: one"), 2: _values("Public section: two")},
            password="synthetic-pass",
            notes="The output must remain encrypted with the same user password.",
        ),
        SyntheticCase(
            "C05",
            "Complex",
            "Repeated values and dense overlap",
            "Redact email addresses, phone numbers, and card numbers",
            (
                tuple(
                    [f"Recipient {index:02d}: repeated@example.com" for index in range(1, 13)]
                    + [
                        "Escalation phone: 312-555-0194",
                        "Payment Card: 4111 1111 1111 1111",
                        "Public batch status: accepted",
                    ]
                ),
            ),
            {
                1: _values(
                    "repeated@example.com",
                    "312-555-0194",
                    "4111 1111 1111 1111",
                )
            },
            {1: _values("Public batch status: accepted")},
            layout="dense",
        ),
        SyntheticCase(
            "C06",
            "Complex",
            "Unicode name and international phone",
            'Redact email addresses, phone numbers, and "José Álvarez"',
            (
                (
                    "Customer Name: José Álvarez",
                    "Email: jose.alvarez@example.es",
                    "International phone: +44 20 7946 0958",
                    "Public region: Europe",
                ),
            ),
            {1: _values("José Álvarez", "jose.alvarez@example.es", "+44 20 7946 0958")},
            {1: _values("Public region: Europe")},
        ),
        SyntheticCase(
            "C07",
            "Complex",
            "Compact tabular records",
            "Redact email addresses, account numbers, and 'Ava Stone'",
            (
                (
                    "TABLE_ROW=Ava Stone|ava@example.com|Account Number: ACCT-1001",
                    "TABLE_ROW=Noah Reed|noah@example.com|Account Number: ACCT-1002",
                    "TABLE_ROW=Mia Chen|mia@example.com|Account Number: ACCT-1003",
                    "Public table version: 4.2",
                ),
            ),
            {
                1: _values(
                    "Ava Stone",
                    "ava@example.com",
                    "noah@example.com",
                    "mia@example.com",
                    "ACCT-1001",
                    "ACCT-1002",
                    "ACCT-1003",
                )
            },
            {1: _values("Noah Reed", "Mia Chen", "Public table version: 4.2")},
            layout="table",
        ),
        SyntheticCase(
            "C08",
            "Complex",
            "Ten-page batch document",
            "Redact email addresses, phone numbers, and SSNs",
            tuple(
                _values(
                    f"Batch email: user{page:02d}@example.com",
                    "Batch phone: 312-555-0168",
                    "Batch SSN: 123-45-6789",
                    f"Public batch page: {page:02d}",
                )
                for page in range(1, 11)
            ),
            {
                page: _values(
                    f"user{page:02d}@example.com",
                    "312-555-0168",
                    "123-45-6789",
                )
                for page in range(1, 11)
            },
            {page: _values(f"Public batch page: {page:02d}") for page in range(1, 11)},
            notes="Exercises repeated detection and verification across ten pages.",
        ),
        SyntheticCase(
            "X01",
            "Expected failure",
            "Image-only scanned page",
            "Redact email addresses",
            (
                (
                    _values(
                        "Raster email: scan@example.com",
                        "Raster public note: manual review required",
                    )
                ),
            ),
            {},
            {},
            layout="scanned",
            expected_error="ImageOnlyPageError",
            notes="Confirms image-only pages are never silently declared clean without local OCR.",
        ),
    ]
    assert len([case for case in cases if not case.expected_error]) == 24
    return cases


def _draw_frame(pdf: canvas.Canvas, case: SyntheticCase, page_number: int, total: int) -> None:
    width, height = LETTER
    tier_color = {
        "Easy": colors.HexColor("#167D68"),
        "Medium": colors.HexColor("#B66A12"),
        "Complex": colors.HexColor("#6B4FA1"),
        "Expected failure": colors.HexColor("#B42318"),
    }[case.tier]
    pdf.setFillColor(colors.HexColor("#102A43"))
    pdf.rect(0, height - 76, width, 76, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(42, height - 42, f"{case.case_id}  {case.title}")
    pdf.setFillColor(tier_color)
    pdf.roundRect(width - 126, height - 57, 84, 24, 6, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(width - 84, height - 49, case.tier.upper())
    pdf.setFillColor(colors.HexColor("#52606D"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(42, 28, f"Synthetic data only | {case.case_id} | Page {page_number} of {total}")
    pdf.drawRightString(width - 42, 28, f"PUBLIC CONTROL {case.case_id} PAGE {page_number}")


def _draw_standard_page(
    pdf: canvas.Canvas,
    case: SyntheticCase,
    page_number: int,
    lines: tuple[str, ...],
) -> None:
    width, height = LETTER
    _draw_frame(pdf, case, page_number, len(case.pages))
    pdf.setFillColor(colors.HexColor("#F5F7FA"))
    pdf.setStrokeColor(colors.HexColor("#BCCCDC"))
    pdf.roundRect(42, 92, width - 84, height - 196, 8, fill=1, stroke=1)
    pdf.setFillColor(colors.HexColor("#243B53"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(60, height - 108, "SYNTHETIC DOCUMENT CONTENT")
    y = height - 142
    font_size = 9 if case.layout == "dense" else 11
    leading = 22 if case.layout == "dense" else 30
    pdf.setFont("Courier", font_size)
    for line in lines:
        for wrapped in textwrap.wrap(line, width=78 if font_size == 11 else 92) or [""]:
            pdf.setFillColor(colors.HexColor("#102A43"))
            pdf.drawString(60, y, wrapped)
            y -= leading
        if y < 116:
            raise ValueError(f"Synthetic content overflow in {case.case_id}")
    pdf.setFillColor(colors.HexColor("#486581"))
    pdf.setFont("Helvetica", 9)
    pdf.drawString(60, 108, "Non-sensitive control text must remain readable after redaction.")


def _draw_rotated_page(pdf: canvas.Canvas, case: SyntheticCase) -> None:
    width, height = LETTER
    _draw_frame(pdf, case, 1, 1)
    pdf.setFillColor(colors.HexColor("#F5F7FA"))
    pdf.roundRect(42, 92, width - 84, height - 196, 8, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#102A43"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, height - 130, "Visible heading: Geometry stress test")
    pdf.saveState()
    pdf.translate(500, 190)
    pdf.rotate(90)
    pdf.setFont("Courier", 11)
    pdf.drawString(0, 0, "Rotated email: rotated@example.com")
    pdf.restoreState()
    pdf.setFont("Courier", 12)
    y = height - 225
    pdf.drawString(88, y, "Codename: Project")
    first_width = pdf.stringWidth("Codename: Project", "Courier", 12)
    pdf.setFont("Courier-Bold", 12)
    pdf.drawString(88 + first_width + 8, y, "Falcon")
    pdf.setStrokeColor(colors.HexColor("#2680C2"))
    pdf.line(72, y - 8, 400, y - 8)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 126, "Public geometry note: rotated and split runs are intentional.")


def _draw_table_page(pdf: canvas.Canvas, case: SyntheticCase) -> None:
    width, height = LETTER
    _draw_frame(pdf, case, 1, 1)
    data = [
        ["Name", "Email", "Account"],
        ["Ava Stone", "ava@example.com", "Account Number: ACCT-1001"],
        ["Noah Reed", "noah@example.com", "Account Number: ACCT-1002"],
        ["Mia Chen", "mia@example.com", "Account Number: ACCT-1003"],
    ]
    x_positions = [54, 180, 338]
    widths = [126, 158, 220]
    row_height = 42
    top = height - 150
    for row_index, row in enumerate(data):
        y = top - row_index * row_height
        fill = colors.HexColor("#D9EAF7") if row_index == 0 else colors.white
        pdf.setFillColor(fill)
        pdf.setStrokeColor(colors.HexColor("#829AB1"))
        for x, cell_width in zip(x_positions, widths, strict=True):
            pdf.rect(x, y - row_height + 8, cell_width, row_height, fill=1, stroke=1)
        pdf.setFillColor(colors.HexColor("#102A43"))
        pdf.setFont("Helvetica-Bold" if row_index == 0 else "Helvetica", 9)
        for x, value in zip(x_positions, row, strict=True):
            pdf.drawString(x + 6, y - 17, value)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(54, top - 5 * row_height, "Public table version: 4.2")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _draw_scanned_pdf(case: SyntheticCase, path: Path) -> None:
    png = WORK_ROOT / "scan-source.png"
    image = PILImage.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, 1205, 250), fill="#102A43")
    draw.text((105, 118), f"{case.case_id} IMAGE-ONLY SYNTHETIC SCAN", fill="white", font=_font(34))
    draw.text((110, 360), "Raster email: scan@example.com", fill="#102A43", font=_font(32))
    draw.text(
        (110, 430),
        "Raster public note: manual review required",
        fill="#102A43",
        font=_font(28),
    )
    draw.text((110, 1510), "PUBLIC CONTROL X01 PAGE 1", fill="#52606D", font=_font(22))
    image.save(png)
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    pdf.drawImage(str(png), 0, 0, width=LETTER[0], height=LETTER[1])
    pdf.showPage()
    pdf.save()


def generate_case_pdf(case: SyntheticCase, destination: Path) -> None:
    """Create a polished source PDF with ReportLab and optional PyMuPDF post-processing."""

    if case.layout == "scanned":
        _draw_scanned_pdf(case, destination)
        return
    base = destination.with_suffix(".base.pdf")
    pdf = canvas.Canvas(str(base), pagesize=LETTER)
    pdf.setTitle(f"Synthetic LocalRedact case {case.case_id}")
    for page_number, lines in enumerate(case.pages, 1):
        if case.layout == "rotated":
            _draw_rotated_page(pdf, case)
        elif case.layout == "table":
            _draw_table_page(pdf, case)
        else:
            _draw_standard_page(pdf, case, page_number, lines)
        pdf.showPage()
    pdf.save()

    if case.metadata_and_attachment or case.password:
        with pymupdf.open(base) as document:
            if case.metadata_and_attachment:
                document.set_metadata(
                    {
                        "author": "Synthetic Sensitive Author",
                        "title": "Synthetic Private Title",
                        "subject": "Synthetic QA only",
                    }
                )
                document.embfile_add("synthetic-secret.txt", b"synthetic attachment secret")
            save_options: dict[str, Any] = {"garbage": 4, "deflate": True}
            if case.password:
                save_options.update(
                    encryption=pymupdf.PDF_ENCRYPT_AES_256,
                    owner_pw="synthetic-owner-pass",
                    user_pw=case.password,
                )
            document.save(destination, **save_options)
        base.unlink()
    else:
        os.replace(base, destination)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _pymupdf_text(path: Path, password: str | None) -> list[str]:
    with pymupdf.open(path) as document:
        if document.needs_pass:
            assert password and document.authenticate(password)
        return [page.get_text() for page in document]


def _pypdf_text(path: Path, password: str | None) -> tuple[int, list[str]]:
    reader = PdfReader(path)
    if reader.is_encrypted:
        assert password and reader.decrypt(password)
    return len(reader.pages), [(page.extract_text() or "") for page in reader.pages]


def _assert_values(
    texts: list[str], expectations: dict[int, tuple[str, ...]], *, present: bool
) -> int:
    checks = 0
    for page_number, values in expectations.items():
        normalized_page = _normalize(texts[page_number - 1])
        for value in values:
            found = _normalize(value) in normalized_page
            assert found is present, (
                f"page {page_number}: expected {value!r} to be {'present' if present else 'absent'}"
            )
            checks += 1
    return checks


def evaluate_case(case: SyntheticCase) -> CaseResult:
    before = BEFORE_ROOT / f"{case.case_id.lower()}-{case.title.lower().replace(' ', '-')}.pdf"
    after = (
        AFTER_ROOT / f"{case.case_id.lower()}-{case.title.lower().replace(' ', '-')}-redacted.pdf"
    )
    generate_case_pdf(case, before)
    started = time.perf_counter()
    checks: list[str] = []
    try:
        result = redact(
            before,
            case.instruction,
            after,
            password=case.password,
        )
        elapsed = (time.perf_counter() - started) * 1000
        if case.expected_error:
            raise AssertionError(f"Expected {case.expected_error}, but redaction succeeded")

        before_text = _pymupdf_text(before, case.password)
        after_text = _pymupdf_text(after, case.password)
        assert len(before_text) == len(after_text) == len(case.pages)
        checks.append("PyMuPDF page count preserved")
        removed_checks = _assert_values(after_text, case.removed, present=False)
        retained_checks = _assert_values(after_text, case.retained, present=True)
        checks.extend(
            [
                f"{removed_checks} sensitive-value assertions absent",
                f"{retained_checks} public-value assertions retained",
            ]
        )
        for page_number in range(1, len(case.pages) + 1):
            assert (
                f"PUBLIC CONTROL {case.case_id} PAGE {page_number}" in after_text[page_number - 1]
            )
        checks.append("public control marker retained on every page")

        pypdf_count, pypdf_text = _pypdf_text(after, case.password)
        assert pypdf_count == len(case.pages)
        _assert_values(pypdf_text, case.removed, present=False)
        checks.append("independent pypdf extraction found no expected sensitive values")

        safe_report = json.dumps(result.to_dict(), ensure_ascii=False)
        for values in case.removed.values():
            assert all(value not in safe_report for value in values)
        checks.append("result report contains no raw expected sensitive values")
        assert result.verified
        checks.append("LocalRedact reopen verification passed")

        if case.metadata_and_attachment:
            with pymupdf.open(after) as document:
                assert not document.metadata.get("author")
                assert document.embfile_names() == []
            checks.append("metadata and embedded attachment stripped")
        if case.password:
            with pymupdf.open(after) as document:
                assert document.needs_pass
                assert document.authenticate(case.password)
            checks.append("output remains encrypted")

        return CaseResult(
            case.case_id,
            case.tier,
            case.title,
            case.instruction,
            "PASS",
            True,
            len(case.pages),
            result.redaction_count,
            result.category_counts,
            elapsed,
            removed_checks,
            retained_checks,
            str(before.relative_to(WORK_ROOT)).replace("\\", "/"),
            str(after.relative_to(WORK_ROOT)).replace("\\", "/"),
            case.notes,
            checks,
        )
    except ImageOnlyPageError as error:
        elapsed = (time.perf_counter() - started) * 1000
        if case.expected_error == "ImageOnlyPageError":
            assert not after.exists()
            return CaseResult(
                case.case_id,
                case.tier,
                case.title,
                case.instruction,
                "PASS_EXPECTED_FAILURE",
                True,
                len(case.pages),
                0,
                {},
                elapsed,
                0,
                0,
                str(before.relative_to(WORK_ROOT)).replace("\\", "/"),
                None,
                case.notes,
                ["image-only page failed closed", "no misleading output PDF was created"],
                type(error).__name__,
            )
        raise
    except Exception as error:
        elapsed = (time.perf_counter() - started) * 1000
        return CaseResult(
            case.case_id,
            case.tier,
            case.title,
            case.instruction,
            "FAIL",
            False,
            len(case.pages),
            0,
            {},
            elapsed,
            0,
            0,
            str(before.relative_to(WORK_ROOT)).replace("\\", "/"),
            str(after.relative_to(WORK_ROOT)).replace("\\", "/") if after.exists() else None,
            case.notes,
            checks,
            f"{type(error).__name__}: {error}",
        )


def _render_first_page(path: Path, destination: Path, password: str | None) -> None:
    with pymupdf.open(path) as document:
        if document.needs_pass:
            assert password and document.authenticate(password)
        pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(1.35, 1.35), alpha=False)
        pixmap.save(destination)


def _failure_panel(destination: Path) -> None:
    image = PILImage.new("RGB", (826, 1069), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (60, 100, 766, 969), radius=24, fill="#FFF1F0", outline="#B42318", width=5
    )
    draw.text((110, 210), "NO AFTER PDF", fill="#B42318", font=_font(44))
    draw.text((110, 310), "EXPECTED SAFE FAILURE", fill="#7A271A", font=_font(28))
    lines = [
        "The page is image-only.",
        "LocalRedact refused to claim",
        "a clean result without OCR.",
        "No output PDF was written.",
    ]
    for index, line in enumerate(lines):
        draw.text((110, 420 + index * 62), line, fill="#7A271A", font=_font(26))
    image.save(destination)


def render_thumbnails(
    cases: list[SyntheticCase], results: list[CaseResult]
) -> dict[str, tuple[Path, Path]]:
    thumbnails: dict[str, tuple[Path, Path]] = {}
    result_map = {result.case_id: result for result in results}
    for case in cases:
        result = result_map[case.case_id]
        before_png = RENDER_ROOT / f"{case.case_id.lower()}-before.png"
        after_png = RENDER_ROOT / f"{case.case_id.lower()}-after.png"
        _render_first_page(WORK_ROOT / result.before_file, before_png, case.password)
        if result.after_file:
            _render_first_page(WORK_ROOT / result.after_file, after_png, case.password)
        else:
            _failure_panel(after_png)
        thumbnails[case.case_id] = (before_png, after_png)
    return thumbnails


def create_contact_sheets(
    cases: list[SyntheticCase],
    thumbnails: dict[str, tuple[Path, Path]],
) -> list[Path]:
    sheets: list[Path] = []
    for tier in ("Easy", "Medium", "Complex", "Expected failure"):
        tier_cases = [case for case in cases if case.tier == tier]
        if not tier_cases:
            continue
        thumb_width, thumb_height = 270, 350
        cell_width, cell_height = 590, 410
        rows = (len(tier_cases) + 1) // 2
        sheet = PILImage.new("RGB", (cell_width * 2, 90 + cell_height * rows), "#EAF0F6")
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (30, 22), f"{tier.upper()} - BEFORE / AFTER VISUAL QA", fill="#102A43", font=_font(30)
        )
        for index, case in enumerate(tier_cases):
            row, column = divmod(index, 2)
            x = column * cell_width + 20
            y = 85 + row * cell_height
            draw.rounded_rectangle((x, y, x + 550, y + 385), radius=12, fill="white")
            draw.text(
                (x + 16, y + 12), f"{case.case_id} {case.title}", fill="#102A43", font=_font(17)
            )
            before = PILImage.open(thumbnails[case.case_id][0]).convert("RGB")
            after = PILImage.open(thumbnails[case.case_id][1]).convert("RGB")
            before.thumbnail((thumb_width, thumb_height - 35))
            after.thumbnail((thumb_width, thumb_height - 35))
            draw.text((x + 16, y + 46), "BEFORE", fill="#52606D", font=_font(14))
            draw.text((x + 294, y + 46), "AFTER", fill="#52606D", font=_font(14))
            sheet.paste(before, (x + 16, y + 70))
            sheet.paste(after, (x + 294, y + 70))
        target = RENDER_ROOT / f"contact-{tier.lower().replace(' ', '-')}.png"
        sheet.save(target)
        sheets.append(target)
    return sheets


def _report_footer(pdf: canvas.Canvas, document: SimpleDocTemplate) -> None:
    pdf.saveState()
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.HexColor("#52606D"))
    pdf.drawString(36, 22, "LocalRedact synthetic evaluation - synthetic data only")
    pdf.drawRightString(landscape(A4)[0] - 36, 22, f"Page {document.page}")
    pdf.restoreState()


def build_report(
    cases: list[SyntheticCase],
    results: list[CaseResult],
    thumbnails: dict[str, tuple[Path, Path]],
) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=30,
        textColor=colors.HexColor("#102A43"),
        alignment=TA_LEFT,
    )
    heading = ParagraphStyle(
        "CaseHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#102A43"),
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#243B53"),
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=7.5,
        leading=9,
    )
    label = ParagraphStyle(
        "PanelLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#486581"),
    )

    document = SimpleDocTemplate(
        str(FINAL_REPORT),
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=34,
        bottomMargin=34,
        title="LocalRedact Synthetic Before/After Evaluation",
        author="LocalRedact test suite",
    )
    story: list[Any] = [
        Paragraph("LocalRedact Synthetic Before/After Evaluation", title),
        Spacer(1, 9),
        Paragraph(
            "Twenty-four successful synthetic PDFs across easy, medium, and complex tiers, "
            "plus one image-only fail-closed safety case. Every successful output was checked "
            "with LocalRedact verification, PyMuPDF extraction, and independent pypdf extraction. "
            "All displayed names and identifiers are fictitious.",
            body,
        ),
        Spacer(1, 12),
    ]
    successful = [result for result in results if result.status == "PASS"]
    expected = [result for result in results if result.status == "PASS_EXPECTED_FAILURE"]
    failed = [result for result in results if not result.passed]
    total_pages = sum(result.pages for result in successful)
    total_redactions = sum(result.redactions for result in successful)
    metrics = Table(
        [
            [
                "Successful before/after cases",
                "Expected safe failures",
                "Output pages",
                "Applied redactions",
                "Unexpected failures",
            ],
            [
                str(len(successful)),
                str(len(expected)),
                str(total_pages),
                str(total_redactions),
                str(len(failed)),
            ],
        ],
        colWidths=[145, 130, 95, 105, 105],
        rowHeights=[26, 34],
    )
    metrics.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F5F7FA")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#102A43")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, 1), 15),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9FB3C8")),
            ]
        )
    )
    coverage = Table(
        [
            ["Instruction coverage", "PDF and safety coverage"],
            [
                Paragraph(
                    "Categories, groups, exact phrases, quoted exceptions, non-contiguous "
                    "page scopes, labeled fields, and bounded multi-line regions.",
                    body,
                ),
                Paragraph(
                    "Rotation, split text runs, compact tables, Unicode, encryption, metadata, "
                    "attachments, repetition, multi-page batches, and image-only fail-closed behavior.",
                    body,
                ),
            ],
        ],
        colWidths=[3.55 * inch, 3.55 * inch],
    )
    coverage.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102A43")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9FB3C8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            metrics,
            Spacer(1, 16),
            coverage,
            Spacer(1, 12),
            Paragraph(
                "The archive accompanying this report contains every original and redacted PDF, "
                "the machine-readable results, and this report. The image-only scan intentionally "
                "has no after file because OCR was not enabled.",
                body,
            ),
            PageBreak(),
            Paragraph("Case-by-case result summary", heading),
            Spacer(1, 8),
        ]
    )
    summary_rows: list[list[Any]] = [
        ["Case", "Tier", "Scenario", "Pages", "Redactions", "Result", "Time"]
    ]
    for result in results:
        summary_rows.append(
            [
                result.case_id,
                result.tier,
                Paragraph(result.title, small),
                str(result.pages),
                str(result.redactions),
                result.status,
                f"{result.elapsed_ms:.1f} ms",
            ]
        )
    summary = Table(summary_rows, colWidths=[42, 82, 250, 42, 62, 104, 70], repeatRows=1)
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102A43")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (1, -1), "CENTER"),
                ("ALIGN", (3, 1), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BCCCDC")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.extend([summary, PageBreak()])

    result_map = {result.case_id: result for result in results}
    for index, case in enumerate(cases):
        result = result_map[case.case_id]
        status_color = "#167D68" if result.passed else "#B42318"
        story.extend(
            [
                Paragraph(f"{case.case_id} - {case.title}", heading),
                Spacer(1, 4),
                Paragraph(
                    f"<b>Tier:</b> {case.tier} &nbsp;&nbsp; "
                    f"<b>Status:</b> <font color='{status_color}'>{result.status}</font> &nbsp;&nbsp; "
                    f"<b>Pages:</b> {result.pages} &nbsp;&nbsp; "
                    f"<b>Redactions:</b> {result.redactions} &nbsp;&nbsp; "
                    f"<b>Runtime:</b> {result.elapsed_ms:.1f} ms",
                    body,
                ),
                Spacer(1, 3),
                Paragraph(f"<b>Instruction:</b> {case.instruction}", body),
                Spacer(1, 7),
            ]
        )
        before_png, after_png = thumbnails[case.case_id]
        before_image = Image(str(before_png), width=3.05 * inch, height=3.95 * inch)
        after_image = Image(str(after_png), width=3.05 * inch, height=3.95 * inch)
        comparison = Table(
            [
                [Paragraph("BEFORE", label), Paragraph("AFTER", label)],
                [before_image, after_image],
            ],
            colWidths=[3.45 * inch, 3.45 * inch],
        )
        comparison.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 1), (0, 1), 0.7, colors.HexColor("#9FB3C8")),
                    ("BOX", (1, 1), (1, 1), 0.7, colors.HexColor("#9FB3C8")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend([comparison, Spacer(1, 7)])
        detail = (
            f"<b>Assertions:</b> {result.removed_assertions} expected sensitive values absent; "
            f"{result.retained_assertions} expected public values retained. "
            f"<b>Categories:</b> {', '.join(f'{key}={value}' for key, value in result.category_counts.items()) or 'none'}."
        )
        if result.notes:
            detail += f" <b>Note:</b> {result.notes}"
        story.append(Paragraph(detail, small))
        if index != len(cases) - 1:
            story.append(PageBreak())

    document.build(story, onFirstPage=_report_footer, onLaterPages=_report_footer)


def write_results(results: list[CaseResult]) -> None:
    payload = {
        "suite": "LocalRedact synthetic before/after evaluation",
        "synthetic_data_only": True,
        "successful_before_after_cases": sum(result.status == "PASS" for result in results),
        "expected_safe_failures": sum(
            result.status == "PASS_EXPECTED_FAILURE" for result in results
        ),
        "unexpected_failures": sum(not result.passed for result in results),
        "total_output_pages": sum(result.pages for result in results if result.status == "PASS"),
        "total_redactions": sum(result.redactions for result in results),
        "cases": [asdict(result) for result in results],
    }
    FINAL_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# LocalRedact synthetic before/after results",
        "",
        "All test data is fictitious. Twenty-four cases produced verified before/after PDFs; "
        "one additional image-only case verified the expected fail-closed behavior.",
        "",
        "| Case | Tier | Scenario | Pages | Redactions | Result | Time |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    lines.extend(
        f"| {result.case_id} | {result.tier} | {result.title} | {result.pages} | "
        f"{result.redactions} | {result.status} | {result.elapsed_ms:.1f} ms |"
        for result in results
    )
    lines.extend(
        [
            "",
            "## Verification performed",
            "",
            "- LocalRedact's built-in save-and-reopen verification.",
            "- PyMuPDF extraction checks for removed and retained values on exact pages.",
            "- Independent pypdf extraction checks for removed values and page counts.",
            "- Privacy check that the result JSON contains no raw expected sensitive values.",
            "- Metadata, attachment, encryption, page-scope, rotation, split-run, Unicode, "
            "table, repetition, and multi-page checks where applicable.",
            "- Visual before/after rendering, summarized in the PDF report.",
            "",
        ]
    )
    FINAL_MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def build_archive(results: list[CaseResult]) -> None:
    readme = WORK_ROOT / "README.md"
    readme.write_text(
        "# LocalRedact synthetic PDF suite\n\n"
        "All content is fictitious. `before/` contains 25 source PDFs. `after/` contains "
        "24 verified redacted PDFs. X01 intentionally has no after PDF because image-only "
        "input failed closed without OCR. See `results.json` and the included report.\n",
        encoding="utf-8",
    )
    shutil.copy2(FINAL_JSON, WORK_ROOT / "results.json")
    shutil.copy2(FINAL_MARKDOWN, WORK_ROOT / "results.md")
    shutil.copy2(FINAL_REPORT, WORK_ROOT / "before-after-report.pdf")
    with zipfile.ZipFile(FINAL_ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for folder in (BEFORE_ROOT, AFTER_ROOT):
            for path in sorted(folder.glob("*.pdf")):
                archive.write(path, path.relative_to(WORK_ROOT).as_posix())
        for name in ("README.md", "results.json", "results.md", "before-after-report.pdf"):
            archive.write(WORK_ROOT / name, name)
    assert len([result for result in results if result.status == "PASS"]) == 24


def main() -> int:
    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT)
    for directory in (BEFORE_ROOT, AFTER_ROOT, RENDER_ROOT, OUTPUT_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    for path in (FINAL_REPORT, FINAL_ARCHIVE, FINAL_JSON, FINAL_MARKDOWN):
        if path.exists():
            path.unlink()

    cases = build_cases()
    results: list[CaseResult] = []
    for case in cases:
        result = evaluate_case(case)
        results.append(result)
        print(
            f"{result.case_id} {result.status:<22} pages={result.pages:<2} "
            f"redactions={result.redactions:<3} time={result.elapsed_ms:7.1f}ms"
        )
        if result.error and not result.passed:
            print(f"  ERROR: {result.error}")

    write_results(results)
    thumbnails = render_thumbnails(cases, results)
    contact_sheets = create_contact_sheets(cases, thumbnails)
    build_report(cases, results, thumbnails)
    build_archive(results)

    unexpected = [result for result in results if not result.passed]
    print(f"Successful before/after cases: {sum(result.status == 'PASS' for result in results)}")
    print(
        "Expected safe failures: "
        f"{sum(result.status == 'PASS_EXPECTED_FAILURE' for result in results)}"
    )
    print(f"Unexpected failures: {len(unexpected)}")
    print(f"Total redactions: {sum(result.redactions for result in results)}")
    print(f"Report: {FINAL_REPORT}")
    print(f"Archive: {FINAL_ARCHIVE}")
    print("Contact sheets:")
    for sheet in contact_sheets:
        print(f"  {sheet}")
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
