# TODO: Tracer-Bullet Issues For Parcel Analytics Notebook

These issues adapt the `to-issues` workflow into local markdown because there is no configured issue tracker in this repo.

## Proposed Slices

1. **Title**: Bootstrap the analytics workspace
   **Type**: AFK
   **Blocked by**: None - can start immediately
   **User stories covered**: 10, 14, 15
   **What to build**: Create a notebook-oriented Python analytics workspace that fits the repo’s existing `Taskfile` conventions. The slice should let a user install dependencies, start Jupyter, and run a smoke notebook against placeholder or empty local inputs.
   **Acceptance criteria**
   - [ ] A reproducible Python environment can be installed with `uv`
   - [ ] Common install and notebook-start commands are exposed through `Taskfile`
   - [ ] A starter notebook runs end to end without requiring manual code edits
   - [ ] The workspace conventions for local data and generated outputs are documented in the notebook or nearby docs

2. **Title**: Ingest official Queensland parcel and locality data
   **Type**: AFK
   **Blocked by**: 1. Bootstrap the analytics workspace
   **User stories covered**: 2, 10, 11, 12, 13
   **What to build**: Add the end-to-end path for downloading the official source datasets into the project, loading them from local files, validating their schema enough to proceed, and constraining them to a chosen area of interest.
   **Acceptance criteria**
   - [ ] The official cadastral parcel and locality datasets can be downloaded into local project storage
   - [ ] The analysis code can load both datasets from local files without manual cleanup
   - [ ] The workflow can subset data by configured localities or spatial bounds
   - [ ] The workflow either applies a residential-only filter or clearly falls back to all in-scope parcels

3. **Title**: Deliver suburb parcel histograms for one report
   **Type**: AFK
   **Blocked by**: 2. Ingest official Queensland parcel and locality data
   **User stories covered**: 1, 5, 6, 7
   **What to build**: Produce one end-to-end report for a chosen target area that outputs suburb-level counts across the fixed parcel-size bins. This slice should be complete enough to verify the core analytical value of the project before generalizing further.
   **Acceptance criteria**
   - [ ] A configured target area can generate suburb-level parcel-size histograms
   - [ ] Histogram bins exactly match the agreed ranges
   - [ ] The output presents counts by suburb without rankings or composite scores
   - [ ] The notebook demonstrates at least one complete example report

4. **Title**: Deliver a median parcel-size hex map for one report
   **Type**: AFK
   **Blocked by**: 2. Ingest official Queensland parcel and locality data
   **User stories covered**: 8, 14
   **What to build**: Produce one static hex map for a chosen target area, using parcel centroids aggregated into hexes and colored by median parcel size. This slice validates the spatial-visual component independently of multi-report orchestration.
   **Acceptance criteria**
   - [ ] A configured target area can generate a static hex map
   - [ ] Each hex is summarized by median parcel size, not count or mean
   - [ ] The output is legible enough to distinguish larger-block and smaller-block areas
   - [ ] The map generation logic is separated from notebook presentation logic

5. **Title**: Generalize reports for multiple suburb lists or bounds
   **Type**: AFK
   **Blocked by**: 3. Deliver suburb parcel histograms for one report, 4. Deliver a median parcel-size hex map for one report
   **User stories covered**: 3, 4, 9, 16
   **What to build**: Add reusable report definitions so the same workflow can emit histogram and map outputs for Sunshine Coast, North Brisbane, South Brisbane, or any future custom region specified by suburb list or spatial bounds.
   **Acceptance criteria**
   - [ ] Report definitions can be expressed without editing core analysis logic
   - [ ] The workflow supports both suburb-list-driven and bounds-driven report selection, or clearly standardizes on one approach
   - [ ] Multiple reports can be generated in one run
   - [ ] Outputs are clearly named so different report regions are easy to compare

6. **Title**: Lock in analytical correctness with focused tests
   **Type**: AFK
   **Blocked by**: 3. Deliver suburb parcel histograms for one report, 4. Deliver a median parcel-size hex map for one report
   **User stories covered**: 17, 18
   **What to build**: Add focused automated tests around the stable analytical interfaces so future refactors do not change parcel-area, binning, suburb aggregation, or hex-median behavior by accident.
   **Acceptance criteria**
   - [ ] Tests cover parcel-area normalization and fixed-bin assignment
   - [ ] Tests cover suburb aggregation on small synthetic fixtures
   - [ ] Tests cover hex aggregation using median parcel size
   - [ ] Tests avoid coupling to notebook cell structure or implementation trivia

## Review Questions

1. Does this breakdown feel too coarse, too fine, or about right?
2. Should the hex-map slice depend on the histogram slice, or should they stay parallel after data ingestion?
3. Do you want a separate slice for fetching/downloading the government source data, or is it fine bundled into ingestion?
