import pytest

from localredact import InstructionError, parse_instruction
from localredact.patterns import SUPPORTED_CATEGORIES


def test_compiles_categories_literal_and_does_not_confuse_email_with_address():
    plan = parse_instruction(
        "Redact email addresses, phone numbers, SSNs, and the customer name 'Jane Doe'."
    )

    assert plan.categories == ("email", "name", "phone", "ssn")
    assert plan.literals == ("Jane Doe",)
    assert plan.page_scope.pages is None


def test_compiles_group_page_range_and_exact_exception():
    plan = parse_instruction("Hide contact information on pages 2-4 except 'support@example.com'")

    assert plan.categories == ("address", "email", "phone")
    assert plan.page_scope.pages == (2, 3, 4)
    assert plan.exclude_values == ("support@example.com",)


def test_compiles_field_and_bounded_directives_without_treating_labels_as_values():
    field = parse_instruction("Redact the field labeled 'Employee ID'")
    bounded = parse_instruction("Remove text between 'PRIVATE START' and 'PRIVATE END'")

    assert field.literals == ()
    assert field.directives[0].kind == "after"
    assert field.directives[0].label == "Employee ID"
    assert bounded.literals == ()
    assert bounded.directives[0].kind == "between"


def test_specific_alias_wins_over_nested_generic_alias():
    plan = parse_instruction("Redact dates of birth and email addresses")

    assert plan.categories == ("date_of_birth", "email")


def test_global_everything_preset_is_explicit():
    plan = parse_instruction("Redact everything in this document")

    assert set(plan.categories) == SUPPORTED_CATEGORIES


def test_unknown_target_is_rejected_in_strict_mode():
    with pytest.raises(InstructionError, match="Unrecognized"):
        parse_instruction("Redact email addresses and unicorn IDs")


def test_unknown_exception_is_rejected_instead_of_silently_ignored():
    with pytest.raises(InstructionError, match="exception"):
        parse_instruction("Redact PII except unicorn IDs")


def test_lenient_mode_retains_warning_and_known_subset():
    plan = parse_instruction(
        "Redact email addresses and unicorn IDs",
        strict=False,
    )

    assert plan.categories == ("email",)
    assert plan.warnings


def test_instruction_requires_an_action_and_a_target():
    with pytest.raises(InstructionError, match="Start the instruction"):
        parse_instruction("email addresses")
    with pytest.raises(InstructionError, match="No supported"):
        parse_instruction("Redact the document")


def test_page_zero_is_rejected():
    with pytest.raises(InstructionError, match="start at 1"):
        parse_instruction("Redact email addresses on page 0")


def test_plan_serialization_never_echoes_exact_literal_or_original_instruction():
    secret = "Project Nightingale"
    plan = parse_instruction(f"Redact '{secret}'")

    serialized = str(plan.to_dict())
    assert secret not in serialized
    assert "literal_count" in serialized
