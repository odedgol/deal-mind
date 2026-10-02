from datetime import date
from typing import Any

INTEGER_FIELDS = {
    "acv",
    "tcv",
    "renewal_term_months",
    "probability",
}

BOOLEAN_FIELDS = {
    "approval_required",
    "restricted_access",
}

PERMISSION_LIST_FIELDS = {
    "allowed_account_ids",
    "allowed_source_types",
}


def parse_opportunity_row(row: dict[str, str]) -> dict[str, Any]:
    return {key: parse_opportunity_field(key, value) for key, value in row.items()}


def parse_opportunity_field(key: str, value: str) -> Any:
    if key in INTEGER_FIELDS:
        return int(value)
    if key in BOOLEAN_FIELDS:
        return parse_bool(value)
    if key == "close_date":
        return date.fromisoformat(value)
    return value


def parse_permission_row(row: dict[str, str]) -> dict[str, Any]:
    return {key: parse_permission_field(key, value) for key, value in row.items()}


def parse_permission_field(key: str, value: str) -> Any:
    if key in PERMISSION_LIST_FIELDS:
        return value.split(",")
    if key.startswith("can_"):
        return parse_bool(value)
    return value


def parse_bool(value: str) -> bool:
    return value.lower() == "true"
