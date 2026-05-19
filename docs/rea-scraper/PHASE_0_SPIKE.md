# REA scraper — Phase 0 spike

## Outcome

**BLOCKED.** Camoufox + humanize, no proxy, from this developer machine, gets a hard Kasada block on every realestate.com.au page (homepage, search). The challenge JS runs and telemetry is accepted by the server, but no real content is ever served. We were unable to capture any `ArgonautExchange` payload or any listing HTML.

## What worked

- Camoufox installation and Firefox build fetch were clean (`uv pip install 'camoufox[geoip]'`, then `python -m camoufox fetch`).
- Camoufox launches headless with `humanize=True` and navigates fine in the abstract — the mechanism mirrors `services/oth-scraper/src/oth_scraper/scrape_session/bootstrap.py`.
- The Kasada client-side challenge JS (`/<uuid>/<uuid>/ips.js`) loaded successfully (HTTP 200) and executed inside camoufox's Firefox. It posted telemetry to `/<uuid>/<uuid>/tl` (HTTP 200) and the server set fresh `KP_UIDz` / `KP_UIDz-ssn` cookies in response.
- Capture pipeline works (HTML, PNG, ArgonautExchange/`__NEXT_DATA__` probes, cookie dumping). Re-usable for the engineering phase once we get past the block.

## What didn't

- **Every navigation returns HTTP 429** with a tiny (≈770–820 byte) stub HTML containing only the Kasada bootstrap script + a hidden iframe. No `<head>`. No content. The page never reloads or re-navigates after the challenge JS submits telemetry — confirmed by polling `document.documentElement.outerHTML.length` for 30 s, which stays flat at ~757 chars. Screenshots are blank.
- This was reproduced on three independent navigations: `/` (homepage), `/buy/in-paddington,+qld+4064/list-1`, `/buy/in-carindale,+qld+4152/list-1`. All three: status 429, KPSDK stub, page never resolves.
- Neither `window.ArgonautExchange` nor `__NEXT_DATA__` was ever present. We could not verify the listing-record shape from a live capture.
- No "Pardon Our Interruption" / "Reference #" interstitial — Kasada at REA is configured for the silent-block flavour, not the user-visible challenge-page flavour. Standard sentinel-string detection (Cloudflare-style "Checking your browser" / "Just a moment") will NOT catch this; you have to detect the KPSDK stub (`window.KPSDK` defined + `document.documentElement.outerHTML.length < 5000`) or the 429 status.

## Data shape findings

We could not observe ArgonautExchange in this spike. The prior assumption — that listing data lives under `window.ArgonautExchange` — was not confirmed or refuted. This remains an open question for the engineering phase.

What we did learn about the response surface, indirectly:

- The Kasada stub response carries useful server headers we can fingerprint to detect a block:
  - `x-kpsdk-ct: <token>` is always present on the 429
  - `Set-Cookie` always carries `KP_UIDz`, `KP_UIDz-ssn` (Kasada session ids) and `Country=AU`
  - The `ips.js` and `/tl` responses set `reauid` (REA's own user id cookie, 100-year expiry) — this is a normal REA cookie also seen by genuine browsers, so it is not block-specific
- Comparison to the OTH `listing_snapshot` material-fields list (price, title, blurb, bedrooms, bathrooms, parking, land_size_sqm, property_type, status) is **deferred** until we obtain a real REA listing payload.

## Anti-bot observations

REA uses Kasada (KP_UIDz cookies + `/<uuid>/<uuid>/ips.js` challenge endpoint + `/<uuid>/<uuid>/tl` telemetry endpoint). The relevant observations from this run:

| Signal | Value |
|---|---|
| First-nav response status | 429 (on every attempted URL) |
| Body size | ~770 bytes (Kasada stub only) |
| Kasada cookies set | `KP_UIDz`, `KP_UIDz-ssn` |
| `ips.js` load | 200, executes inside camoufox Firefox |
| `tl` telemetry POST | 200, server issues new KP_UIDz token |
| Post-challenge reload | **Does not happen** — page DOM stays at the 770-byte stub indefinitely |
| User-visible interstitial | None — Kasada returns a stub, not a "Pardon Our Interruption" page |
| Camoufox + humanize sufficient? | **No.** Challenge JS runs, telemetry is accepted, but the classifier still refuses to issue a usable session |
| Proxy used | None (residential AU IP, single host) |

Why this is hard: the challenge succeeded mechanically (telemetry accepted, fresh token issued) but the classifier verdict was "still a bot". This is the canonical Kasada hard-block — it means our environment fingerprint is being detected at a layer below `humanize=True`, likely one of:
- camoufox's default browser fingerprint (UA family, screen, fonts, plugins, WebGL) being a known bot-fingerprint
- TLS / HTTP/2 fingerprint of camoufox's Firefox bundle
- IP reputation (this developer IP may have a poor REA reputation)
- The combination "Australian IP + headless Firefox + no human history" being out-of-distribution

The spike's brief explicitly time-boxes Kasada bypass work to the engineering phase, so we stopped here.

## Open questions for engineering phase

1. **Proxy strategy.** Is REA blocking this specific IP, or is it the fingerprint? Re-run from a residential AU proxy (Bright Data, Smartproxy AU pool) before any other tweak. If a clean residential IP works, every other knob is secondary. If it still 429s, the fingerprint is the problem.
2. **Camoufox fingerprint pinning.** We ran with no `os=` / no `fingerprint=`. The Kasada classifier may be flagging camoufox's randomized fingerprint. Try `os="macos"` and a fixed fingerprint seed.
3. **Apify / pre-built REA actor as a fallback.** If we can't crack Kasada with reasonable effort, Apify (and Scrapfly, ScraperAPI) sell REA actors specifically because Kasada is hard. Engineering should price-out a managed solution before sinking weeks into bypass.
4. **Is `window.ArgonautExchange` actually the right global?** Unverified by this spike. The Scrapfly writeup says yes, but until we see a real page we don't know. The engineering phase should re-verify and also dump the full window-global keyset on first success.
5. **Pagination shape.** URL is `/list-N` — does state live there alone, or does the SPA fetch a JSON API after first load that we could hit directly with a warmed Kasada cookie? If yes, that's the preferred path (one expensive bootstrap → many cheap API hits, mirroring how OTH-scraper works).
6. **Detail-page vs search-result data parity.** Unanswered. Likely the detail page has richer description / agent / inspection-time fields, but until we see both we can't decide whether to fetch detail pages or rely on search payloads alone (relevant for cost: detail pages roughly multiply request volume by 30×).
7. **Block-detection sentinels for the worker loop.** The `_SENTINEL_STRINGS` list in `scrape_session/session.py` will not catch REA's silent block — there's no body text to match. The session abstraction will need a new detection mode: "status 429 + body length < 5000 + `window.KPSDK` defined", or simply "status 429 on REA hostname".
8. **Per-page rate.** Cannot be measured from a fully-blocked spike. Once we have a working bootstrap, the engineering phase needs a real rate-limit probe (start at OTH's 1 req/2s and ramp up cautiously).
9. **Are the existing OTH session-rotation primitives reusable?** Almost certainly yes (cookies, UA, accept-language injection at the transport layer is generic), but the *bootstrap* function for REA will be different and the block-detection sentinels will be different. Plan to add a `bootstrap_via_camoufox_rea()` variant rather than overloading the existing one.

## Recommendation

**"Go but with a proxy" — with a clear fallback to Apify if the proxy doesn't shift the verdict.**

Concretely, the engineering phase should:

1. Spend ≤ 1 day re-running this spike from a paid residential AU proxy. If that flips the 429 to 200 and exposes `ArgonautExchange`, proceed with the in-house scraper modelled on `services/oth-scraper/`.
2. If proxied attempts still 429, spend ≤ 1 more day on camoufox fingerprint pinning + slower human-like flow.
3. If both fail, switch to Apify's REA actor (or a comparable managed scraper). The OTH-scraper architecture (job queue, snapshot diffing, soft-expiry, listing reconciler) is the load-bearing part of the project — the *source* of the listing JSON is interchangeable. A managed actor that returns JSON conformant to a Pydantic model is just another implementation of `rea_client.search(...)`.

Do NOT attempt to write a custom Kasada solver. That's a multi-month research project and not the goal of this app.

## Capture files

All under `services/rea-spike/captures/`:

- `search_homepage.html` / `.png` — 429 Kasada stub from `/`
- `search_paddington_4064.html` / `.png` — 429 Kasada stub from `/buy/in-paddington,+qld+4064/list-1`
- `search_carindale_4152.html` / `.png` — 429 Kasada stub from `/buy/in-carindale,+qld+4152/list-1`
- `summary.json` — roll-up of per-page summaries from the main spike
- `network_log.json` — full request/response log from `spike_network.py` (homepage), shows the `ips.js` + `/tl` challenge round-trip
- `network_final.html` / `.png` — page state after 30 s of waiting on the homepage (still the 770-byte stub)

Spike scripts:

- `services/rea-spike/spike.py` — main probe (homepage warm-up → 2 search URLs → first detail page)
- `services/rea-spike/spike_network.py` — companion probe with full network instrumentation
- `services/rea-spike/pyproject.toml` — minimal `camoufox[geoip]` dep set, isolated `.venv`

Re-run: `cd services/rea-spike && uv venv && uv pip install 'camoufox[geoip]' && .venv/bin/python -m camoufox fetch && .venv/bin/python spike.py`.

---

## Phase 0b — fingerprint matrix

Phase 0a left two hypotheses alive: (a) the developer IP is bad, (b) the camoufox fingerprint is being flagged. The user confirmed (a) is unlikely — they are on an Australian residential IP. Phase 0b ran 8 camoufox configurations against `https://www.realestate.com.au/buy/in-paddington,+qld+4064/list-1` to test (b).

**Outcome: BLOCKED. All configs returned 429 with a ~770–820 byte Kasada stub.**

### Results

| # | Config | Status | HTML size | ArgonautExchange | Verdict |
|---|---|---|---|---|---|
| 01 | `headless=True, humanize=True` | 429 | 818 | undefined | block |
| 02 | + `os="macos"` | 429 | 818 | undefined | block |
| 03 | + `locale="en-AU"` | 429 | 818 | undefined | block |
| 04 | `headless=False, humanize=True, os=macos, locale=en-AU` | 429 | 818 | undefined | block |
| 05 | `headless=False, humanize=True, os=macos, geoip=True` | 429 | 785 | undefined | block |
| 06 | `headless=False, humanize=False, os=macos, geoip=True` | 429 | 784 | undefined | block |
| 07 | #04 + Google warm-up (referrer chain) | 429 | 818 | undefined | block |
| 08 | `headless="virtual"` | n/a | n/a | n/a | launch error — virtual-display is Linux-only in camoufox |

Every successful launch was rejected at the network layer. Even headed mode + Google referrer + geoip-derived locale didn't shift the verdict. The 429 returns *before* any client JS gets a chance to run — i.e. Kasada is fingerprinting at L7 (TLS/HTTP2/header order) and refusing to even serve the challenge page to us. That's a step harder than the Phase 0a observation, where the challenge JS ran before the silent block.

Note one quirk: camoufox without `os=` pinning presented `platform: "Win32"` + `UA: ...Win64; x64; ...Firefox/135.0` despite running on macOS. That's expected (camoufox spoofs by default) but it means the L7 fingerprint Kasada is rejecting may include something the spoof can't change — JA3 TLS signature is the prime suspect, as camoufox uses Firefox's actual TLS stack.

### What this rules out

- **Headlessness alone** — config 04 is fully headed and still 429s.
- **Locale / timezone / OS family** — combinations of these don't help.
- **Humanize** — both on and off block identically.
- **Referrer chain** — coming in from Google doesn't help.
- **The "first nav warm-up" theory** — Phase 0a established that even after a successful homepage telemetry round-trip, search pages stay blocked. Phase 0b confirms the homepage itself is gated now too.

What's left untested: residential proxies (user said own IP is residential AU, so this is unlikely to be the fix), TLS-fingerprint patching (camoufox doesn't expose this knob), or full-browser solutions like Playwright + a real Chrome with a recently-warm cookie jar (untried).

### Updated recommendation: **pivot to Apify (or comparable managed actor)**

The in-house bypass path is **not viable at any reasonable effort budget**. We've spent the camoufox tuning budget; the remaining knob (TLS / JA3 patching) is a research project, not an engineering task. Kasada's value-prop to REA is specifically that they mutate defences faster than scrapers can adapt — that's the wall we're hitting.

The OTH-scraper architecture is the load-bearing part of the project. Concretely:

- `services/oth-scraper/src/oth_scraper/queue/`, `rate_limiter/`, `snapshot_diff.py`, `listing_reconciler/`, `worker_loop/` — all reusable as-is
- `oth_client/` — interface contract is "given a `(suburb, category, filters, page)`, return a list of listing records". Apify (or any actor that returns JSON) is one implementation; OTH's JSON API is another. Build a thin `rea_apify_client.py` that calls the Apify Actor API, polls, and returns the same Pydantic shape.
- `scrape_session/` — not needed in an Apify path. The actor owns the browser.
- `suburb_resolver/` — keep, but resolve via Apify's actor inputs (which accept REA suburb URLs directly).

**Concrete next steps for engineering phase**:

1. Sign up for Apify, run `azzouzana/real-estate-au-scraper-pro` against one Brisbane suburb (Paddington) for ≤$1 to see the actual JSON shape it returns.
2. Compare its field coverage to OTH's `listing_snapshot` material fields and to what we'd want long-term.
3. Decide whether to (a) wrap the Apify actor as the listing source, accepting a $10-30/sweep ongoing cost, or (b) walk away from REA entirely and stay with OTH despite known gaps.
4. If walking away: revisit Domain — its Akamai challenge is meaningfully easier than Kasada and the original Domain spike (not run) may yet succeed. Phase 0a's report flagged this as the natural fallback.

### Files produced in 0b

Under `services/rea-spike/captures/`:

- `fp_01_baseline/` … `fp_08_virtual/` — per-config `body.html`, `screenshot.png`, `navigator.json`, `summary.json`
- `fp_rollup.json` — combined results across all 8 configs
- `fp_run.log` — full timestamped log

Spike script: `services/rea-spike/spike_fingerprint.py`.
