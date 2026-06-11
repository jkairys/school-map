"""Phase 0 spike: probe domain.com.au with camoufox.

Goal: validate whether camoufox can get past Akamai Bot Manager on
www.domain.com.au from this developer machine. Success = HTTP 200 +
body > 50 KB + __NEXT_DATA__ present.

Matrix of 5 camoufox configs against /sale/paddington-qld-4064/.
Stops on the first success and then fetches one detail page with the
same config (reusing the same browser context, so the warm Akamai
cookie jar stays intact).

Throwaway script. Do not import from oth-scraper.
"""

import asyncio
import json
import logging
import re
import sys
import traceback
from pathlib import Path

from camoufox import AsyncCamoufox

LOG = logging.getLogger("domain-spike")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

CAPTURES_DIR = Path(__file__).parent / "captures"
CAPTURES_DIR.mkdir(exist_ok=True)

NAV_TIMEOUT_MS = 60_000
NETWORKIDLE_TIMEOUT_MS = 60_000
NEXTDATA_POLL_S = 15.0
INTER_CONFIG_SLEEP_S = 60.0
SUCCESS_BODY_MIN = 50_000

SEARCH_URLS = [
    ("paddington_sale", "https://www.domain.com.au/sale/paddington-qld-4064/"),
    ("carindale_sale", "https://www.domain.com.au/sale/carindale-qld-4152/"),
    ("paddington_sold", "https://www.domain.com.au/sold/paddington-qld-4064/"),
]

# Akamai Bot Manager cookies of interest
AKAMAI_COOKIE_NAMES = {"ak_bmsc", "bm_sv", "bm_sz", "_abck", "bm_mi", "bm_so", "bm_lso"}

SENTINELS = [
    "Pardon Our Interruption",
    "Reference #",
    "Access Denied",
    "you have been blocked",
    "Akamai",
    "Just a moment",
    "Checking your browser",
]

NAVIGATOR_PROBE = """
() => {
    try {
        return {
            ua: navigator.userAgent,
            platform: navigator.platform,
            languages: navigator.languages,
            language: navigator.language,
            webdriver: navigator.webdriver,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            screen: { w: screen.width, h: screen.height, dpr: window.devicePixelRatio },
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        };
    } catch (e) {
        return { error: String(e) };
    }
}
"""


# Each config: (name, camoufox_kwargs)
CONFIGS = [
    ("01_baseline", {"headless": True, "humanize": True}),
    ("02_macos", {"headless": True, "humanize": True, "os": "macos"}),
    ("03_macos_enau", {"headless": True, "humanize": True, "os": "macos", "locale": "en-AU"}),
    ("04_headed_macos_enau", {"headless": False, "humanize": True, "os": "macos", "locale": "en-AU"}),
    ("05_headed_geoip", {"headless": False, "humanize": True, "os": "macos", "geoip": True}),
]


def detect_sentinels(text: str) -> list[str]:
    if not text:
        return []
    return [s for s in SENTINELS if s in text]


async def wait_for_nextdata(page, *, timeout_s: float) -> bool:
    """Poll for __NEXT_DATA__ element presence for up to `timeout_s`."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            present = await page.evaluate(
                "() => document.getElementById('__NEXT_DATA__') !== null"
            )
        except Exception:
            present = False
        if present:
            return True
        await asyncio.sleep(0.5)
    return False


async def probe_url(context, url: str, out_dir: Path, *, slug: str) -> dict:
    page = await context.new_page()
    summary: dict = {
        "url": url,
        "slug": slug,
        "status": None,
        "final_url": None,
        "title": None,
        "html_size": 0,
        "next_data_present": False,
        "next_data_path": None,
        "listing_dom_present": False,
        "screenshot_path": None,
        "html_path": None,
        "navigator_path": None,
        "all_cookie_names": [],
        "akamai_cookies": [],
        "sentinels": [],
        "error": None,
    }
    try:
        response = await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        if response is not None:
            summary["status"] = response.status

        # Try networkidle, then poll for __NEXT_DATA__
        try:
            await page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT_MS)
        except Exception:
            LOG.info("networkidle did not settle within %ds; continuing", NETWORKIDLE_TIMEOUT_MS // 1000)

        nextdata_present = await wait_for_nextdata(page, timeout_s=NEXTDATA_POLL_S)
        summary["next_data_present"] = nextdata_present

        summary["final_url"] = page.url
        try:
            summary["title"] = await page.title()
        except Exception:
            pass

        try:
            html = await page.content()
        except Exception as e:
            html = ""
            summary["error"] = f"content_failed: {e!r}"
        summary["html_size"] = len(html)

        html_path = out_dir / "body.html"
        html_path.write_text(html, encoding="utf-8")
        summary["html_path"] = str(html_path)

        png_path = out_dir / "screenshot.png"
        try:
            await page.screenshot(path=str(png_path), full_page=False)
            summary["screenshot_path"] = str(png_path)
        except Exception as e:
            LOG.warning("screenshot failed: %s", e)

        if nextdata_present:
            try:
                nd_text = await page.evaluate(
                    "() => (document.getElementById('__NEXT_DATA__') || {}).textContent || ''"
                )
                if nd_text:
                    nd_path = out_dir / "nextdata.json"
                    nd_path.write_text(nd_text, encoding="utf-8")
                    summary["next_data_path"] = str(nd_path)
            except Exception:
                pass

        # DOM-level sanity check
        try:
            listing_present = await page.evaluate(
                "() => Boolean(document.querySelector('[data-testid*=\"listing\"]'))"
            )
        except Exception:
            listing_present = False
        summary["listing_dom_present"] = bool(listing_present)

        nav = await page.evaluate(NAVIGATOR_PROBE)
        nav_path = out_dir / "navigator.json"
        nav_path.write_text(json.dumps(nav, indent=2, default=str), encoding="utf-8")
        summary["navigator_path"] = str(nav_path)

        # Cookies
        cookies = await context.cookies()
        all_names = [c.get("name", "") for c in cookies]
        summary["all_cookie_names"] = all_names
        summary["akamai_cookies"] = [n for n in all_names if n in AKAMAI_COOKIE_NAMES]

        # Sentinel match on body text + title
        try:
            body_text = await page.evaluate(
                "() => (document.body && document.body.innerText) || ''"
            )
        except Exception:
            body_text = ""
        combined = (body_text or "") + "\n" + (summary["title"] or "")
        summary["sentinels"] = detect_sentinels(combined)

    except Exception as e:
        LOG.exception("probe failed for %s", url)
        summary["error"] = repr(e)
    return page, summary


def is_success(summary: dict) -> bool:
    return (
        summary.get("status") == 200
        and summary.get("html_size", 0) > SUCCESS_BODY_MIN
        and summary.get("next_data_present") is True
    )


def print_summary(cs: dict) -> None:
    print("=" * 80)
    print(f"Config:             {cs.get('name')}")
    print(f"Kwargs:             {cs.get('kwargs')}")
    if cs.get("launch_error"):
        print(f"LAUNCH ERROR:       {cs['launch_error']}")
    r = cs.get("result") or {}
    print(f"URL:                {r.get('url')}")
    print(f"Status:             {r.get('status')}")
    print(f"Final URL:          {r.get('final_url')}")
    print(f"HTML size:          {r.get('html_size')}")
    print(f"__NEXT_DATA__:      {r.get('next_data_present')}")
    print(f"listing DOM:        {r.get('listing_dom_present')}")
    print(f"Title:              {r.get('title')!r}")
    print(f"Akamai cookies:     {r.get('akamai_cookies')}")
    print(f"All cookie count:   {len(r.get('all_cookie_names') or [])}")
    print(f"Sentinels:          {r.get('sentinels')}")
    print(f"Error:              {r.get('error')}")
    print("=" * 80, flush=True)


def extract_detail_url(nextdata_path: Path, html_path: Path) -> str | None:
    """Try to find one listing detail URL from the search-page __NEXT_DATA__ or HTML."""
    # First: try JSON dump for a domain.com.au/<slug>-<id> style URL
    if nextdata_path and nextdata_path.exists():
        try:
            raw = nextdata_path.read_text(encoding="utf-8")
        except Exception:
            raw = ""
        # Domain detail URLs: /<suburb-state-postcode>/...-<id>
        # listingSlug or url fields
        # Match a fully-qualified url with /<state>-<postcode>/...-<digits>
        m = re.search(
            r'"(https://www\.domain\.com\.au/[a-z0-9\-]+-[a-z]{2,3}-\d{4}/[^"\\?\s]+-\d{6,})"',
            raw,
        )
        if m:
            return m.group(1)
        # Path-only
        m = re.search(
            r'"(/[a-z0-9\-]+-[a-z]{2,3}-\d{4}/[a-z0-9\-]+-\d{6,})"',
            raw,
        )
        if m:
            return "https://www.domain.com.au" + m.group(1)
        # Looser: any /<digits>$ at end of path inside a quoted url
        m = re.search(
            r'"(https://www\.domain\.com\.au/[^"\\?\s]+-\d{6,})"',
            raw,
        )
        if m:
            return m.group(1)

    if html_path and html_path.exists():
        try:
            html = html_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            html = ""
        m = re.search(
            r'href="(/[a-z0-9\-]+-[a-z]{2,3}-\d{4}/[a-z0-9\-]+-\d{6,})"',
            html,
        )
        if m:
            return "https://www.domain.com.au" + m.group(1)
        m = re.search(
            r'href="(https://www\.domain\.com\.au/[a-z0-9\-]+-[a-z]{2,3}-\d{4}/[a-z0-9\-]+-\d{6,})"',
            html,
        )
        if m:
            return m.group(1)

    return None


async def run_config(name: str, kwargs: dict) -> tuple[dict, dict | None]:
    """Run one camoufox config against the search URLs in order.

    Returns (config_summary, detail_summary_or_None). detail_summary is set
    only if a search URL succeeded AND a detail page was fetched.
    """
    out_root = CAPTURES_DIR / f"dom_{name}"
    out_root.mkdir(parents=True, exist_ok=True)

    LOG.info("=== config %s : kwargs=%s ===", name, kwargs)
    config_summary: dict = {
        "name": name,
        "kwargs": {k: str(v) for k, v in kwargs.items()},
        "result": None,
        "search_attempts": [],
        "launch_error": None,
    }
    detail_summary: dict | None = None

    try:
        async with AsyncCamoufox(**kwargs) as browser:
            context = await browser.new_context()
            try:
                winning_search = None
                winning_page = None
                for slug, url in SEARCH_URLS:
                    out_dir = out_root / f"search_{slug}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    LOG.info("config %s: visiting %s", name, url)
                    page, r = await probe_url(context, url, out_dir, slug=slug)
                    config_summary["search_attempts"].append(r)
                    if is_success(r):
                        winning_search = r
                        winning_page = page
                        config_summary["result"] = r
                        LOG.info(
                            "config %s: success on %s (status=%s html=%d nextdata=%s)",
                            name,
                            slug,
                            r.get("status"),
                            r.get("html_size"),
                            r.get("next_data_present"),
                        )
                        break
                    else:
                        try:
                            await page.close()
                        except Exception:
                            pass
                        LOG.info(
                            "config %s: %s did NOT succeed (status=%s html=%d nextdata=%s); trying next URL",
                            name,
                            slug,
                            r.get("status"),
                            r.get("html_size"),
                            r.get("next_data_present"),
                        )

                if winning_search is None:
                    config_summary["result"] = (
                        config_summary["search_attempts"][0]
                        if config_summary["search_attempts"]
                        else None
                    )

                # On success, fetch one detail page with the same warm context
                if winning_search is not None and winning_page is not None:
                    # Save the search __NEXT_DATA__ under the canonical name
                    nd_path = Path(winning_search.get("next_data_path") or "")
                    if nd_path.exists():
                        canonical = CAPTURES_DIR / "next_data_search_paddington.json"
                        canonical.write_text(
                            nd_path.read_text(encoding="utf-8"), encoding="utf-8"
                        )
                        LOG.info("saved canonical search __NEXT_DATA__ to %s", canonical)

                    html_path = Path(winning_search.get("html_path") or "")
                    detail_url = extract_detail_url(nd_path, html_path)
                    LOG.info("extracted detail URL: %r", detail_url)

                    if detail_url:
                        # Reuse the same page; keeps the warm Akamai cookie jar
                        detail_out_dir = out_root / "detail"
                        detail_out_dir.mkdir(parents=True, exist_ok=True)
                        await asyncio.sleep(5.0)
                        # Use winning_page directly: navigate it to the detail URL
                        d_summary: dict = {
                            "url": detail_url,
                            "slug": "detail",
                            "status": None,
                            "final_url": None,
                            "title": None,
                            "html_size": 0,
                            "next_data_present": False,
                            "next_data_path": None,
                            "listing_dom_present": False,
                            "screenshot_path": None,
                            "html_path": None,
                            "navigator_path": None,
                            "all_cookie_names": [],
                            "akamai_cookies": [],
                            "sentinels": [],
                            "error": None,
                        }
                        try:
                            resp = await winning_page.goto(
                                detail_url,
                                wait_until="load",
                                timeout=NAV_TIMEOUT_MS,
                            )
                            if resp is not None:
                                d_summary["status"] = resp.status
                            try:
                                await winning_page.wait_for_load_state(
                                    "networkidle", timeout=NETWORKIDLE_TIMEOUT_MS
                                )
                            except Exception:
                                pass
                            nd_present = await wait_for_nextdata(
                                winning_page, timeout_s=NEXTDATA_POLL_S
                            )
                            d_summary["next_data_present"] = nd_present
                            d_summary["final_url"] = winning_page.url
                            try:
                                d_summary["title"] = await winning_page.title()
                            except Exception:
                                pass
                            try:
                                d_html = await winning_page.content()
                            except Exception:
                                d_html = ""
                            d_summary["html_size"] = len(d_html)
                            (detail_out_dir / "body.html").write_text(
                                d_html, encoding="utf-8"
                            )
                            d_summary["html_path"] = str(
                                detail_out_dir / "body.html"
                            )
                            try:
                                await winning_page.screenshot(
                                    path=str(detail_out_dir / "screenshot.png"),
                                    full_page=False,
                                )
                                d_summary["screenshot_path"] = str(
                                    detail_out_dir / "screenshot.png"
                                )
                            except Exception:
                                pass
                            if nd_present:
                                try:
                                    nd_text = await winning_page.evaluate(
                                        "() => (document.getElementById('__NEXT_DATA__') || {}).textContent || ''"
                                    )
                                    if nd_text:
                                        # Detail ID heuristic: trailing -<digits>
                                        m = re.search(r"-(\d{6,})/?$", detail_url)
                                        detail_id = m.group(1) if m else "unknown"
                                        canonical = (
                                            CAPTURES_DIR
                                            / f"next_data_detail_{detail_id}.json"
                                        )
                                        canonical.write_text(
                                            nd_text, encoding="utf-8"
                                        )
                                        d_summary["next_data_path"] = str(canonical)
                                        LOG.info(
                                            "saved canonical detail __NEXT_DATA__ to %s",
                                            canonical,
                                        )
                                except Exception:
                                    pass
                            try:
                                listing_present = await winning_page.evaluate(
                                    "() => Boolean(document.querySelector('[data-testid*=\"listing\"]'))"
                                )
                            except Exception:
                                listing_present = False
                            d_summary["listing_dom_present"] = bool(listing_present)
                            cookies = await context.cookies()
                            all_names = [c.get("name", "") for c in cookies]
                            d_summary["all_cookie_names"] = all_names
                            d_summary["akamai_cookies"] = [
                                n for n in all_names if n in AKAMAI_COOKIE_NAMES
                            ]
                        except Exception as e:
                            LOG.exception("detail nav failed")
                            d_summary["error"] = repr(e)
                        detail_summary = {
                            "name": f"{name}_detail",
                            "kwargs": {k: str(v) for k, v in kwargs.items()},
                            "result": d_summary,
                        }
                        (detail_out_dir / "summary.json").write_text(
                            json.dumps(detail_summary, indent=2, default=str),
                            encoding="utf-8",
                        )

                if winning_page is not None:
                    try:
                        await winning_page.close()
                    except Exception:
                        pass
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
    except Exception as e:
        LOG.exception("camoufox launch failed for %s", name)
        config_summary["launch_error"] = repr(e)
        config_summary["launch_traceback"] = traceback.format_exc()

    (out_root / "summary.json").write_text(
        json.dumps(config_summary, indent=2, default=str), encoding="utf-8"
    )
    return config_summary, detail_summary


async def main() -> int:
    all_results: list[dict] = []
    winner: dict | None = None
    winner_detail: dict | None = None

    for i, (name, kwargs) in enumerate(CONFIGS):
        cs, det = await run_config(name, kwargs)
        all_results.append(cs)
        print_summary(cs)
        if det:
            print_summary(det)

        r = cs.get("result") or {}
        if is_success(r):
            LOG.info("*** SUCCESS on config %s ***", name)
            winner = cs
            winner_detail = det
            break

        if i < len(CONFIGS) - 1:
            LOG.info(
                "sleeping %.0fs before next config (don't burst Akamai)",
                INTER_CONFIG_SLEEP_S,
            )
            await asyncio.sleep(INTER_CONFIG_SLEEP_S)

    rollup = {
        "winner": winner["name"] if winner else None,
        "configs_run": [r["name"] for r in all_results],
        "results": all_results,
        "winner_detail": winner_detail,
    }
    (CAPTURES_DIR / "rollup.json").write_text(
        json.dumps(rollup, indent=2, default=str), encoding="utf-8"
    )
    LOG.info("wrote rollup to %s", CAPTURES_DIR / "rollup.json")
    LOG.info(
        "winner: %s",
        winner["name"] if winner else "NONE (all configs failed)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
