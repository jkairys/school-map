"""Phase 0 spike: probe realestate.com.au with camoufox.

Goal: determine whether camoufox (stealth Firefox) can load a REA
search page from this machine without a proxy, and whether listing
data is exposed via `window.ArgonautExchange`. Output: a set of capture
files in ./captures/ and a printed per-page summary.

This is a throwaway script. Do not import from oth-scraper. Do not
build it into the production stack.
"""

import asyncio
import json
import logging
import random
import re
import sys
from pathlib import Path

from camoufox import AsyncCamoufox

LOG = logging.getLogger("rea-spike")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

CAPTURES_DIR = Path(__file__).parent / "captures"
CAPTURES_DIR.mkdir(exist_ok=True)

NAV_TIMEOUT_MS = 60_000
ANTI_BOT_WAIT_S = 10.0

SEARCH_URLS = [
    ("paddington_4064", "https://www.realestate.com.au/buy/in-paddington,+qld+4064/list-1"),
    ("carindale_4152", "https://www.realestate.com.au/buy/in-carindale,+qld+4152/list-1"),
]

# Sentinel strings that suggest an interstitial / block page.
SENTINELS = [
    "Pardon Our Interruption",
    "Reference #",
    "Checking your browser",
    "Just a moment",
    "Access Denied",
    "you have been blocked",
    "kasada",
    "Kasada",
]

KASADA_COOKIE_PATTERNS = [
    re.compile(r"^x-kpsdk", re.IGNORECASE),
    re.compile(r"^ips_", re.IGNORECASE),
    re.compile(r"kasada", re.IGNORECASE),
    re.compile(r"^KP_", re.IGNORECASE),
]


def is_kasada_cookie(name: str) -> bool:
    return any(p.search(name) for p in KASADA_COOKIE_PATTERNS)


async def settle_anti_bot(page) -> str:
    """Detect a Kasada challenge stub (KPSDK script + tiny body) and wait it out.

    REA's Kasada returns an HTTP 429 with a stub HTML containing a script tag
    that resolves the challenge and reloads. networkidle frequently fires
    before that reload happens, so we explicitly look for the KPSDK marker
    and poll for the page to change.
    """
    # Pass 1: text-based interstitial sentinels (Cloudflare-style etc.)
    try:
        body = await page.evaluate("() => (document.body && document.body.innerText) || ''")
    except Exception:
        body = ""
    if any(s in body for s in SENTINELS):
        LOG.info("text interstitial detected; waiting %.0fs", ANTI_BOT_WAIT_S)
        await asyncio.sleep(ANTI_BOT_WAIT_S)

    # Pass 2: Kasada stub detection. The KPSDK script declares window.KPSDK.
    try:
        kpsdk_present = await page.evaluate("() => typeof window.KPSDK !== 'undefined'")
        html_len = await page.evaluate("() => (document.documentElement.outerHTML || '').length")
    except Exception:
        kpsdk_present = False
        html_len = 0
    if kpsdk_present and html_len < 5000:
        LOG.info("Kasada KPSDK stub detected (html_len=%d); polling for resolution", html_len)
        for i in range(20):  # up to 30s
            await asyncio.sleep(1.5)
            try:
                cur_len = await page.evaluate(
                    "() => (document.documentElement.outerHTML || '').length"
                )
            except Exception:
                cur_len = 0
            if cur_len > 20000:
                LOG.info("page expanded after %d polls (len=%d)", i + 1, cur_len)
                break

    # Re-read body
    try:
        body = await page.evaluate("() => (document.body && document.body.innerText) || ''")
    except Exception:
        pass
    return body or ""


async def human_like_interaction(page) -> None:
    try:
        viewport = page.viewport_size
        if not viewport:
            return
        w = viewport["width"]
        h = viewport["height"]
        for _ in range(2):
            await page.mouse.move(
                random.randint(0, max(1, w - 1)),
                random.randint(0, max(1, h - 1)),
            )
            await asyncio.sleep(random.uniform(0.2, 0.7))
        await page.evaluate("() => window.scrollBy(0, window.innerHeight / 2)")
        await asyncio.sleep(random.uniform(0.5, 1.5))
    except Exception:
        LOG.debug("human-like interaction failed", exc_info=True)


def detect_sentinels(text: str) -> list[str]:
    if not text:
        return []
    return [s for s in SENTINELS if s in text]


async def visit(context, slug: str, url: str, *, is_detail: bool = False) -> dict:
    page = await context.new_page()
    summary: dict = {
        "slug": slug,
        "url": url,
        "is_detail": is_detail,
        "status": None,
        "final_url": None,
        "title": None,
        "html_size": 0,
        "argonaut_typeof": None,
        "argonaut_dump_path": None,
        "next_data_present": False,
        "next_data_dump_path": None,
        "html_path": None,
        "screenshot_path": None,
        "sentinels": [],
        "kasada_cookies": [],
        "all_cookie_names": [],
        "first_detail_url": None,
        "error": None,
    }
    try:
        # Use "load" so we don't bail out before the Kasada stub gets a chance
        # to execute its challenge script and reload the page.
        response = await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        if response is not None:
            summary["status"] = response.status
        # Now give Kasada time to resolve, then settle networkidle.
        body_text = await settle_anti_bot(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            LOG.info("networkidle did not settle within 30s; continuing")
        await human_like_interaction(page)
        # After interaction, do one more passive wait
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        summary["final_url"] = page.url
        summary["title"] = await page.title()

        html = await page.content()
        summary["html_size"] = len(html)
        html_path = CAPTURES_DIR / (
            f"detail_{slug}.html" if is_detail else f"search_{slug}.html"
        )
        html_path.write_text(html, encoding="utf-8")
        summary["html_path"] = str(html_path)

        png_path = CAPTURES_DIR / (
            f"detail_{slug}.png" if is_detail else f"search_{slug}.png"
        )
        try:
            await page.screenshot(path=str(png_path), full_page=False)
            summary["screenshot_path"] = str(png_path)
        except Exception as e:
            LOG.warning("screenshot failed: %s", e)

        # Sentinel detection from body text + page title
        combined = (body_text or "") + "\n" + (summary["title"] or "")
        summary["sentinels"] = detect_sentinels(combined)

        # ArgonautExchange probe
        argonaut_typeof = await page.evaluate("() => typeof window.ArgonautExchange")
        summary["argonaut_typeof"] = argonaut_typeof
        if argonaut_typeof == "object":
            try:
                dump = await page.evaluate(
                    "() => { try { return JSON.stringify(window.ArgonautExchange); }"
                    " catch (e) { return JSON.stringify({__err: String(e)}); } }"
                )
                dump_path = CAPTURES_DIR / (
                    f"argonaut_detail_{slug}.json" if is_detail else f"argonaut_{slug}.json"
                )
                dump_path.write_text(dump or "", encoding="utf-8")
                summary["argonaut_dump_path"] = str(dump_path)
            except Exception as e:
                LOG.warning("argonaut dump failed: %s", e)

        # __NEXT_DATA__ fallback
        try:
            next_present = await page.evaluate(
                "() => !!document.getElementById('__NEXT_DATA__')"
            )
        except Exception:
            next_present = False
        summary["next_data_present"] = bool(next_present)
        if next_present:
            try:
                next_text = await page.evaluate(
                    "() => (document.getElementById('__NEXT_DATA__') || {}).textContent || ''"
                )
                if next_text:
                    nd_path = CAPTURES_DIR / (
                        f"nextdata_detail_{slug}.json" if is_detail else f"nextdata_{slug}.json"
                    )
                    nd_path.write_text(next_text, encoding="utf-8")
                    summary["next_data_dump_path"] = str(nd_path)
            except Exception:
                pass

        # Cookies
        cookies = await context.cookies()
        all_names = [c.get("name", "") for c in cookies]
        summary["all_cookie_names"] = all_names
        summary["kasada_cookies"] = [n for n in all_names if is_kasada_cookie(n)]

        # For search pages, try to find a detail-page URL
        if not is_detail:
            detail_url = None
            # Prefer ArgonautExchange dump if present
            if summary["argonaut_dump_path"]:
                try:
                    raw = Path(summary["argonaut_dump_path"]).read_text(encoding="utf-8")
                    m = re.search(r'"(https://www\.realestate\.com\.au/property-[^"\\]+)"', raw)
                    if m:
                        detail_url = m.group(1)
                    if not detail_url:
                        m = re.search(r'"(/property-[a-z0-9\-]+/[^"\\]+)"', raw)
                        if m:
                            detail_url = "https://www.realestate.com.au" + m.group(1)
                except Exception:
                    pass
            if not detail_url:
                # Fall back to HTML grep
                m = re.search(r'href="(/property-[a-z0-9\-]+/[^"#?]+)"', html)
                if m:
                    detail_url = "https://www.realestate.com.au" + m.group(1)
            summary["first_detail_url"] = detail_url

    except Exception as e:
        LOG.exception("visit failed for %s", url)
        summary["error"] = repr(e)
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return summary


def print_summary(s: dict) -> None:
    print("=" * 80)
    print(f"URL:                {s['url']}")
    print(f"Final URL:          {s['final_url']}")
    print(f"Status:             {s['status']}")
    print(f"Title:              {s['title']!r}")
    print(f"HTML size:          {s['html_size']} bytes")
    print(f"ArgonautExchange:   typeof={s['argonaut_typeof']!r} dump={s['argonaut_dump_path']}")
    print(f"__NEXT_DATA__:      present={s['next_data_present']} dump={s['next_data_dump_path']}")
    print(f"Sentinels matched:  {s['sentinels']}")
    print(f"Kasada-ish cookies: {s['kasada_cookies']}")
    print(f"Total cookies:      {len(s['all_cookie_names'])}")
    print(f"HTML path:          {s['html_path']}")
    print(f"Screenshot path:    {s['screenshot_path']}")
    if not s["is_detail"]:
        print(f"First detail URL:   {s['first_detail_url']}")
    if s["error"]:
        print(f"ERROR:              {s['error']}")
    print("=" * 80, flush=True)


async def main() -> int:
    LOG.info("launching camoufox (headless=True, humanize=True)")
    results: list[dict] = []
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        try:
            # Warm up: visit homepage first so the browser collects Kasada
            # cookies organically before we hit a search page.
            LOG.info("warm-up: visiting homepage")
            warm = await visit(context, "homepage", "https://www.realestate.com.au/", is_detail=False)
            results.append(warm)
            print_summary(warm)

            # Try search URLs in order, stop on first success (no sentinels + status 200).
            search_summary = None
            for slug, url in SEARCH_URLS:
                LOG.info("visiting search: %s", url)
                s = await visit(context, slug, url, is_detail=False)
                results.append(s)
                print_summary(s)
                if (
                    s["status"] == 200
                    and not s["sentinels"]
                    and (s["argonaut_typeof"] == "object" or s["next_data_present"])
                ):
                    search_summary = s
                    break
                LOG.info("search attempt for %s did not look successful; trying next", slug)

            if search_summary is None:
                LOG.warning("no search URL succeeded cleanly; skipping detail fetch")
            else:
                detail_url = search_summary["first_detail_url"]
                if not detail_url:
                    LOG.warning("no detail URL extracted from %s; skipping", search_summary["slug"])
                else:
                    # Derive a stable-ish slug for the detail page from the URL tail
                    tail = detail_url.rstrip("/").rsplit("/", 1)[-1]
                    detail_slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", tail)[:80] or "detail"
                    LOG.info("visiting detail: %s", detail_url)
                    d = await visit(context, detail_slug, detail_url, is_detail=True)
                    results.append(d)
                    print_summary(d)
        finally:
            await context.close()

    # Persist a roll-up JSON for the report
    rollup_path = CAPTURES_DIR / "summary.json"
    rollup_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    LOG.info("wrote roll-up %s", rollup_path)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
