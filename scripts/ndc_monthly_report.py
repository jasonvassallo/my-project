#!/usr/bin/env python
"""Command line entry point for generating the NDC monthly report."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ndc_optimization.matching import DrugMatcher
from ndc_optimization.rxnav import RxNavClient


def _parse_po_argument(value: str) -> Tuple[str, Path, Optional[str]]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("PO file arguments must be in FACILITY=path[::sheet] format")
    facility, payload = value.split("=", 1)
    sheet = None
    path_text = payload
    if "::" in payload:
        path_text, sheet = payload.split("::", 1)
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        raise argparse.ArgumentTypeError(f"PO file '{path}' does not exist")
    return facility.strip(), path, sheet


def _load_table(path: Path, sheet: Optional[str]) -> pd.DataFrame:
    if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
        return pd.read_excel(path, sheet_name=sheet)
    return pd.read_csv(path)


def _determine_date_range(month: Optional[str], start: Optional[str], end: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    if month:
        try:
            start_dt = datetime.strptime(month + "-01", "%Y-%m-%d")
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Month must be in YYYY-MM format") from exc
        if start_dt.month == 12:
            end_dt = datetime(start_dt.year + 1, 1, 1)
        else:
            end_dt = datetime(start_dt.year, start_dt.month + 1, 1)
        return start_dt, end_dt
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    return start_dt, end_dt


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the NDC monthly report")
    parser.add_argument("--injectable-workbook", required=True, help="Path to the Excel workbook that contains the Injectable tab")
    parser.add_argument("--injectable-sheet", default="Injectable", help="Sheet name that holds the Injectable data")
    parser.add_argument("--injectable-description-column", default="Drug Name / Strength / Dosage Form", help="Column name for the free text description in the Injectable sheet")
    parser.add_argument("--injectable-ndc-column", default="NDC", help="Column that stores the NDC for Injectable items")
    parser.add_argument("--comments-column", default="Comments", help="Column that stores analyst comments")
    parser.add_argument("--po-file", action="append", type=_parse_po_argument, required=True, help="Facility purchase order file in FACILITY=path[::sheet] format. Repeat for each facility.")
    parser.add_argument("--po-description-column", default="Drug Name / Strength / Dosage Form", help="Column containing the drug description within facility PO files")
    parser.add_argument("--po-ndc-column", default="NDC", help="Column containing the NDC within facility PO files")
    parser.add_argument("--po-date-column", default="PO Processing Date", help="Date column used for filtering facility PO history")
    parser.add_argument("--month", help="Month to evaluate in YYYY-MM format")
    parser.add_argument("--start-date", help="Optional ISO formatted start date (overrides --month when provided)")
    parser.add_argument("--end-date", help="Optional ISO formatted end date (overrides --month when provided)")
    parser.add_argument("--output", default="ndc_monthly_report.xlsx", help="Where to write the resulting report")
    parser.add_argument("--output-format", choices=["excel", "csv"], default="excel", help="Output format")
    parser.add_argument("--fuzzy-threshold", type=int, default=88, help="Minimum token-set ratio for fallback name matches")
    parser.add_argument("--enable-rxnav", action="store_true", help="Use the RxNav API to enrich missing dosage forms/strengths when NDC is present")
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    injectable_path = Path(args.injectable_workbook).expanduser().resolve()
    if not injectable_path.exists():
        parser.error(f"Injectable workbook '{injectable_path}' not found")
    injectable_df = pd.read_excel(injectable_path, sheet_name=args.injectable_sheet)

    facility_frames: Dict[str, pd.DataFrame] = {}
    for facility, path, sheet in args.po_file:
        facility_frames[facility] = _load_table(path, sheet)

    rxnav = RxNavClient() if args.enable_rxnav else None

    matcher = DrugMatcher(
        facility_frames,
        description_column=args.po_description_column,
        ndc_column=args.po_ndc_column,
        po_date_column=args.po_date_column,
        rxnav=rxnav,
        fuzzy_threshold=args.fuzzy_threshold,
    )

    start_date, end_date = _determine_date_range(args.month, args.start_date, args.end_date)

    report_rows = matcher.build_report(
        injectable_df,
        injectable_description_column=args.injectable_description_column,
        injectable_ndc_column=args.injectable_ndc_column,
        comments_column=args.comments_column,
        start_date=start_date,
        end_date=end_date,
    )

    data: List[Dict[str, Optional[str]]] = []
    facilities = sorted({facility for facility, _path, _sheet in args.po_file})
    for row in report_rows:
        entry: Dict[str, Optional[str]] = {
            "Drug": row.drug_text,
            "NDC": row.ndc11,
            "Drug Name": row.drug_name,
            "Strength": row.strength,
            "Dosage Form": row.dosage_form,
        }
        if args.comments_column:
            entry[args.comments_column] = row.comments
        for facility in facilities:
            entry[facility] = row.facility_matches.get(facility, "")
        data.append(entry)

    output_df = pd.DataFrame(data)
    output_path = Path(args.output).expanduser().resolve()
    if args.output_format == "excel":
        output_df.to_excel(output_path, index=False)
    else:
        output_df.to_csv(output_path, index=False)
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
