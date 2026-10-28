# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise generated privacy shapes, checksum failures, boundaries and masking."""

import pytest
from pydantic import ValidationError

from datakeel.core.pii import PiiMatch, PiiType, detect_pii, redact_pii
from tests.core.pii_samples import card, identity


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("first.last+tag@example.org", "email"),
        ("+86 13800138000", "phone"),
        ("13800138000", "phone"),
        ("+1 (415) 555-0132", "phone"),
        ("415-555-0132", "phone"),
        ("+44 7911 123456", "phone"),
        ("+33 6 12 34 56 78", "phone"),
        ("+49 1512 3456789", "phone"),
        ("+81 90 1234 5678", "phone"),
        ("+61 412 345 678", "phone"),
        ("+91 98765 43210", "phone"),
        (f"{203}.0.113.29", "ip"),
        (f"{2001}:db8::1", "ip"),
        ("::1", "ip"),
        ("sk-" + "a1B2c3D4" * 4, "secret"),
        ("sk-" + "proj-" + "a1B2c3D4" * 8, "secret"),
        ("AKIA" + "A1B2C3D4" * 2, "secret"),
        ("ghp_" + "a1B2c3D4" * 4, "secret"),
        ("github_pat_" + "a1B2c3D4" * 4, "secret"),
        ("xoxb-" + "12345678-" * 3, "secret"),
        ("AIza" + "a1B2c3D4" * 4, "secret"),
        ("eyJ" + "a1B2c3D4" * 2 + "." + "a1B2c3D4" * 2 + "." + "a1B2c3D4" * 2, "secret"),
        ("https://" + "user:pass@" + "example.org/data", "credential_url"),
        ("https://" + "user:pass@" + f"[{2001}:db8::1]/data", "credential_url"),
        ("postgresql://" + "user:pass@" + "example.org/data", "credential_url"),
        (identity(), "china_id"),
        (identity(province="62"), "china_id"),
        (card(), "bank_card"),
        (card("4", 16), "bank_card"),
        (card("51", 16), "bank_card"),
        (card("2221", 16), "bank_card"),
        (card("34", 15), "bank_card"),
        (card("6011", 16), "bank_card"),
        (card("65", 16), "bank_card"),
        (card("3528", 16), "bank_card"),
        (card("300", 14), "bank_card"),
    ],
)
def test_detection_when_supported_shape_reports_only_its_type(value: str, kind: PiiType) -> None:
    """All supported families are found with exact Unicode character offsets."""
    text = f"值 {value}。"
    matches = detect_pii(text)
    assert len(matches) == 1
    assert matches[0].type == kind
    assert text[matches[0].start : matches[0].end] == value
    assert redact_pii(text) == f"值 [{kind.upper()}]。"
    assert value not in matches[0].model_dump_json()


@pytest.mark.parametrize("prefix", ["4", "62", "81", "3528"])
@pytest.mark.parametrize("length", [16, 19])
def test_cards_when_grouped_or_hyphenated_validate_whole_number(prefix: str, length: int) -> None:
    """Separators do not bypass the checksum or split a single card finding."""
    value = card(prefix, length)
    grouped = " ".join(value[index : index + 4] for index in range(0, len(value), 4))
    assert [match.type for match in detect_pii(grouped)] == ["bank_card"]
    assert redact_pii(grouped.replace(" ", "-")) == "[BANK_CARD]"


@pytest.mark.parametrize("value", [identity(), card(), card("4", 16)])
def test_numbers_when_checksum_mutated_cannot_keep_identity_or_card_type(value: str) -> None:
    """An otherwise valid synthetic shape fails after only its check digit changes."""
    broken = (
        value[:-1] + str((int(value[-1]) + 1) % 10) if value[-1].isdigit() else value[:-1] + "0"
    )
    assert not {match.type for match in detect_pii(broken)} & {"china_id", "bank_card"}


@pytest.mark.parametrize(
    "value",
    [
        identity("20010229"),
        identity("20240230"),
        identity("17991231"),
        identity("21001231"),
        identity(province="99"),
        identity(serial="000"),
        "4" * 16,
        "1" * 18,
        "1" * 10,
        "12345678",
        "12345678901234567890",
        "2026-10-24",
        "2026/10/24",
        "10:30:00",
        "256.30.40.50",
        "::12345",
        "sk-short",
        "AKIA" + "A" * 15,
        "https://example.org/data",
        "a..b@example.org",
        "a@" + "example..org",
        "a@" + "-example.org",
        "tokenization of ordinary training data",
    ],
)
def test_detection_when_shape_is_invalid_or_unrelated_returns_no_finding(value: str) -> None:
    """Checksums, date validity, issuer shapes and token boundaries limit false positives."""
    assert not detect_pii(value)


@pytest.mark.parametrize("label", ["api_key", "access-token", "secret_access_key", "password"])
def test_labeled_secret_when_present_masks_value_but_preserves_label(label: str) -> None:
    """A labeled credential reports the secret position rather than innocent context."""
    value = "a1B2c3D4" * 4
    assert redact_pii(f'{label}="{value}"') == f'{label}="[SECRET]"'


def test_overlaps_when_credential_url_contains_email_phone_and_token_mask_as_one() -> None:
    """Enclosing credentials take precedence so partial replacements cannot leak userinfo."""
    value = "https://" + "user@example.org:" + "sk-" + "a1B2c3D4" * 4 + "@example.net/data"
    assert [match.type for match in detect_pii(value)] == ["credential_url"]
    assert redact_pii(f"Use {value}, then continue.") == "Use [CREDENTIAL_URL], then continue."


def test_redaction_when_contacts_are_adjacent_keeps_distinct_findings() -> None:
    """Adjacent Chinese phones and mixed contacts retain separate spans and type labels."""
    text = "电话13800138000,13900139000,owner@example.org。"
    assert [match.type for match in detect_pii(text)] == ["phone", "phone", "email"]
    assert redact_pii(text) == "电话[PHONE],[PHONE],[EMAIL]。"
    assert redact_pii(text, kinds=frozenset({"email"}), replacement="hidden") == (
        "电话13800138000,13900139000,hidden。"
    )


def test_finding_when_modified_or_extended_rejects_mutation_and_extra_fields() -> None:
    """Privacy evidence is a frozen boundary model and never accepts an original-value field."""
    match = PiiMatch(type="email", start=1, end=5)
    with pytest.raises(ValidationError):
        match.start = 2
    with pytest.raises(ValidationError):
        PiiMatch.model_validate({"type": "email", "start": 1, "end": 5, "value": "private"})


def test_bearer_and_private_key_when_generated_mask_complete_secret() -> None:
    """Bearer and PEM boundaries use the same type placeholder as recognizable token prefixes."""
    value = "a1B2c3D4" * 4
    assert redact_pii(f"Bearer {value}") == "Bearer [SECRET]"
    pem = "-----BEGIN " + "PRIVATE KEY-----\n" + value + "\n-----END " + "PRIVATE KEY-----"
    assert redact_pii(pem) == "[SECRET]"


@pytest.mark.parametrize("prefix", ["4", "34", "300", "62"])
def test_cards_when_invalid_and_grouped_do_not_become_partial_phone_findings(prefix: str) -> None:
    """An invalid card cannot evade validation by exposing only a phone-sized prefix."""
    length = 15 if prefix == "34" else 14 if prefix == "300" else 16
    value = card(prefix, length)
    broken = value[:-1] + str((int(value[-1]) + 1) % 10)
    grouped = " ".join(broken[index : index + 4] for index in range(0, len(broken), 4))
    assert not detect_pii(broken)
    assert not detect_pii(grouped)


def test_email_when_adjacent_to_chinese_text_retains_its_complete_span() -> None:
    """ASCII boundaries protect emails embedded directly in Chinese prose."""
    assert redact_pii("邮箱person@example.org地址") == "邮箱[EMAIL]地址"


def test_id_when_checksum_invalid_never_reports_resident_identity() -> None:
    """Removing the identity checksum check must fail this single mutation anchor."""
    value = identity()
    broken = value[:-1] + ("1" if value[-1] != "1" else "2")
    assert all(match.type != "china_id" for match in detect_pii(broken))


def test_card_when_checksum_invalid_never_reports_payment_card() -> None:
    """Removing Luhn validation must fail this single mutation anchor."""
    value = card()
    broken = value[:-1] + str((int(value[-1]) + 1) % 10)
    assert all(match.type != "bank_card" for match in detect_pii(broken))


def test_international_phone_when_digits_also_pass_luhn_keeps_phone_type() -> None:
    """An explicit dialing prefix cannot become a payment-card finding by coincidence."""
    value = "+" + card("4915", 13)
    assert [match.type for match in detect_pii(value)] == ["phone"]
    assert redact_pii(value) == "[PHONE]"
