# Changelog

All notable changes to LocalRedact are recorded here.

## [0.1.0] - 2026-08-14

### Added

- Deterministic plain-English instruction compilation for common PII categories,
  exact text, exceptions, page scopes, and layout cues.
- Coordinate-aware PDF redaction that applies annotations, sanitizes common hidden
  payloads, saves atomically, and verifies the result.
- Python API, command-line tools, and an optional loopback-only HTTP service.
- Local OCR integration for scanned PDFs when Tesseract is installed.
- Unit, integration, and synthetic-PDF regression coverage.

[0.1.0]: https://github.com/1aifanatic/localredact/releases/tag/v0.1.0
