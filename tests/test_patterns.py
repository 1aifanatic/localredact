from localredact.patterns import find_pattern_matches


def values(text: str, *categories: str) -> list[tuple[str, str]]:
    return [(match.category, match.value) for match in find_pattern_matches(text, categories)]


def test_common_patterns_and_contextual_identifiers():
    text = (
        "Email jane@example.com; phone (312) 555-0199; SSN 123-45-6789\n"
        "Account Number: ACCT 4488 2211\nPassport: X1234567"
    )

    found = values(text, "email", "phone", "ssn", "account_number", "passport")

    assert ("email", "jane@example.com") in found
    assert ("phone", "(312) 555-0199") in found
    assert ("ssn", "123-45-6789") in found
    assert ("account_number", "ACCT 4488 2211") in found
    assert ("passport", "X1234567") in found


def test_credit_card_requires_luhn_checksum():
    text = "Valid 4111 1111 1111 1111; invalid 4111 1111 1111 1112"

    found = values(text, "credit_card")

    assert found == [("credit_card", "4111 1111 1111 1111")]


def test_ipv4_octets_are_validated():
    text = "Server 192.168.10.20 but version 999.999.999.999"

    found = values(text, "ip_address")

    assert found == [("ip_address", "192.168.10.20")]


def test_ambiguous_number_is_not_an_account_without_a_label():
    assert values("Reference 44882211", "account_number") == []
