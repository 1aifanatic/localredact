# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Naveen

"""File-oriented command line interface."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from . import __version__
from .errors import LocalRedactError
from .instructions import parse_instruction, supported_targets
from .service import redact


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localredact",
        description="Redact a PDF locally using a plain-English instruction.",
        epilog=(
            "Example: localredact contract.pdf "
            "\"Redact email addresses, phone numbers, and 'Project Falcon'\""
        ),
    )
    parser.add_argument("source", type=Path, help="input PDF")
    parser.add_argument("instruction", nargs="?", help="plain-English redaction instruction")
    parser.add_argument(
        "-i",
        "--instruction",
        dest="instruction_option",
        help="instruction (alternative to the positional form)",
    )
    parser.add_argument("-o", "--output", type=Path, help="output PDF (default: NAME.redacted.pdf)")
    parser.add_argument(
        "--dry-run", action="store_true", help="detect and report without creating a PDF"
    )
    parser.add_argument(
        "--explain", action="store_true", help="show the compiled plan before processing"
    )
    parser.add_argument("--report", type=Path, help="write a raw-value-free JSON report")
    parser.add_argument("--force", action="store_true", help="replace an existing output/report")
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="continue with recognized targets while reporting unknown words",
    )
    parser.add_argument(
        "--ocr", action="store_true", help="use locally installed Tesseract for every selected page"
    )
    parser.add_argument(
        "--ocr-language", default="eng", help="Tesseract language code (default: eng)"
    )
    parser.add_argument("--ocr-dpi", type=int, default=150, help="OCR resolution (default: 150)")
    parser.add_argument(
        "--allow-image-only-pages",
        action="store_true",
        help="explicitly skip image-only pages instead of failing closed",
    )
    parser.add_argument(
        "--password", action="store_true", help="prompt securely for an encrypted PDF password"
    )
    parser.add_argument(
        "--keep-pdf-extras",
        action="store_true",
        help="retain metadata, links, form state, JavaScript, and attachments",
    )
    parser.add_argument(
        "--no-verify", action="store_true", help="skip reopening and checking the produced PDF"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _write_report(path: Path, data: dict[str, object], overwrite: bool) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    try:
        with path.open(mode, encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise LocalRedactError(
            f"Report already exists: {path}. Use --force to replace it."
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.instruction and arguments.instruction_option:
        parser.error("provide the instruction either positionally or with --instruction, not both")
    instruction = arguments.instruction_option or arguments.instruction
    if not instruction:
        parser.error("a plain-English instruction is required")
    if not 72 <= arguments.ocr_dpi <= 600:
        parser.error("--ocr-dpi must be between 72 and 600")

    try:
        plan = parse_instruction(instruction, strict=not arguments.lenient)
        if arguments.explain:
            print(plan.describe())
            if plan.warnings:
                for warning in plan.warnings:
                    print(f"Warning: {warning}", file=sys.stderr)
        password = getpass.getpass("PDF password: ") if arguments.password else None
        if arguments.report and arguments.report.exists() and not arguments.force:
            raise LocalRedactError(
                f"Report already exists: {arguments.report.resolve()}. Use --force to replace it."
            )
        result = redact(
            arguments.source,
            plan,
            arguments.output,
            password=password,
            dry_run=arguments.dry_run,
            overwrite=arguments.force,
            verify=not arguments.no_verify,
            sanitize=not arguments.keep_pdf_extras,
            ocr=arguments.ocr,
            ocr_language=arguments.ocr_language,
            ocr_dpi=arguments.ocr_dpi,
            allow_image_only_pages=arguments.allow_image_only_pages,
        )
        counts = ", ".join(f"{key}={value}" for key, value in result.category_counts.items())
        print(f"Found {result.redaction_count} redaction(s) on {result.pages_processed} page(s).")
        if counts:
            print(f"Categories: {counts}")
        if result.output:
            print(f"Created: {result.output}")
            print(f"Verified: {'yes' if result.verified else 'no'}")
        else:
            print("Dry run: no output PDF was written.")
        for warning in result.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        if arguments.report:
            _write_report(arguments.report, result.to_dict(), arguments.force)
            print(f"Report: {arguments.report.expanduser().resolve()}")
        return 0
    except (LocalRedactError, OSError) as error:
        print(f"localredact: {error}", file=sys.stderr)
        return 2


def plan_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="localredact-plan",
        description="Compile a redaction instruction without reading a document.",
    )
    parser.add_argument("instruction", nargs="?", help="plain-English redaction instruction")
    parser.add_argument("--lenient", action="store_true", help="show a partial plan with warnings")
    parser.add_argument("--targets", action="store_true", help="list supported target names")
    arguments = parser.parse_args(argv)
    try:
        if arguments.targets:
            print(json.dumps(supported_targets(), indent=2))
            if not arguments.instruction:
                return 0
        if not arguments.instruction:
            parser.error("an instruction is required unless --targets is used")
        plan = parse_instruction(arguments.instruction, strict=not arguments.lenient)
        print(plan.describe())
        print(json.dumps(plan.to_dict(), indent=2))
        return 0
    except LocalRedactError as error:
        print(f"localredact-plan: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
