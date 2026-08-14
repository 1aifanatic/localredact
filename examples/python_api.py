"""Minimal LocalRedact library example."""

from localredact import redact

result = redact(
    "input.pdf",
    "Redact email addresses, phone numbers, and 'Project Falcon'",
    "input.redacted.pdf",
)

print(f"Removed {result.redaction_count} value(s): {result.category_counts}")
print(f"Verified output: {result.output}")
