"""Phase 0b spike: matrix of camoufox fingerprint configurations against one REA URL.

For each config, captures status, body size, ArgonautExchange presence,
screenshot, navigator fingerprint dump. Saves under captures/fp_<name>/.

Stops on first config that returns HTTP 200 + body > 50 KB + ArgonautExchange.
On success, also fetches one detail page with the same config.

Runs sequentially with a 60s sleep between configs to space out KP_UIDz
cookie issuance — we don't want to look like a scrape burst.
"""

import asyncio
import json
import logging
import re
import sys
import traceback
from pathlib import Path

from camoufox import AsyncCamoufox

LOG = logging.getLogger("rea-spike-fp")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

CAPTURES_DIR = Path(__file__).parent / "captures"
CAPTURES_DIR.mkdir(exist_ok=True)

NAV_TIMEOUT_MS = 60_000
SETTLE_SECONDS = 30.0
INTER_CONFIG_SLEEP_S = 60.0

TARGET_URL = "https://www.realestate.com.au/buy/in-paddington,+qld+4064/list-1"
GOOGLE_REFERRER_URL = "https://www.google.com/search?q=realestate+paddington+brisbane"

SUCCESS_BODY_MIN = 50_000

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


# Each config is a tuple: (name, camoufox_kwargs, special_mode)
# special_mode: None | "warmup_google"
CONFIGS = [
    ("01_baseline", {"headless": True, "humanize": True}, None),
    ("02_macos", {"headless": True, "humanize": True, "os": "macos"}, None),
    ("03_macos_enau", {"headless": True, "humanize": True, "os": "macos", "locale": "en-AU"}, None),
    ("04_headed_macos_enau", {"headless": False, "humanize": True, "os": "macos", "locale": "en-AU"}, None),
    ("05_headed_geoip", {"headless": False, "humanize": True, "os": "macos", "geoip": True}, None),
    ("06_no_humanize", {"headless": False, "humanize": False, "os": "macos", "geoip": True}, None),
    ("07_google_warmup", {"headless": False, "humanize": True, "os": "macos", "locale": "en-AU"}, "warmup_google"),
    ("08_virtual", {"headless": "virtual", "humanize": True, "os": "macos"}, None),
]


def is_success(summary: dict) -> bool:
    return (
        summary.get("status") == 200
        and summary.get("html_size", 0) > SUCCESS_BODY_MIN
        and summary.get("argonaut_typeof") == "object"
    )


async def capture_navigator(page) -> dict:
    try:
        return await page.evaluate(NAVIGATOR_PROBE)
    except Exception as e:
        return {"error": repr(e)}


async def probe_url(context, url: str, out_dir: Path, *, referer: str | None = None) -> dict:
    page = await context.new_page()
    summary: dict = {
        "url": url,
        "referer": referer,
        "status": None,
        "final_url": None,
        "title": None,
        "html_size": 0,
        "argonaut_typeof": None,
        "argonaut_dump_path": None,
        "next_data_present": False,
        "kasada_stub_detected": False,
        "kpsdk_present": False,
        "screenshot_path": None,
        "html_path": None,
        "navigator_path": None,
        "error": None,
    }
    try:
        kwargs = {"wait_until": "load", "timeout": NAV_TIMEOUT_MS}
        if referer:
            kwargs["referer"] = referer
        response = await page.goto(url, **kwargs)
        if response is not None:
            summary["status"] = response.status

        # Let Kasada challenge run if it's going to
        await asyncio.sleep(SETTLE_SECONDS)

        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

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

        try:
            kpsdk = await page.evaluate("() => typeof window.KPSDK !== 'undefined'")
        except Exception:
            kpsdk = False
        summary["kpsdk_present"] = bool(kpsdk)
        summary["kasada_stub_detected"] = bool(kpsdk and len(html) < 5_000)

        png_path = out_dir / "screenshot.png"
        try:
            await page.screenshot(path=str(png_path), full_page=False)
            summary["screenshot_path"] = str(png_path)
        except Exception as e:
            LOG.warning("screenshot failed: %s", e)

        try:
            argonaut_typeof = await page.evaluate("() => typeof window.ArgonautExchange")
        except Exception:
            argonaut_typeof = None
        summary["argonaut_typeof"] = argonaut_typeof
        if argonaut_typeof == "object":
            try:
                dump = await page.evaluate(
                    "() => { try { return JSON.stringify(window.ArgonautExchange); }"
                    " catch (e) { return JSON.stringify({__err: String(e)}); } }"
                )
                dump_path = out_dir / "argonaut.json"
                dump_path.write_text(dump or "", encoding="utf-8")
                summary["argonaut_dump_path"] = str(dump_path)
            except Exception as e:
                LOG.warning("argonaut dump failed: %s", e)

        try:
            next_present = await page.evaluate(
                "() => !!document.getElementById('__NEXT_DATA__')"
            )
        except Exception:
            next_present = False
        summary["next_data_present"] = bool(next_present)
        if next_present:
            try:
                nd_text = await page.evaluate(
                    "() => (document.getElementById('__NEXT_DATA__') || {}).textContent || ''"
                )
                if nd_text:
                    (out_dir / "nextdata.json").write_text(nd_text, encoding="utf-8")
            except Exception:
                pass

        nav = await capture_navigator(page)
        nav_path = out_dir / "navigator.json"
        nav_path.write_text(json.dumps(nav, indent=2, default=str), encoding="utf-8")
        summary["navigator_path"] = str(nav_path)

    except Exception as e:
        LOG.exception("probe failed for %s", url)
        summary["error"] = repr(e)
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return summary


async def run_config(name: str, kwargs: dict, special: str | None) -> dict:
    out_dir = CAPTURES_DIR / f"fp_{name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    LOG.info("=== config %s : kwargs=%s special=%s ===", name, kwargs, special)
    config_summary: dict = {
        "name": name,
        "kwargs": {k: str(v) for k, v in kwargs.items()},
        "special": special,
        "target_url": TARGET_URL,
        "result": None,
        "launch_error": None,
    }
    try:
        async with AsyncCamoufox(**kwargs) as browser:
            context = await browser.new_context()
            try:
                if special == "warmup_google":
                    # Best-effort: hit google search results page, sleep, then
                    # navigate to REA with google as the referer.
                    warm_page = await context.new_page()
                    try:
                        LOG.info("warmup: hitting google search")
                        await warm_page.goto(
                            GOOGLE_REFERRER_URL,
                            wait_until="load",
                            timeout=NAV_TIMEOUT_MS,
                        )
                        await asyncio.sleep(5.0)
                    except Exception as e:
                        LOG.warning("google warmup nav failed: %s", e)
                    finally:
                        try:
                            await warm_page.close()
                        except Exception:
                            pass
                    result = await probe_url(
                        context, TARGET_URL, out_dir, referer=GOOGLE_REFERRER_URL
                    )
                else:
                    result = await probe_url(context, TARGET_URL, out_dir)
                config_summary["result"] = result
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
    except Exception as e:
        LOG.exception("camoufox launch failed for %s", name)
        config_summary["launch_error"] = repr(e)
        config_summary["launch_traceback"] = traceback.format_exc()

    (out_dir / "summary.json").write_text(
        json.dumps(config_summary, indent=2, default=str), encoding="utf-8"
    )
    return config_summary


def print_config_summary(cs: dict) -> None:
    print("=" * 80)
    print(f"Config:             {cs['name']}")
    print(f"Kwargs:             {cs['kwargs']}")
    print(f"Special mode:       {cs['special']}")
    if cs.get("launch_error"):
        print(f"LAUNCH ERROR:       {cs['launch_error']}")
    r = cs.get("result") or {}
    print(f"Status:             {r.get('status')}")
    print(f"HTML size:          {r.get('html_size')}")
    print(f"ArgonautExchange:   {r.get('argonaut_typeof')}")
    print(f"__NEXT_DATA__:      {r.get('next_data_present')}")
    print(f"KPSDK present:      {r.get('kpsdk_present')}")
    print(f"Kasada stub:        {r.get('kasada_stub_detected')}")
    print(f"Title:              {r.get('title')!r}")
    print(f"Error:              {r.get('error')}")
    print("=" * 80, flush=True)


async def fetch_detail_after_success(name: str, kwargs: dict) -> dict | None:
    """If a config succeeds, try one detail page with the same config."""
    out_dir = CAPTURES_DIR / f"fp_{name}_detail"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pull a detail URL out of the successful argonaut dump or HTML
    search_out = CAPTURES_DIR / f"fp_{name}"
    detail_url = None
    arg_path = search_out / "argonaut.json"
    if arg_path.exists():
        try:
            raw = arg_path.read_text(encoding="utf-8")
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
        html_path = search_out / "body.html"
        if html_path.exists():
            html = html_path.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'href="(/property-[a-z0-9\-]+/[^"#?]+)"', html)
            if m:
                detail_url = "https://www.realestate.com.au" + m.group(1)

    if not detail_url:
        LOG.warning("no detail URL extractable after %s success", name)
        return None

    LOG.info("fetching detail page with same config: %s", detail_url)
    summary: dict = {
        "name": f"{name}_detail",
        "kwargs": {k: str(v) for k, v in kwargs.items()},
        "target_url": detail_url,
        "result": None,
    }
    try:
        async with AsyncCamoufox(**kwargs) as browser:
            context = await browser.new_context()
            try:
                result = await probe_url(context, detail_url, out_dir)
                summary["result"] = result
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
    except Exception as e:
        summary["launch_error"] = repr(e)

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary


async def main() -> int:
    all_results: list[dict] = []
    winner: dict | None = None

    for i, (name, kwargs, special) in enumerate(CONFIGS):
        cs = await run_config(name, kwargs, special)
        all_results.append(cs)
        print_config_summary(cs)

        r = cs.get("result") or {}
        if is_success(r):
            LOG.info("*** SUCCESS on config %s ***", name)
            winner = cs
            # Try a detail page with the same config.
            await asyncio.sleep(15.0)
            detail = await fetch_detail_after_success(name, kwargs)
            if detail:
                all_results.append(detail)
                print_config_summary(detail)
            break

        if i < len(CONFIGS) - 1:
            LOG.info(
                "sleeping %.0fs before next config (don't burst Kasada)",
                INTER_CONFIG_SLEEP_S,
            )
            await asyncio.sleep(INTER_CONFIG_SLEEP_S)

    rollup = {
        "winner": winner["name"] if winner else None,
        "configs_run": [r["name"] for r in all_results],
        "results": all_results,
    }
    (CAPTURES_DIR / "fp_rollup.json").write_text(
        json.dumps(rollup, indent=2, default=str), encoding="utf-8"
    )
    LOG.info("wrote rollup to %s", CAPTURES_DIR / "fp_rollup.json")
    LOG.info("winner: %s", winner["name"] if winner else "NONE (all configs failed)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
