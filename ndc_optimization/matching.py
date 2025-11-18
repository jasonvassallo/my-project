"""Matching logic between injectable items and facility purchase orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz

from .parsing import DrugComponents, build_match_string, normalize_ndc, parse_drug_components
from .rxnav import RxNavClient


@dataclass
class FacilityRecord:
    facility: str
    ndc11: Optional[str]
    description: str
    po_date: Optional[pd.Timestamp]
    components: DrugComponents
    match_string: str


@dataclass
class ReportRow:
    drug_text: str
    ndc11: Optional[str]
    comments: Optional[str]
    drug_name: str
    strength: str
    dosage_form: Optional[str]
    facility_matches: Dict[str, str]


class DrugMatcher:
    """Match injectable records against facility PO history."""

    def __init__(
        self,
        facility_data: Dict[str, pd.DataFrame],
        *,
        description_column: str,
        ndc_column: str,
        po_date_column: Optional[str] = None,
        rxnav: Optional[RxNavClient] = None,
        fuzzy_threshold: int = 88,
    ) -> None:
        self.description_column = description_column
        self.ndc_column = ndc_column
        self.po_date_column = po_date_column
        self.rxnav = rxnav
        self.fuzzy_threshold = fuzzy_threshold
        self.facility_records = self._prepare_facility_records(facility_data)

    def _prepare_facility_records(self, facility_data: Dict[str, pd.DataFrame]) -> Dict[str, List[FacilityRecord]]:
        records: Dict[str, List[FacilityRecord]] = {}
        for facility, frame in facility_data.items():
            facility_rows: List[FacilityRecord] = []
            for _, row in frame.iterrows():
                description = str(row.get(self.description_column, ""))
                components = parse_drug_components(description)
                ndc11 = normalize_ndc(str(row.get(self.ndc_column, "")))
                if self.rxnav and ndc11 and not components.dosage_form:
                    enriched = self.rxnav.lookup(ndc11)
                    if enriched:
                        components.dosage_form = enriched.dosage_form or components.dosage_form
                        if not components.strength and enriched.strength:
                            components.strength = enriched.strength
                match_string = build_match_string(components)
                po_date = None
                if self.po_date_column and self.po_date_column in row:
                    po_date = pd.to_datetime(row[self.po_date_column], errors="coerce")
                facility_rows.append(
                    FacilityRecord(
                        facility=facility,
                        ndc11=ndc11,
                        description=description,
                        po_date=po_date,
                        components=components,
                        match_string=match_string,
                    )
                )
            records[facility] = facility_rows
        return records

    def _ndc_match(self, ndc11: Optional[str], facility_rows: Iterable[FacilityRecord]) -> List[FacilityRecord]:
        if not ndc11:
            return []
        return [row for row in facility_rows if row.ndc11 == ndc11]

    def _name_match(
        self,
        target_match_string: str,
        facility_rows: Iterable[FacilityRecord],
    ) -> List[Tuple[FacilityRecord, int]]:
        candidates: List[Tuple[FacilityRecord, int]] = []
        for row in facility_rows:
            if not row.match_string:
                continue
            score = fuzz.token_set_ratio(target_match_string, row.match_string)
            if score >= self.fuzzy_threshold:
                candidates.append((row, score))
        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates

    def _format_match(self, ndc_records: List[FacilityRecord], fuzzy_records: List[Tuple[FacilityRecord, int]]) -> str:
        if ndc_records:
            ndcs = {rec.ndc11 for rec in ndc_records if rec.ndc11}
            summary = ", ".join(sorted(ndcs))
            return f"NDC match: {summary}"
        if fuzzy_records:
            snippets = []
            for record, score in fuzzy_records[:3]:
                label = record.ndc11 or record.description
                snippets.append(f"{label} ({score}%)")
            return "Name match: " + "; ".join(snippets)
        return ""

    def build_report(
        self,
        injectable_df: pd.DataFrame,
        *,
        injectable_description_column: str,
        injectable_ndc_column: str,
        comments_column: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[ReportRow]:
        report_rows: List[ReportRow] = []
        for _, row in injectable_df.iterrows():
            description = str(row.get(injectable_description_column, ""))
            components = parse_drug_components(description)
            ndc11 = normalize_ndc(str(row.get(injectable_ndc_column, "")))
            if self.rxnav and ndc11 and not components.dosage_form:
                enriched = self.rxnav.lookup(ndc11)
                if enriched:
                    components.dosage_form = enriched.dosage_form or components.dosage_form
                    if not components.strength and enriched.strength:
                        components.strength = enriched.strength
            match_string = build_match_string(components)
            facility_matches: Dict[str, str] = {}
            for facility, records in self.facility_records.items():
                facility_rows = records
                if start_date or end_date:
                    facility_rows = [
                        record
                        for record in facility_rows
                        if record.po_date is None
                        or (
                            (not start_date or record.po_date >= start_date)
                            and (not end_date or record.po_date <= end_date)
                        )
                    ]
                ndc_records = self._ndc_match(ndc11, facility_rows)
                fuzzy_records = self._name_match(match_string, facility_rows) if not ndc_records else []
                facility_matches[facility] = self._format_match(ndc_records, fuzzy_records)
            report_rows.append(
                ReportRow(
                    drug_text=description,
                    ndc11=ndc11,
                    comments=row.get(comments_column) if comments_column else None,
                    drug_name=components.name,
                    strength=components.strength,
                    dosage_form=components.dosage_form,
                    facility_matches=facility_matches,
                )
            )
        return report_rows


__all__ = ["DrugMatcher", "ReportRow"]
