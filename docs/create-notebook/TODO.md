# TODO: Tracer-Bullet Issues For Parcel Analytics Notebook

These issues adapt the `to-issues` workflow into local markdown because there is no configured issue tracker in this repo.

## Reconciled Status

Reconciled against branch `parcels` at `f5581aa` on `2026-05-24`.

What actually landed:

- The `services/parcel-analytics` workspace exists with `uv`, `Taskfile`, notebooks, helper modules, and tests.
- `fetch-report-data` downloads locality boundaries for a configured report, resolves all localities for an LGA-backed report, then fetches parcel data one locality at a time and caches each locality extract before merging them into one report-level GeoJSON.
- `render-report` generates histogram CSV/PNG outputs plus median-hex GeoJSON/PNG outputs for one report.
- The implementation is locality-name driven. There is no `loc_code` pipeline in the current codebase.

Still open or ambiguous:

- There is no residential-only parcel filter. The workflow currently filters to base lot parcels, not detached-house residential zoning/land-use.
- There is no command that renders multiple reports in one invocation.
- The notebook is still a thin exploratory workbook around a selected locality and surrounding context, not the primary report renderer.

## Proposed Slices

1. **Title**: Bootstrap the analytics workspace
   **Type**: AFK
   **Blocked by**: None - can start immediately
   **User stories covered**: 10, 14, 15
   **Status**: Done
   **What to build**: Create a notebook-oriented Python analytics workspace that fits the repo’s existing `Taskfile` conventions. The slice should let a user install dependencies, start Jupyter, and run a smoke notebook against placeholder or empty local inputs.
   **Acceptance criteria**
   - [x] A reproducible Python environment can be installed with `uv`
   - [x] Common install and notebook-start commands are exposed through `Taskfile`
   - [x] A starter notebook runs end to end without requiring manual code edits
   - [x] The workspace conventions for local data and generated outputs are documented in the notebook or nearby docs

2. **Title**: Ingest official Queensland parcel and locality data
   **Type**: AFK
   **Blocked by**: 1. Bootstrap the analytics workspace
   **User stories covered**: 2, 10, 11, 12, 13
   **Status**: Mostly done
   **What to build**: Add the end-to-end path for downloading the official source datasets into the project, loading them from local files, validating their schema enough to proceed, and constraining them to a chosen area of interest.
   **Acceptance criteria**
   - [x] The official cadastral parcel and locality datasets can be downloaded into local project storage
   - [x] The analysis code can load both datasets from local files without manual cleanup
   - [x] The workflow can subset data by configured localities or spatial bounds
   - [ ] The workflow either applies a residential-only filter or clearly falls back to all in-scope parcels
   **Implementation notes**
   - LGA-backed reports now resolve the matching locality names from the downloaded locality layer, then fetch parcel data one locality at a time.
   - Parcel fetches are cached per locality under a `*_parts/` directory and merged into one report-level parcel extract.
   - Current filtering is `parcel_typ = 'Lot Type Parcel'` plus a downstream `cover_typ == "Base"` filter. That is not the same thing as a residential-only filter.

3. **Title**: Deliver suburb parcel histograms for one report
   **Type**: AFK
   **Blocked by**: 2. Ingest official Queensland parcel and locality data
   **User stories covered**: 1, 5, 6, 7
   **Status**: Done
   **What to build**: Produce one end-to-end report for a chosen target area that outputs suburb-level counts across the fixed parcel-size bins. This slice should be complete enough to verify the core analytical value of the project before generalizing further.
   **Acceptance criteria**
   - [x] A configured target area can generate suburb-level parcel-size histograms
   - [x] Histogram bins exactly match the agreed ranges
   - [x] The output presents counts by suburb without rankings or composite scores
   - [x] The notebook demonstrates at least one complete example report
   **Implementation notes**
   - `render-report` now writes `histogram_counts.csv` and `histogram_counts.png` per report.
   - The notebook uses the `sunshine_coast_region` report data for interactive follow-up on a chosen locality.

4. **Title**: Deliver a median parcel-size hex map for one report
   **Type**: AFK
   **Blocked by**: 2. Ingest official Queensland parcel and locality data
   **User stories covered**: 8, 14
   **Status**: Done
   **What to build**: Produce one static hex map for a chosen target area, using parcel centroids aggregated into hexes and colored by median parcel size. This slice validates the spatial-visual component independently of multi-report orchestration.
   **Acceptance criteria**
   - [x] A configured target area can generate a static hex map
   - [x] Each hex is summarized by median parcel size, not count or mean
   - [x] The output is legible enough to distinguish larger-block and smaller-block areas
   - [x] The map generation logic is separated from notebook presentation logic

5. **Title**: Generalize reports for multiple suburb lists or bounds
   **Type**: AFK
   **Blocked by**: 3. Deliver suburb parcel histograms for one report, 4. Deliver a median parcel-size hex map for one report
   **User stories covered**: 3, 4, 9, 16
   **Status**: Partially done
   **What to build**: Add reusable report definitions so the same workflow can emit histogram and map outputs for Sunshine Coast, North Brisbane, South Brisbane, or any future custom region specified by suburb list or spatial bounds.
   **Acceptance criteria**
   - [x] Report definitions can be expressed without editing core analysis logic
   - [x] The workflow supports both suburb-list-driven and bounds-driven report selection, or clearly standardizes on one approach
   - [ ] Multiple reports can be generated in one run
   - [x] Outputs are clearly named so different report regions are easy to compare
   **Implementation notes**
   - The config already supports locality-list reports, LGA-backed reports, and bounds.
   - The current CLI renders one report per invocation.

6. **Title**: Lock in analytical correctness with focused tests
   **Type**: AFK
   **Blocked by**: 3. Deliver suburb parcel histograms for one report, 4. Deliver a median parcel-size hex map for one report
   **User stories covered**: 17, 18
   **Status**: Done
   **What to build**: Add focused automated tests around the stable analytical interfaces so future refactors do not change parcel-area, binning, suburb aggregation, or hex-median behavior by accident.
   **Acceptance criteria**
   - [x] Tests cover parcel-area normalization and fixed-bin assignment
   - [x] Tests cover suburb aggregation on small synthetic fixtures
   - [x] Tests cover hex aggregation using median parcel size
   - [x] Tests avoid coupling to notebook cell structure or implementation trivia

## Resolved Review Notes

1. The original slice size was about right; the main mismatch was that the TODO never got reconciled after the code shipped.
2. Histogram and hex work effectively stayed parallel after ingestion, even though they now share the same report-rendering path.
3. Fetching stayed bundled with ingestion, but the implementation evolved into per-locality cached downloads for larger LGA-scale reports.

## Remaining Follow-Ups

- Decide whether to implement a real residential-only filter or explicitly document that v1 uses base lot parcels as the analysis proxy.
- Add a convenience command for rendering all configured reports in one run if that is still desired.
- If `loc_code`-driven or truly statewide processing is still the goal, treat that as a new slice rather than assuming it already exists.
