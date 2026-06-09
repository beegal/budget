from __future__ import annotations

import re
import unicodedata


INTERNAL_TRANSFER_GROUPS = {
    "virement interne",
    "internal transfer",
    "interne uberweisung",
    "interne overschrijving",
    "transfert",
    "transferts",
    "transfert interne",
    "transferts internes",
}
DEFAULT_INTERNAL_TRANSFER_GROUP = "Virement Interne"


def normalized_text(value: object) -> str:
    raw = str(value or "").strip()
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


def label_group(label: object) -> str:
    group, _separator, _detail = str(label or "").partition("-")
    return group.strip()


def label_detail(label: object) -> str:
    _group, separator, detail = str(label or "").partition("-")
    return detail.strip() if separator else ""


def is_internal_transfer_group(group: object) -> bool:
    return normalized_text(group) in INTERNAL_TRANSFER_GROUPS


def is_internal_transfer_label(label: object) -> bool:
    return is_internal_transfer_group(label_group(label))


def internal_transfer_target_name(label: object) -> str:
    return label_detail(label)


def internal_transfer_mirror_label(label: object, source_account_name: str) -> str:
    group = label_group(label)
    return f"{group} - {source_account_name}"


def internal_transfer_label_for_account(account_name: object) -> str:
    return f"{DEFAULT_INTERNAL_TRANSFER_GROUP} - {str(account_name or '').strip()}"
