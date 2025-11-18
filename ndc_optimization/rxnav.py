"""Thin wrapper around the public RxNav API for on-demand NDC lookups."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, Optional

import requests


RXNAV_URL = "https://rxnav.nlm.nih.gov/REST/ndcstatus.json"
DEFAULT_CACHE = Path.home() / ".cache" / "ndc_optimization_rxnav.json"


@dataclass
class RxNavResult:
    ndc11: str
    name: Optional[str]
    dosage_form: Optional[str]
    strength: Optional[str]


class RxNavClient:
    """Fetch drug metadata from RxNav with a small on-disk cache."""

    def __init__(self, cache_path: Path = DEFAULT_CACHE, timeout: int = 10) -> None:
        self.cache_path = cache_path
        self.timeout = timeout
        self.cache: Dict[str, Dict[str, Optional[str]]] = {}
        if cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text())
            except Exception:
                self.cache = {}

    def _persist(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2))

    def lookup(self, ndc11: str) -> Optional[RxNavResult]:
        if not ndc11:
            return None
        if ndc11 in self.cache:
            payload = self.cache[ndc11]
            return RxNavResult(ndc11=ndc11, **payload)

        params = {"ndc": ndc11}
        try:
            response = requests.get(RXNAV_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return None

        data = response.json()
        props = data.get("ndcStatus", {}).get("ndcTime", [])
        if not props:
            return None
        # Use the first (most recent) record.
        concepts = props[0].get("conceptProperties", [])
        if not concepts:
            return None
        concept = concepts[0]
        result = RxNavResult(
            ndc11=ndc11,
            name=concept.get("name"),
            dosage_form=concept.get("doseForm"),
            strength=concept.get("strength"),
        )
        self.cache[ndc11] = {
            "name": result.name,
            "dosage_form": result.dosage_form,
            "strength": result.strength,
        }
        self._persist()
        return result


__all__ = ["RxNavClient", "RxNavResult"]
