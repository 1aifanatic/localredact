# LocalRedact

[![PyPI](https://img.shields.io/pypi/v/localredact.svg)](https://pypi.org/project/localredact/)
[![Python](https://img.shields.io/pypi/pyversions/localredact.svg)](https://pypi.org/project/localredact/)
[![CI](https://github.com/1aifanatic/localredact/actions/workflows/ci.yml/badge.svg)](https://github.com/1aifanatic/localredact/actions/workflows/ci.yml)

> **Alpha software:** automated redaction can miss sensitive content. Visually
> review every high-stakes output before sharing it.

LocalRedact is a small, private PDF-redaction tool for instructions such as:

```text
Redact email addresses, phone numbers, SSNs, and the customer name 'Jane Doe'.
```

It uses deterministic Python rules—not an LLM, agent, cloud API, telemetry, or
model download. Text and coordinates are read locally with PyMuPDF. Matches are
turned into PDF redaction annotations and then **applied**, removing the
underlying content instead of merely drawing a black rectangle over it.

## Install

From PyPI:

```bash
python -m pip install localredact
```

To run the optional loopback HTTP service:

```bash
python -m pip install "localredact[server]"
```

The base install has one runtime dependency: PyMuPDF. The project is packaged
as both a wheel and a source distribution.

## Use it

The shortest complete command is:

```bash
localredact input.pdf "Redact email addresses, phone numbers, and SSNs"
```

This creates `input.redacted.pdf`, strips common PDF extras such as metadata,
embedded files, JavaScript, links, and saved form state, reopens the result, and
checks that detected values are no longer extractable.

More examples:

```bash
# Exact text plus detected categories
localredact contract.pdf \
  "Redact account numbers and the customer name 'Jane Doe'" \
  --output safe-contract.pdf

# Page scope and an explicit exception
localredact report.pdf \
  "Hide contact information on pages 2-4 except 'support@example.com'"

# A custom labeled field without defining a regex
localredact form.pdf \
  "Redact the field labeled 'Employee ID'"

# Review counts without writing a PDF
localredact form.pdf "Remove financial information" --dry-run --explain

# Write a report that contains no matched values
localredact form.pdf "Remove PII" --report form.redaction-report.json
```

Existing output files are not replaced unless `--force` is supplied. The input
PDF itself is never an allowed output target.

### Preview instruction interpretation

The parser can be used without opening a document:

```bash
localredact-plan "Redact email addresses and card numbers on pages 1 and 3"
```

LocalRedact rejects unknown target words by default instead of silently guessing.
`--lenient` is available only when a caller intentionally wants the recognized
subset and is prepared to review the warning.

## English it understands

The language is intentionally constrained and auditable:

- Actions: `redact`, `hide`, `remove`, `mask`, `black out`, `obscure`, `erase`.
- Common fields: emails, phones, SSNs, card numbers (Luhn-checked), IPs, URLs,
  dates of birth, street addresses, labeled names, account/routing numbers,
  passports, driver's licenses, medical records, tax IDs, insurance IDs, IBANs,
  API keys, bearer tokens, and JWTs.
- Groups: `PII`, `contact information`, `financial information`, `government
  IDs`, `health information`, and `credentials`.
- Exact values: quote them, for example `redact 'Project Falcon'`.
- Exceptions: `except`, `excluding`, `but not`, or `but keep`, followed by a
  known category or quoted exact value.
- Pages: `page 2`, `pages 2-5`, `pages 1 and 3`, `first page`, or `last page`.
- Layout cues: `the field labeled 'Member ID'`, `everything after 'Secret:'`,
  or `text between 'PRIVATE START' and 'PRIVATE END'`.

Names and ambiguous identifiers are detected only in strong labeled contexts.
For an unlabeled person's name, quote the exact value. That narrower behavior is
deliberate: a tiny generic-name heuristic is more likely to redact headings and
company names than to provide trustworthy coverage.

## Python API

```python
from localredact import parse_instruction, redact

plan = parse_instruction(
    "Redact email addresses, SSNs, and 'Jane Doe' except 'support@example.com'"
)
print(plan.describe())

result = redact("input.pdf", plan, "output.pdf")
print(result.redaction_count, result.category_counts, result.verified)
```

Use `dry_run=True`, `ocr=True`, `overwrite=True`, or `sanitize=False` only when
the corresponding tradeoff is intentional. Results and JSON reports carry an
ephemeral keyed digest, type, page, character count, and rectangle count; raw
matched text is never returned.

## Optional local HTTP service

```bash
python -m pip install "localredact[server]"
localredact-server
```

The service binds to `127.0.0.1:8765`, disables access logs, returns `no-store`
responses, and refuses a non-loopback bind unless `--allow-network` is explicit.
It never makes an outbound request.

```bash
curl -o redacted.pdf \
  -F "document=@input.pdf" \
  -F "instruction=Redact email addresses and SSNs" \
  http://127.0.0.1:8765/v1/redact
```

Do not expose this small local service to an untrusted network without adding
authentication, TLS, request isolation, rate limits, and normal production
hardening.

## Scanned PDFs and OCR

Born-digital PDFs work with the base pip install. Image-only pages fail closed
instead of being reported as clean. For scanned documents, install Tesseract and
its language data locally, make it discoverable to PyMuPDF, and run:

```bash
localredact scan.pdf "Redact PII" --ocr --ocr-language eng
```

OCR is local but much slower. There is no automatic cloud fallback. If an
image-only page is known to be safe or will be reviewed manually,
`--allow-image-only-pages` makes that exception explicit in the report.

## Safety model and limits

LocalRedact provides best-effort automated detection, not a compliance
certification. Important behavior:

- Real PDF content removal uses `add_redact_annot()` plus
  `apply_redactions(images=2)`, so intersecting text is removed and intersecting
  image pixels are blanked.
- Output is written to a temporary sibling, verified, and atomically moved into
  place. A failed verification leaves no claimed-safe output.
- No raw match values, original text, reversible maps, or learning files are
  persisted by the package.
- Sanitization removes common hidden payloads by default. `--keep-pdf-extras`
  opts out when interactive features matter more than that safety margin.
- Detection can still miss unusual formatting, handwriting, weak OCR, text
  stored as vector outlines, novel identifiers, or semantically sensitive prose.
  Visually review high-stakes output.
- Removing text can also remove overlapping vector art or pixels. This is a
  safety-biased consequence of irreversible redaction.

## Why this differs from OpenRedaction

The referenced OpenRedaction project has a strong local, regex-first TypeScript
detector with validators and a wide ecosystem. Its document flow extracts PDF
text and returns substituted text; it does not produce an applied, redacted PDF,
and its public interfaces use options rather than English instructions.

LocalRedact borrows the useful architectural ideas—not source code—while keeping
only a Python library, two small CLIs, an optional loopback API, a controlled
English compiler, and coordinate-aware PDF removal. The pinned upstream analysis
and source citations are in
[docs/upstream-research.md](https://github.com/1aifanatic/localredact/blob/main/docs/upstream-research.md).

## Test and build

Clone the source repository, then install the development dependencies:

```bash
python -m pip install -e ".[dev]"
```

```bash
pytest
ruff check .
python -m build
python -m pip install --force-reinstall dist/localredact-0.1.1-py3-none-any.whl
```

The end-to-end tests generate PDFs locally and assert that sensitive content is
absent from text extraction after redaction while surrounding content and page
count remain intact.

### Reproduce the 25-case synthetic evaluation

Install the development dependencies and run the suite:

```bash
python -m pip install -e ".[dev]"
python tools/run_synthetic_pdf_suite.py
```

The suite creates 24 verified before/after scenarios across easy, medium, and
complex tiers, plus one image-only case that must fail closed without OCR. It
checks output with both PyMuPDF and pypdf, produces a visual comparison report,
and packages every source and redacted PDF into a ZIP under `output/pdf/`.

## License and responsible use

LocalRedact is licensed under the
[GNU Affero General Public License v3.0 only](https://github.com/1aifanatic/localredact/blob/main/LICENSE).
Its mandatory PyMuPDF dependency is separately offered under the AGPL and
commercial licensing. If
your distribution or hosted-service use cannot satisfy the applicable AGPL
obligations, obtain appropriate commercial licensing from Artifex or use a
different backend. See
[third-party licensing](https://github.com/1aifanatic/localredact/blob/main/THIRD_PARTY_LICENSES.md).

This is not legal advice. Security problems should be reported privately using
the process in
[SECURITY.md](https://github.com/1aifanatic/localredact/blob/main/SECURITY.md),
not in a public issue.
