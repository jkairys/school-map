# PRD: Queensland Parcel Analytics Notebook

## Problem Statement

I want a fast way to come up to speed on parts of South East Queensland that might suit a move, without physically driving every suburb first. In particular, I want to understand which suburbs in the Sunshine Coast area and outer Brisbane tend to contain detached-house-style blocks in my preferred size range of `500-750 m²`.

The current problem is that I do not have a reliable, area-wide view of parcel sizes by suburb. Real-estate listings are too fragmented, and casual map browsing does not make it easy to compare suburbs or spot pockets where larger blocks cluster together.

## Solution

Build a reproducible Python/Jupyter analytics workflow that uses official Queensland government spatial datasets to:

- load cadastral parcel geometry and locality boundaries from local files
- produce fixed-bin parcel-size histograms for configured suburb sets
- render static hex maps colored by median parcel size
- support reusable report definitions so I can generate reports for Sunshine Coast, North Brisbane, South Brisbane, or any future target area

The workflow should be notebook-first, with thin notebook cells calling helper modules that handle loading, filtering, aggregation, and map rendering.

## User Stories

1. As a prospective mover, I want to compare parcel-size distributions across suburbs so that I can decide which suburbs are worth visiting.
2. As a prospective mover, I want the analysis to focus on official government parcel data so that the results are broader and less biased than listing sites.
3. As a prospective mover, I want to inspect suburbs in the Sunshine Coast area so that I can evaluate coastal and hinterland-adjacent options.
4. As a prospective mover, I want to inspect suburbs in outer Brisbane so that I can compare northern and southern options.
5. As a prospective mover, I want fixed parcel-size bins of `<300`, `300-400`, `400-500`, `500-600`, `600-700`, `700-800`, and `800+` square metres so that I can quickly see how much stock exists around my preferred block size.
6. As a prospective mover, I want suburb-level counts rather than a ranking score so that I can make my own judgment from the raw numbers.
7. As a prospective mover, I want the analysis to treat `500-750 m²` as my target range so that I can identify suburbs with meaningful supply near my preference.
8. As a prospective mover, I want static map outputs colored by median parcel size so that I can visually spot clusters of larger and smaller blocks.
9. As a notebook user, I want to pass a list of suburbs or spatial bounds into reusable report functions so that I can generate new reports without rewriting logic.
10. As a notebook user, I want local source files under versioned project conventions so that the workflow is deterministic and repeatable.
11. As a notebook user, I want the agent to download the official source datasets into the project so that I do not need to source them manually.
12. As a notebook user, I want the workflow to prefer residential-only filtering when a trustworthy attribute exists so that the outputs better reflect detached-house-style land.
13. As a notebook user, I want the workflow to fall back to all parcels within chosen localities when residential filtering is unavailable so that the analysis still runs.
14. As a notebook user, I want helper modules to encapsulate the spatial logic so that the notebook stays readable and easy to iterate on.
15. As a notebook user, I want `uv` and `Taskfile` commands for install and notebook startup so that the environment is easy to reproduce.
16. As a notebook user, I want the workflow to be able to generate one report per target area so that I can compare outputs side by side.
17. As a developer, I want the critical aggregation and mapping logic covered by tests so that refactors do not silently change the results.
18. As a developer, I want small, synthetic test fixtures for parcel geometry so that spatial tests stay fast and deterministic.

## Implementation Decisions

- The workflow will be built as a Python analytics project centered on Jupyter notebooks.
- Environment and execution will be managed with `uv`, with common commands wrapped in `Taskfile` tasks.
- The initial data sources will be the official Queensland government cadastral parcel dataset and the official Queensland locality boundary dataset stored as local project files.
- The default unit of analysis will be cadastral parcels/lots rather than valuation properties.
- The first pass will use parcel geometry within configured localities as the analysis base. A residential-only filter will be applied only if the parcel source exposes a reliable, practical attribute for that purpose; otherwise all parcels in scope will be included.
- Parcel size will be derived from a trustworthy parcel-area attribute when present, otherwise from projected geometry area in square metres.
- Histograms will use fixed bins agreed in advance: `<300`, `300-400`, `400-500`, `500-600`, `600-700`, `700-800`, `800+`.
- The main suburb output will be descriptive counts by bin, not rankings or composite scores.
- The map output will use hexagonal aggregation, with each hex colored by the median parcel size of parcel centroids falling inside that hex.
- Reports will be parameterized so a report can be defined by a list of suburbs or spatial bounds.
- The notebook should stay thin. Spatial loading, filtering, aggregation, and rendering should live in deep helper modules with simple interfaces.
- Expensive spatial work should be constrained early by report area so the workflow remains practical on local hardware.
- Static outputs are sufficient for the first version. Interactive web maps are out of scope for this phase.

## Testing Decisions

- Good tests should validate externally observable behavior and stable analytical outcomes, not notebook cell internals or incidental implementation details.
- The highest-value tests are for configuration parsing, parcel-area normalization, fixed-bin assignment, suburb aggregation, and hex aggregation.
- Spatial joins and report generation should be tested with small synthetic geometries that make expected outputs obvious.
- The notebook itself should only receive smoke-level validation; most logic should be exercised through helper modules.
- Tests should assert that configured suburb filters and spatial bounds produce the intended subset of parcels.
- Tests should assert that histogram counts match expected bin membership on known fixtures.
- Tests should assert that hex outputs use median parcel size as the summary statistic.
- If the repo has no strong prior art for Python spatial testing, the project should use straightforward `pytest`-style tests around pure or near-pure helper functions and small geospatial fixtures.

## Out of Scope

- Interactive dashboards or production web applications
- Property-price analysis, zoning analysis, flood overlays, or demographic overlays
- Travel-time scoring, school scoring, or suburb ranking formulas
- Automated report narration or recommendation engines
- Full statewide precomputation for every Queensland suburb
- Perfect classification of residential parcels when the source data does not support it cleanly

## Further Notes

- As of `2026-05-07`, the current official sources identified for this work are:
  - `Cadastral data - Queensland series`, updated `2026-04-19`
  - `Locality boundaries - Queensland`, updated `2026-04-14`
- `Valuation Property Boundaries - Queensland`, updated `2026-05-07`, is a possible future alternative if parcel lots prove to be the wrong unit of analysis, but it is not the default for v1.
- The first usable output should prioritize correctness and repeatability over polish. A notebook and a set of static report artifacts are enough to validate the idea.
