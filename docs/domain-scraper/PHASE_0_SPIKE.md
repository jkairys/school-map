# Domain scraper — Phase 0 spike

## Outcome

**SUCCESS.** Camoufox baseline (`headless=True, humanize=True`) on this developer machine, no proxy, returned HTTP 200 + 1.24 MB body + `__NEXT_DATA__` present on the very first attempt against `https://www.domain.com.au/sale/paddington-qld-4064/`. A detail page (`/31-alma-street-paddington-qld-4064-2020841855`) fetched immediately after on the same warm context also returned 200 + 545 KB + `__NEXT_DATA__`. Akamai Bot Manager did set its full cookie stack (`_abck`, `bm_sz`, `bm_so`, `bm_lso` on the search; `ak_bmsc`, `bm_mi` added on the detail) but did not challenge or block.

No fallback URLs needed. Configs 2–5 were not run because the matrix halts on first success.

## What worked

- The simplest possible camoufox config (`AsyncCamoufox(headless=True, humanize=True)`) — identical to OTH's bootstrap shape. No `os=`, no `locale=`, no `geoip=`, no warm-up nav, no proxy.
- Path-based search URL `https://www.domain.com.au/sale/paddington-qld-4064/` resolved to a fully-rendered Next.js page.
- The same browser context, reused for the detail page, kept Akamai happy — the detail nav was a clean 200 with the same fingerprint and richer cookie set.
- All capture probes worked: `__NEXT_DATA__` extraction, `[data-testid*="listing"]` DOM check (true on both pages), screenshot, navigator dump, cookie enumeration.

## What didn't

- Nothing. Spike halted on first config.

## Results table

| # | Config | Status | Body size | `__NEXT_DATA__` | Verdict |
|---|---|---|---|---|---|
| 01 | `headless=True, humanize=True` | 200 | 1,243,559 | yes | **success** — listing DOM also present, title is the real SEO title, 11 cookies including 4 Akamai signals |
| 01_detail | same config, warm context, detail page nav | 200 | 545,175 | yes | success — full listing payload, 13 cookies, adds `ak_bmsc` + `bm_mi` |
| 02–05 | (not run, halted on success) | — | — | — | — |

The two captured runs at a glance:

```
config 01_baseline search:
  url: https://www.domain.com.au/sale/paddington-qld-4064/
  title: '374 Real Estate Properties for Sale in Paddington, QLD, 4064 | Domain'
  akamai cookies: bm_so, bm_lso, bm_sz, _abck
  listing DOM testid present: true
  sentinels: none

config 01_baseline detail (same warm context):
  url: https://www.domain.com.au/31-alma-street-paddington-qld-4064-2020841855
  title: '31 Alma Street, Paddington QLD 4064 | Domain'
  akamai cookies: bm_so, bm_lso, _abck, ak_bmsc, bm_mi, bm_sz
  listing DOM testid present: true
  sentinels: none
```

## Data shape findings

### Where the listings live in `__NEXT_DATA__`

**Search page:**

- `__NEXT_DATA__.props.pageProps.componentProps.listingsMap` — a dict keyed by stringified listing ID. 20 entries per page.
- `__NEXT_DATA__.props.pageProps.componentProps.listingSearchResultIds` — the same 20 IDs as a list, preserving result order.
- `__NEXT_DATA__.props.pageProps.componentProps.currentPage` / `totalPages` / `totalListings` — pagination metadata. For Paddington-sale: page 1 / 19 / 374.
- `__NEXT_DATA__.props.pageProps.componentProps.topspotFeaturedPropertyIds` — sponsored slots, separate from the organic 20.

The stable listing ID is the dict key — also `listingsMap[id].id` (int) and the trailing `-2020568511` segment of `listingsMap[id].listingModel.url`. We should use the int ID as the canonical key. URL pattern is `/<dashed-street-suburb-state-postcode>-<id>` — Domain folds the postcode and ID into the slug.

### Search-result listing record shape

`listingsMap[<id>].listingModel` has these top-level keys (from one organic Paddington result):

| Key | Type | Example / notes |
|---|---|---|
| `promoType` | str | `"premiumplus"` / `"premium"` / `"standard"` / `"platinum"` — Domain's promo tier |
| `url` | str | `/9-belmont-crescent-paddington-qld-4064-2020568511` |
| `images` | list[str] | CDN URLs, 660×440, ~30 per listing |
| `retinaImages` | None or list | usually null on non-platinum |
| `skeletonImages` | list[dict] | `{images, mediaType}` |
| `brandingAppearance` | str | `"light"` / `"dark"` |
| `price` | str | **Free-form display string** — `"For Sale"`, `"Auction"`, `"Contact Agent"`, `"Price Guide $12M $12.5M"`, `"Offers over $3,300,000"`, `"THE DEAL: Expressions of Interest"`. No numeric price field on the search payload. |
| `hasVideo` | bool | |
| `branding` | dict | `{agencyId, agents, agentNames, brandLogo, retinaBrandLogos, skeletonBrandLogo, brandName, brandColor, agentPhoto, agentRetinaPhotos, agentName}` — agency + first agent in one bundle |
| `address` | dict | `{street, suburb, state, postcode, lat, lng}` — **lat/lng present on the search payload, unlike OTH** |
| `features` | dict | `{beds, baths, parking, propertyType, propertyTypeFormatted, isRural, landSize, landUnit, isRetirement}` |
| `inspection` | dict | `{openTime, closeTime}` ISO timestamps; null if none scheduled |
| `auction` | dict or None | auction details |
| `tags` | dict | `{tagText, tagClassName}` — e.g. `{tagText: "Under offer", tagClassName: "is-under-offer"}`, `{tagText: "New", tagClassName: "is-new"}`. **This is the only status-ish field on search results.** |
| `displaySearchPriceRange` | None or dict | only set when Domain's "price guide" experiment is on |
| `enableSingleLineAddress` | bool | rendering hint |

### Comparison vs OTH `listing_snapshot` material fields

OTH's `MATERIAL_FIELDS` (from `services/oth-scraper/src/oth_scraper/snapshot_diff.py`): `price, title, blurb, bedrooms, bathrooms, parking, land_size_sqm, property_type, status`.

| OTH field | Domain search-result source | Coverage |
|---|---|---|
| `price` | `listingModel.price` (string) | **GAP** — Domain returns a display string, not a number. A normaliser will need to parse `"For Sale"`, `"Contact Agent"`, `"Auction"`, `"Offers over $X"`, `"Price Guide $X $Y"` etc. Many listings have no numeric price at all (auction, EOI). |
| `title` | not on search; `headline` on detail; `address` (single line) is the de facto title | **PARTIAL** — search payload has no editorial title; use single-line address (`9 Belmont Crescent, Paddington QLD 4064`) as a substitute, or fetch the detail-page `headline` |
| `blurb` | not on search | **GAP** — only on detail (`componentProps.description`) |
| `bedrooms` | `listingModel.features.beds` | match |
| `bathrooms` | `listingModel.features.baths` | match |
| `parking` | `listingModel.features.parking` | match |
| `land_size_sqm` | `listingModel.features.landSize` + `landUnit` | match (units already `m²`; need to handle `ha` conversion for acreage) |
| `property_type` | `listingModel.features.propertyType` (`House`, `Townhouse`, `VacantLand`, …) | match |
| `status` | `listingModel.tags.tagText` (`New`, `Updated`, `Under offer`, None) — and the `/sale/` vs `/sold/` URL prefix | **PARTIAL** — Domain encodes status partly in the URL section, partly in the `tags` block. Not as clean as OTH's explicit `status`. |

**Extras Domain gives us that OTH doesn't:**

- `address.lat` / `address.lng` directly on search results — no separate geocode pass needed.
- Agent + agency in one bundle on the search result (`branding`).
- Inspection times on search.
- Image carousel on search (we won't need detail-page hits just for photos).
- 30 listings per page worth of features on search — actually it's 20. OTH is also 20.

**Detail page (`componentProps`) adds the richer fields:**

- `description` — the long-form blurb (array of paragraph strings)
- `headline` / `tagline` — editorial title
- `structuredFeatures` — list of `{name, category, source}` like `{Air conditioning, Indoor, advertiser}`
- `priceGuide.estimatedPrice` — Domain's algorithmic estimate (often `{from: null, to: null}` until enough data)
- `domainSays` — Domain's per-listing analytics block: `firstListedDate`, `lastSoldOnDate`, `medianRentPrice`, `medianSoldPrice`, `numberSold`, `forSalePropertiesUrl`, `soldPropertiesUrl`, `updatedDate`
- `inspection.inspectionTimes` (list, not just next)
- `inspection.auctionTime` / `auctionLocation`
- `schoolCatchment.schools` — already-paired catchment data; **this is interesting for the main app** since the whole product is a school-overlay map
- `map.{latitude, longitude, displayCentreLatitude, displayCentreLongitude}` — two coordinate pairs: actual and "display centre" (Domain hides exact location for some auction listings until late)
- `stampDutyEstimate`, `whatIsNearby`, `neighbourhoodInsights`, `suburbInsights`
- `createdOn`, `modifiedOn` — timestamps. The detail page captures these explicitly.
- `agents` — full agent record list (more than the search `branding` summary)
- `features` (list of free-text strings) + `structuredFeatures` (categorised)

### Listing ID location (canonical)

Three sources, all in agreement:

1. **Search:** key of `componentProps.listingsMap` (string), also `.listingModel.id` (int).
2. **Search:** trailing numeric segment of `listingModel.url` (e.g. `…-2020568511`).
3. **Detail:** `componentProps.listingId` (int), also `propertyId` (int — same value), and the URL tail.

The integer form is canonical. URLs include the slug for SEO but the slug can change while the ID stays stable.

### Pagination

`?page=N` query param (per the brief and confirmed by `currentPage`/`totalPages` in the payload). 20 organic listings per page + a small number of `topspotFeaturedPropertyIds`. Paddington-sale today: 374 total / 19 pages.

## Anti-bot observations

Domain runs Akamai Bot Manager. Cookies observed on the warm session:

| Cookie | Set after | Notes |
|---|---|---|
| `bm_so` | search nav | Akamai BM session bootstrap |
| `bm_lso` | search nav | Akamai BM long session |
| `bm_sz` | search nav | Akamai BM session/sensor data |
| `_abck` | search nav | The classic Akamai "is-this-a-bot" verdict cookie |
| `ak_bmsc` | detail nav | Akamai BM main cookie; **only appeared after second nav** |
| `bm_mi` | detail nav | Akamai BM mitigation / interaction signal |

**Camoufox got through Akamai without any tuning.** Baseline + humanize was sufficient. This matches the prior expectation that Domain's defence is meaningfully softer than REA's Kasada — Kasada hard-blocked even with referrer chains, headed mode, and geoip-derived locale (`docs/rea-scraper/PHASE_0_SPIKE.md`), whereas Domain accepted the most basic config on first request.

Other notes worth carrying into engineering:

- The camoufox baseline presents `platform: "Win32"` and `UA: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0` despite running on macOS — that's camoufox's default spoof. Akamai accepted it. We do not appear to need `os="macos"` pinning for Domain.
- Timezone resolved to `Australia/Brisbane` (correct — this is the real machine's TZ, not spoofed). If we run the worker from a non-AU host in production we may need to think about this; for now it's free.
- `languages: ["en-US", "en"]` — not `en-AU`. Akamai didn't care.
- `_abck` appeared on first nav with no challenge, suggesting Akamai's "is human" verdict was issued immediately and held through the detail page. The risk surface is the future: Akamai will sometimes flip an existing session to a soft challenge after suspicious behaviour. We need to detect that.
- **Block-detection sentinel for Domain**: status != 200 OR body < ~10 KB OR `_abck` cookie value contains `~-1~` (Akamai's "this is a bot" verdict marker — well-documented). The session abstraction can grow a `_DOMAIN_SENTINELS` mode using these.

## Open questions for engineering phase

1. **Single-suburb sweep cadence.** We made 2 requests cleanly. We don't yet know what rate Akamai tolerates. Start at OTH's 1 req / 2 s and ramp cautiously. The `_abck` verdict can flip mid-session.
2. **Re-bootstrap frequency.** Does the warm context survive 20 pages? 100? Likely safe for one suburb sweep. Plan to re-bootstrap per suburb until measured otherwise.
3. **Price normaliser.** `listingModel.price` is a free-form display string. Needs a parser that handles "For Sale", "Auction", "Contact Agent", "Offers over $X", "Price Guide $X – $Y", "EOI"/"Expressions of Interest", and yields `(numeric_low, numeric_high, method)` — where `method ∈ {price, range, auction, eoi, contact_agent, …}`. This is more nuance than OTH's `price` int — consider whether `listing_snapshot.price` stays an int or becomes a small JSONB.
4. **`status` mapping.** Domain encodes status in two places (URL segment `/sale/` vs `/sold/`, plus `tags.tagText`). The job source — which scrape list is being run — determines URL segment, so the worker already knows that. `tags.tagText` carries `Under offer` / `New` / `Updated` / null. The reconciler will need a Domain-specific status enum.
5. **GraphQL alternative.** `__NEXT_DATA__` is great but Next.js often also has client-side GraphQL/REST hops once the page mounts. The Domain payload has `graphqlApi` and `rootGraphQuery` keys with what look like Apollo cache state. If Domain serves a JSON API we can hit directly with the warm Akamai cookies, that's the OTH-style "one expensive bootstrap → many cheap hits" pattern. Worth a 1-day investigation in engineering.
6. **Detail vs search trade-off.** Search payload covers most material fields cleanly. The detail page adds `description` (the blurb), `headline`, `structuredFeatures`, agent contacts, school catchment, and Domain's `domainSays` analytics block. For diff-friendly material fields alone, search is enough. For a full snapshot mirroring OTH's `raw_payload`, we'd want detail pages — but at 20× the request volume (one per listing instead of 20 per page). Make this an explicit knob: `OTH_FETCH_DETAILS=true/false`.
7. **Auction listings with hidden coordinates.** Some auction listings have `address.lat`/`lng` zeroed and only `map.displayCentreLatitude`/`displayCentreLongitude` set. We need to pick which one to persist and document the rule (probably: prefer real lat/lng if non-null; fall back to display centre with a `coords_are_approximate` flag).
8. **School catchment data on detail pages.** Already in the payload (`schoolCatchment.schools`). This is directly relevant to the project's school-overlay map. Should we capture and persist it alongside the listing, or treat it as derivable from the address + a separate catchment source? Worth aligning with the frontend/data layer before committing to a model.
9. **Sentinel-string detection.** Confirmed there's no user-visible interstitial in the success case. The session abstraction's `_SENTINEL_STRINGS` list won't catch a future Akamai soft-challenge either. We need a Domain-specific block detector: `_abck` value pattern, status != 200, body length floor. Mirror the structure used for OTH but with Akamai-specific signals.
10. **Headless stability over hours.** This spike was 2 navs in ~17 s. The OTH soft-expiry sweep runs every 24 h. Engineering needs to confirm camoufox can run a 1000-listing sweep without crashing the way it did on the parallel oth-scraper worker rollout (see the Firefox-runtime-libs hotfix in commit `e12f516`).

## Recommendation

**Go in-house.** Build a Domain scraper modelled on `services/oth-scraper/` with the same architecture (job queue, snapshot diffing, soft-expiry, listing reconciler). The data source is `Next.js __NEXT_DATA__` extraction via camoufox.

Concretely, what the engineering phase needs to deliver:

- `services/domain-scraper/` parallel to `services/oth-scraper/`, sharing nothing in code but mirroring the architecture (deep + coordination modules per the OTH `CLAUDE.md`).
- New deep modules:
  - `domain_client` — Pydantic models for the Domain `listingsMap` entry, plus the price-string normaliser. Loads from a captured `__NEXT_DATA__` JSON, not from HTTP — `scrape_session` owns the page nav.
  - `scrape_session` (Domain variant) — camoufox bootstrap with the working baseline config; Akamai-cookie-aware block detection; warm-context reuse for detail pages.
  - `suburb_resolver` (Domain variant) — Domain's URL pattern is `/<sale|sold>/<suburb>-<state>-<postcode>/` — much simpler than OTH's autocomplete API. Probably just a string template + a one-time suburb-list seed.
- Reuse from `oth-scraper`:
  - `snapshot_diff`, `job_queue`, `rate_limiter`, `listing_reconciler` core, `worker_loop` skeleton — these are all source-agnostic. Either extract them to a shared package or copy-and-adapt.
- The `MATERIAL_FIELDS` tuple stays the same — Domain's data fits the OTH listing model cleanly, with the `price` parser doing the heavy lifting.

Do NOT pivot to Apify or any managed actor for Domain. The Phase 0 result is unambiguous: a 5-line camoufox call returns full structured data. The complexity is in the price normaliser, the reconciliation logic, and operating the worker — none of which Apify helps with.

Re-run the spike with a fresh IP / fresh cookie jar before engineering kicks off, just to confirm it wasn't a lucky run. One more 20-second test, not a project.

## Capture files

All under `services/domain-spike/captures/`:

- `next_data_search_paddington.json` — full `__NEXT_DATA__` from `/sale/paddington-qld-4064/` (canonical, copied from the per-config dir)
- `next_data_detail_2020841855.json` — full `__NEXT_DATA__` from the detail page `/31-alma-street-paddington-qld-4064-2020841855`
- `rollup.json` — per-config and per-URL summaries
- `run.log` — stdout/stderr from `spike_domain.py`
- `dom_01_baseline/search_paddington_sale/body.html` — raw HTML
- `dom_01_baseline/search_paddington_sale/screenshot.png` — visible viewport
- `dom_01_baseline/search_paddington_sale/nextdata.json` — same payload as the canonical, per-config copy
- `dom_01_baseline/search_paddington_sale/navigator.json` — fingerprint dump
- `dom_01_baseline/detail/body.html` — raw HTML of detail page
- `dom_01_baseline/detail/screenshot.png`
- `dom_01_baseline/detail/summary.json`
- `dom_01_baseline/summary.json` — config-level roll-up

Spike script: `services/domain-spike/spike_domain.py`. Re-run: `cd services/domain-spike && /Users/jethro/github/jkairys/school-map-worktrees/domain/services/rea-spike/.venv/bin/python spike_domain.py` (reuses the REA spike's `.venv` which already has `camoufox[geoip]` installed).
