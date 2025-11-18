# NDC monthly reporting utilities

This repository now ships a Python-based workflow for building the NDC monthly report
referenced in the project brief. The tooling focuses on parsing the free-text drug
name/strength/dosage form fields that live both in the master **Injectable** sheet and
in the facility purchase-order history exports. After parsing, the script attempts to
match Injectable rows against facility purchase history by

1. **Exact NDC matches** (normalized to the 11-digit format).
2. **Fallback fuzzy matches** on normalized drug name/strength/dosage form strings.

When an NDC match does not exist, the fallback path compares the Injectable description
with the abbreviated facility description and reports the best scoring results along
with the fuzzy-match score.

The script can optionally enrich missing dosage-form or strength information using the
public RxNav API whenever an NDC is provided. Results are cached locally to avoid
repeated lookups.

## Getting started

Create (or update) the conda environment using the supplied `environment.yml` file and
activate it:

```bash
conda env update --file environment.yml --prune
conda activate my-project
```

Install the repository in editable mode if you prefer:

```bash
pip install -e .
```

## Running the monthly report script

The entry point lives at `scripts/ndc_monthly_report.py`. A typical execution pattern is
shown below. Each facility purchase-order file is supplied via `--po-file` using the
`FACILITY=path[::sheet]` syntax. Excel sheets are supported as well as CSV exports.

```bash
python scripts/ndc_monthly_report.py \
  --injectable-workbook ~/projects/ndc-optimization/monthly_facility_purchases.xlsx \
  --injectable-sheet Injectable \
  --injectable-description-column "Drug Name / Strength / Dosage Form" \
  --injectable-ndc-column NDC \
  --comments-column Comments \
  --po-file MRH=~/projects/ndc-optimization/po/MRH.xlsx::Sheet1 \
  --po-file BRH=~/projects/ndc-optimization/po/BRH.csv \
  --po-description-column "Drug Name / Strength / Dosage Form" \
  --po-ndc-column NDC \
  --po-date-column "PO Processing Date" \
  --month 2024-05 \
  --output ndc_monthly_report.xlsx \
  --output-format excel \
  --enable-rxnav
```

### Arguments of note

* `--month` (or `--start-date` / `--end-date`) limits the PO history rows that feed the
  matching step.
* `--fuzzy-threshold` controls how strict the fallback drug-name matching should be.
  Values between 82 and 90 usually balance precision/recall for abbreviated facility
  descriptions.
* `--enable-rxnav` leverages the public RxNav API to fill missing dosage-form or
  strength information when an NDC is available. Cached results land in
  `~/.cache/ndc_optimization_rxnav.json`.
* Use `--output-format csv` when downstream tooling prefers a CSV export over Excel.

The generated output includes the original free-text description, the parsed structured
columns, the normalized NDC, and one column per facility that highlights either the
matched NDCs or the fallback fuzzy matches (with similarity scores).

## Notes on extending the matcher

* Facility exports that use different column names can be accommodated by setting the
  `--po-description-column`, `--po-ndc-column`, or `--po-date-column` arguments on a
  per-run basis.
* The parsing heuristics (`ndc_optimization/parsing.py`) capture common dosage-form
  abbreviations. If additional synonyms are needed, extend the `DOSAGE_FORM_SYNONYMS`
  table.
* Fuzzy matching leverages `rapidfuzz.token_set_ratio`. If future data reveals more
  complicated abbreviation patterns, consider augmenting the scoring logic with custom
  synonym tables or phonetic matching before adjusting the numeric threshold.
