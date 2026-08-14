import json
import socket
from pathlib import Path

import pymupdf
import pytest

from localredact import EncryptedPDFError, ImageOnlyPageError, PDFError, redact


def make_pdf(path: Path, pages: list[list[str]], *, metadata: bool = False) -> Path:
    document = pymupdf.open()
    for lines in pages:
        page = document.new_page()
        for index, line in enumerate(lines):
            page.insert_text((72, 72 + index * 24), line, fontsize=11)
    if metadata:
        document.set_metadata({"author": "Sensitive Author", "title": "Private Title"})
        document.embfile_add("secret.txt", b"attachment secret")
    document.save(path)
    document.close()
    return path


def pdf_text(path: Path) -> list[str]:
    with pymupdf.open(path) as document:
        return [page.get_text() for page in document]


def test_real_redaction_removes_text_and_sanitizes_extras(tmp_path: Path):
    source = make_pdf(
        tmp_path / "source.pdf",
        [
            [
                "Quarterly report - public",
                "Email: jane@example.com",
                "Phone: 312-555-0199",
                "SSN: 123-45-6789",
                "Codename: Project Falcon",
                "Keep this sentence visible.",
            ]
        ],
        metadata=True,
    )
    output = tmp_path / "safe.pdf"

    result = redact(
        source,
        "Redact email addresses, phone numbers, SSNs, and 'Project Falcon'",
        output,
    )

    output_text = "".join(pdf_text(output))
    input_text = "".join(pdf_text(source))
    assert "jane@example.com" not in output_text
    assert "312-555-0199" not in output_text
    assert "123-45-6789" not in output_text
    assert "Project Falcon" not in output_text
    assert "Quarterly report - public" in output_text
    assert "Keep this sentence visible" in output_text
    assert "jane@example.com" in input_text
    assert result.redaction_count == 4
    assert result.verified is True
    assert result.output == output.resolve()

    with pymupdf.open(output) as document:
        assert document.page_count == 1
        assert not document.metadata.get("author")
        assert document.embfile_names() == []


def test_email_before_sentence_punctuation_is_redacted(tmp_path: Path):
    source = make_pdf(
        tmp_path / "punctuated-emails.pdf",
        [["Contact VendorManagement@b1bank.com.", "Write to LegalNotice@fisglobal.com."]],
    )
    output = tmp_path / "punctuated-emails.redacted.pdf"

    result = redact(source, "Redact email addresses", output)

    text = pdf_text(output)[0]
    assert "VendorManagement@b1bank.com" not in text
    assert "LegalNotice@fisglobal.com" not in text
    assert result.redaction_count == 2


def test_page_scope_leaves_other_pages_untouched_and_verifies(tmp_path: Path):
    source = make_pdf(
        tmp_path / "pages.pdf",
        [
            ["Email shared@example.com", "Page one public"],
            ["Email shared@example.com", "Page two public"],
        ],
    )
    output = tmp_path / "scoped.pdf"

    result = redact(source, "Redact email addresses on page 1", output)
    pages = pdf_text(output)

    assert "shared@example.com" not in pages[0]
    assert "shared@example.com" in pages[1]
    assert result.redaction_count == 1
    assert result.verified is True


def test_exact_exception_is_kept_while_other_matches_are_removed(tmp_path: Path):
    source = make_pdf(
        tmp_path / "exceptions.pdf",
        [["Public support@example.com", "Private jane@example.com"]],
    )
    output = tmp_path / "exceptions.redacted.pdf"

    result = redact(
        source,
        "Redact email addresses except 'support@example.com'",
        output,
    )
    text = pdf_text(output)[0]

    assert "support@example.com" in text
    assert "jane@example.com" not in text
    assert result.redaction_count == 1


def test_labeled_field_instruction_maps_value_to_pdf_rectangles(tmp_path: Path):
    source = make_pdf(
        tmp_path / "label.pdf",
        [["Employee ID: EMP-2048", "Department: Research"]],
    )
    output = tmp_path / "label.redacted.pdf"

    result = redact(source, "Redact the field labeled 'Employee ID'", output)
    text = pdf_text(output)[0]

    assert "Employee ID" in text
    assert "EMP-2048" not in text
    assert "Department: Research" in text
    assert result.category_counts == {"labeled_field": 1}


def test_dry_run_writes_nothing_and_report_has_no_raw_values(tmp_path: Path):
    source = make_pdf(tmp_path / "dry.pdf", [["Email secret@example.com"]])
    output = tmp_path / "should-not-exist.pdf"

    result = redact(
        source,
        "Redact email addresses",
        output,
        dry_run=True,
    )
    serialized = json.dumps(result.to_dict())

    assert not output.exists()
    assert result.output is None
    assert result.verified is False
    assert "secret@example.com" not in serialized
    assert result.redaction_count == 1


def test_refuses_source_overwrite_and_existing_output(tmp_path: Path):
    source = make_pdf(tmp_path / "source.pdf", [["Email x@example.com"]])
    existing = make_pdf(tmp_path / "existing.pdf", [["Do not replace"]])

    with pytest.raises(PDFError, match="source PDF"):
        redact(source, "Redact email addresses", source)
    with pytest.raises(PDFError, match="already exists"):
        redact(source, "Redact email addresses", existing)


def test_image_only_page_fails_closed(tmp_path: Path):
    source = tmp_path / "scan.pdf"
    document = pymupdf.open()
    page = document.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pixmap.clear_with(255)
    page.insert_image(pymupdf.Rect(0, 0, 200, 200), pixmap=pixmap)
    document.save(source)
    document.close()

    with pytest.raises(ImageOnlyPageError, match="image-only"):
        redact(source, "Redact email addresses", tmp_path / "scan.redacted.pdf")


def test_rotated_text_is_redacted(tmp_path: Path):
    source = tmp_path / "rotated.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((300, 500), "Email rotated@example.com", rotate=90)
    page.insert_text((72, 72), "Visible heading")
    document.save(source)
    document.close()
    output = tmp_path / "rotated.redacted.pdf"

    result = redact(source, "Redact email addresses", output)

    assert "rotated@example.com" not in pdf_text(output)[0]
    assert result.redaction_count == 1


def test_exact_phrase_survives_pdf_text_run_splitting(tmp_path: Path):
    source = tmp_path / "split-runs.pdf"
    document = pymupdf.open()
    page = document.new_page()
    first = "Codename: Project"
    page.insert_text((72, 72), first)
    x = 72 + pymupdf.get_text_length(first) + 4
    page.insert_text((x, 72), "Falcon")
    page.insert_text((72, 110), "Public context")
    document.save(source)
    document.close()
    output = tmp_path / "split-runs.redacted.pdf"

    result = redact(source, "Redact 'Project Falcon'", output)

    text = pdf_text(output)[0]
    assert "Project" not in text
    assert "Falcon" not in text
    assert "Public context" in text
    assert result.redaction_count == 1


def test_core_redaction_never_opens_a_network_socket(tmp_path: Path, monkeypatch):
    source = make_pdf(tmp_path / "offline.pdf", [["Email offline@example.com"]])
    output = tmp_path / "offline.redacted.pdf"

    def reject_network(*args, **kwargs):
        raise AssertionError("redaction attempted to open a network socket")

    monkeypatch.setattr(socket, "socket", reject_network)
    result = redact(source, "Redact email addresses", output)

    assert result.verified is True
    assert output.exists()


def test_encrypted_pdf_uses_password_only_in_memory(tmp_path: Path):
    source = tmp_path / "encrypted.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Email encrypted@example.com")
    document.save(
        source,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="user-password",
    )
    document.close()
    output = tmp_path / "encrypted.redacted.pdf"

    with pytest.raises(EncryptedPDFError):
        redact(source, "Redact email addresses", output)
    result = redact(
        source,
        "Redact email addresses",
        output,
        password="user-password",
    )

    assert result.verified is True
    with pymupdf.open(output) as redacted:
        assert redacted.needs_pass
        assert redacted.authenticate("user-password")
        assert "encrypted@example.com" not in redacted[0].get_text()
