"""Charge les contrats de revue optionnels qui decrivent les variantes responsive attendues."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

RESPONSIVE_CONTRACT_REQUIRED_FIELDS = (
    "family",
    "code",
    "key",
    "differenceKind",
    "contractRule",
    "presentWidths",
    "decision",
    "rationale",
    "owner",
)
RESPONSIVE_CONTRACT_MATCH_FIELDS = (
    "family",
    "code",
    "key",
    "differenceKind",
    "contractRule",
    "presentWidths",
    "missingWidths",
)
RESPONSIVE_CONTRACT_DECISIONS = {
    "intentional-asset-variant",
    "intentional-breakpoint-only",
    "intentional-carousel-or-order-variant",
    "intentional-content-variant",
}


def load_responsive_review_contract(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_responsive_review_contract(payload, path=str(path))


def normalize_responsive_review_contract(
    payload: Any,
    *,
    path: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "version": None,
            "path": path,
            "declarations": [],
            "invalidDeclarations": [
                {"index": 0, "reason": "contract payload must be a JSON object"}
            ],
        }

    invalid: list[dict[str, Any]] = []
    if payload.get("version") != 1:
        invalid.append(
            {
                "index": -1,
                "reason": "version must be 1",
                "version": payload.get("version"),
            }
        )

    raw_declarations = payload.get("responsiveContracts")
    if not isinstance(raw_declarations, list):
        return {
            "version": payload.get("version"),
            "path": path,
            "declarations": [],
            "invalidDeclarations": [
                *invalid,
                {"index": -1, "reason": "responsiveContracts must be a list"},
            ],
        }

    declarations: list[dict[str, Any]] = []
    for index, raw_declaration in enumerate(raw_declarations):
        if not isinstance(raw_declaration, dict):
            invalid.append({"index": index, "reason": "declaration must be an object"})
            continue
        missing = [
            field
            for field in RESPONSIVE_CONTRACT_REQUIRED_FIELDS
            if not _has_contract_value(raw_declaration.get(field))
        ]
        decision = str(raw_declaration.get("decision") or "")
        if missing:
            invalid.append({"index": index, "reason": "missing required fields", "fields": missing})
            continue
        if decision not in RESPONSIVE_CONTRACT_DECISIONS:
            invalid.append(
                {
                    "index": index,
                    "reason": "invalid decision",
                    "decision": decision,
                }
            )
            continue
        declaration = _normalize_declaration(raw_declaration)
        declaration["index"] = index
        declaration["id"] = str(raw_declaration.get("id") or _contract_fingerprint(declaration))
        declarations.append(declaration)

    return {
        "version": payload.get("version"),
        "path": path,
        "declarations": declarations,
        "invalidDeclarations": invalid,
    }


def find_responsive_review_contract(
    issue: dict[str, Any],
    *,
    family: str,
    contract: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not contract:
        return None
    candidate = {**issue, "family": family}
    for declaration in contract.get("declarations", []):
        if isinstance(declaration, dict) and _contract_matches(candidate, declaration):
            return declaration
    return None


def responsive_review_contract_summary(
    contract: dict[str, Any],
    *,
    matched_ids: set[str],
) -> dict[str, Any]:
    declarations = [
        declaration
        for declaration in contract.get("declarations", [])
        if isinstance(declaration, dict)
    ]
    invalid_declarations = [
        declaration
        for declaration in contract.get("invalidDeclarations", [])
        if isinstance(declaration, dict)
    ]
    unused_declarations = [
        _public_declaration(declaration)
        for declaration in declarations
        if str(declaration.get("id") or "") not in matched_ids
    ]
    return {
        "version": contract.get("version"),
        "path": contract.get("path"),
        "declarationCount": len(declarations),
        "matchedCount": len(matched_ids),
        "unusedCount": len(unused_declarations),
        "invalidCount": len(invalid_declarations),
        "byDecision": _count_declarations(declarations, "decision"),
        "byContractRule": _count_declarations(declarations, "contractRule"),
        "unusedDeclarations": unused_declarations,
        "invalidDeclarations": invalid_declarations,
    }


def _normalize_declaration(declaration: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in (
        *RESPONSIVE_CONTRACT_MATCH_FIELDS,
        "decision",
        "rationale",
        "owner",
        "nodeRole",
        "contractAction",
        "contractRisk",
    ):
        if field in declaration:
            normalized[field] = _normalize_contract_value(declaration[field])
    return normalized


def _contract_matches(candidate: dict[str, Any], declaration: dict[str, Any]) -> bool:
    return all(
        field not in declaration
        or _normalize_contract_value(candidate.get(field)) == declaration.get(field)
        for field in RESPONSIVE_CONTRACT_MATCH_FIELDS
    )


def _contract_fingerprint(declaration: dict[str, Any]) -> str:
    parts = [
        f"{field}={_fingerprint_value(declaration.get(field))}"
        for field in RESPONSIVE_CONTRACT_MATCH_FIELDS
        if field in declaration
    ]
    return "|".join(parts)


def _normalize_contract_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_contract_scalar(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_contract_scalar(item) for item in value]
    return _normalize_contract_scalar(value)


def _normalize_contract_scalar(value: Any) -> Any:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            return stripped
    return value


def _has_contract_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _fingerprint_value(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _count_declarations(declarations: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter(
        str(declaration.get(key) or "") for declaration in declarations if declaration.get(key)
    )
    return dict(sorted(counts.items()))


def _public_declaration(declaration: dict[str, Any]) -> dict[str, Any]:
    return {
        key: declaration[key]
        for key in (
            "id",
            "family",
            "code",
            "key",
            "differenceKind",
            "contractRule",
            "presentWidths",
            "missingWidths",
            "decision",
            "owner",
        )
        if key in declaration
    }
