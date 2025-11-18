"""Parsing helpers for drug name/strength/dosage form fields."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional, Sequence

DOSAGE_FORM_SYNONYMS: Dict[str, Sequence[str]] = {
    "TABLET": ("TAB", "TABLET", "TABLETS", "TABS"),
    "CAPSULE": ("CAP", "CAPS", "CAPSULE", "CAPSULES"),
    "INJECTION": (
        "INJ",
        "INJECTION",
        "INJECTABLE",
        "IV",
        "INTRAVENOUS",
        "IM",
        "SUBQ",
        "SUBCUT",
        "SQ",
        "SC",
        "VIAL",
        "AMPULE",
        "AMP",
    ),
    "SOLUTION": ("SOL", "SOLUTION", "SOLN"),
    "SUSPENSION": ("SUSP", "SUSPENSION"),
    "CREAM": ("CREAM", "CRM"),
    "OINTMENT": ("OINT", "OINTMENT"),
    "PATCH": ("PATCH", "PCH"),
    "POWDER": ("POW", "POWDER"),
    "SPRAY": ("SPRAY", "NASAL SPRAY", "NS"),
    "DROPS": ("DROP", "DROPS", "DRP"),
    "KIT": ("KIT",),
    "GEL": ("GEL",),
    "SYRUP": ("SYR", "SYRUP"),
    "SUPPOSITORY": ("SUPP", "SUPPOSITORY"),
}

STRENGTH_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)\s*(?P<unit>MG|MCG|G|GRAM|GRAMS|UNITS|IU|MEQ|ML|L|%|MGM|MCG/ML|MG/ML|MEQ/ML|MEQ/L|MCG/ACT|MG/ACT)",
    re.IGNORECASE,
)

CLEANUP_PATTERN = re.compile(r"[^A-Z0-9%/ ]+")
WHITESPACE = re.compile(r"\s+")


@dataclass
class DrugComponents:
    """Structured representation of a free-text drug description."""

    raw_text: str
    name: str
    strength: str = ""
    dosage_form: Optional[str] = None
    normalized_name: str = field(init=False)
    match_key: str = field(init=False)

    def __post_init__(self) -> None:
        base = CLEANUP_PATTERN.sub(" ", self.name.upper()).strip()
        self.normalized_name = WHITESPACE.sub(" ", base)
        segments = [self.normalized_name]
        if self.strength:
            segments.append(self.strength.upper())
        if self.dosage_form:
            segments.append(self.dosage_form.upper())
        self.match_key = " ".join(segments)

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "raw_text": self.raw_text,
            "drug_name": self.name,
            "strength": self.strength,
            "dosage_form": self.dosage_form,
        }


def normalize_ndc(value: str) -> Optional[str]:
    """Normalize an NDC value to an 11-digit string if possible."""

    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None

    digits = re.sub(r"\D", "", value)
    if len(digits) == 11:
        return digits
    if "-" in value:
        parts = value.split("-")
        if len(parts) == 3:
            sizes = list(map(len, parts))
            if sizes == [4, 4, 2]:
                return f"0{parts[0]}{parts[1]}{parts[2]}"
            if sizes == [5, 3, 2]:
                return f"{parts[0]}0{parts[1]}{parts[2]}"
            if sizes == [5, 4, 1]:
                return f"{parts[0]}{parts[1]}0{parts[2]}"
    if len(digits) == 10:
        return digits.zfill(11)
    if len(digits) == 9:
        return digits.zfill(11)
    return None


def _extract_dosage_form(tokens: List[str]) -> Optional[str]:
    for canonical, synonyms in DOSAGE_FORM_SYNONYMS.items():
        for synonym in synonyms:
            if synonym in tokens:
                while synonym in tokens:
                    tokens.remove(synonym)
                return canonical
    return None


def _extract_strength(text: str) -> str:
    matches = list(STRENGTH_PATTERN.finditer(text))
    unique: List[str] = []
    for match in matches:
        snippet = match.group(0).upper().replace(" ", "")
        if snippet not in unique:
            unique.append(snippet)
    return " / ".join(unique)


def _clean_tokens(text: str) -> List[str]:
    cleaned = CLEANUP_PATTERN.sub(" ", text.upper())
    cleaned = WHITESPACE.sub(" ", cleaned).strip()
    tokens = [token for token in cleaned.split(" ") if token]
    return tokens


def parse_drug_components(text: str) -> DrugComponents:
    """Split a drug name/strength/form blob into structured pieces."""

    if not isinstance(text, str):
        text = ""
    working = text.strip()
    tokens = _clean_tokens(working)
    dosage_form = _extract_dosage_form(tokens)
    # Strengths rely on the original (pre token) case to keep decimals.
    strength = _extract_strength(working)

    token_text = " ".join(tokens)
    if strength:
        token_text = token_text.replace(strength.replace(" / ", " "), "")
    name = token_text.strip()
    if not name:
        name = working

    return DrugComponents(
        raw_text=text,
        name=name.title(),
        strength=strength,
        dosage_form=dosage_form,
    )


def build_match_string(components: DrugComponents) -> str:
    """Return a normalized string for fuzzy matching."""

    parts: List[str] = []
    if components.normalized_name:
        parts.append(components.normalized_name)
    if components.strength:
        parts.append(components.strength.upper())
    if components.dosage_form:
        parts.append(components.dosage_form.upper())
    return " ".join(parts)


__all__ = [
    "DrugComponents",
    "parse_drug_components",
    "normalize_ndc",
    "build_match_string",
]
