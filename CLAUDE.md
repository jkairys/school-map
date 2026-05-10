# CLAUDE.md — repo guide

A multi-service workspace built around a Brisbane real-estate / schools / transit map. Each service has its own conventions and docs — start in the relevant subdirectory.

## Services

| Path | What it is | Where to look first |
|---|---|---|
| `apps/frontend/` | React + Vite map UI (Leaflet, Mapbox tiles). Reads static JSON from `public/data/`. | `apps/frontend/README.md` |
| `services/oth-scraper/` | Python microservice that discovers, opens, and tracks listings on onthehouse.com.au across user-curated suburb lists. Producer-consumer with a Postgres queue, camoufox-based anti-bot, time-tracked snapshots. | `services/oth-scraper/CLAUDE.md` (conventions + architecture) → `services/oth-scraper/README.md` (how to run it) → `docs/scraper-service/DOMAIN_MODEL.md` (entities + invariants for conversation reference) → `docs/scraper-service/PRD.md` (design source of truth, PRD + 14 issue specs) |
| `services/property-scraper/` | Older one-shot Python scraper for Brisbane sold properties. Read-only reference now — superseded by `services/oth-scraper/`. | `services/property-scraper/README.md` |
| `services/school-scraper/` | Node + playwright-extra-stealth scraper for MySchool NAPLAN data. Closest in-repo prior art for stealth-browser scraping. | `services/school-scraper/scraper.js` |

## When making changes

- Each service has its own conventions; read the service's `CLAUDE.md` (if present) before structural work in that area.
- Branch protection requires PRs to merge into `main` — direct push is rejected. Use `gh pr create` and squash-merge.
- The repo has no CI today, so the gating is review + the live smoke tests documented per-service.
