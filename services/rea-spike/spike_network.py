"""Companion probe: record all network traffic during a single REA homepage
visit to confirm whether the Kasada challenge JS (ips.js) is fetched and
what response it gets.
"""

import asyncio
import json
import logging
from pathlib import Path

from camoufox import AsyncCamoufox

LOG = logging.getLogger("rea-spike-network")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CAPTURES_DIR = Path(__file__).parent / "captures"
CAPTURES_DIR.mkdir(exist_ok=True)


async def main() -> int:
    requests_log: list[dict] = []
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        def on_request(req):
            requests_log.append({
                "phase": "request",
                "method": req.method,
                "url": req.url,
                "resource_type": req.resource_type,
            })

        async def on_response(resp):
            try:
                requests_log.append({
                    "phase": "response",
                    "status": resp.status,
                    "url": resp.url,
                    "headers_subset": {
                        k: resp.headers.get(k)
                        for k in (
                            "content-type",
                            "x-kpsdk-ct",
                            "x-kpsdk-cd",
                            "set-cookie",
                            "server",
                            "cf-ray",
                        )
                        if resp.headers.get(k)
                    },
                })
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        try:
            LOG.info("navigating to REA homepage")
            try:
                resp = await page.goto(
                    "https://www.realestate.com.au/",
                    wait_until="load",
                    timeout=60_000,
                )
                LOG.info("initial status=%s", resp.status if resp else None)
            except Exception as e:
                LOG.warning("nav errored: %s", e)
            # Sit for a long time letting any reload/poll happen
            for i in range(12):
                await asyncio.sleep(2.5)
                html_len = await page.evaluate(
                    "() => (document.documentElement.outerHTML || '').length"
                )
                title = await page.title()
                LOG.info("t+%.1fs html_len=%d title=%r", (i + 1) * 2.5, html_len, title)
                if html_len > 20000:
                    LOG.info("page expanded; breaking")
                    break
            final_html = await page.content()
            (CAPTURES_DIR / "network_final.html").write_text(final_html, encoding="utf-8")
            await page.screenshot(path=str(CAPTURES_DIR / "network_final.png"))
        finally:
            await page.close()
            await context.close()

    (CAPTURES_DIR / "network_log.json").write_text(
        json.dumps(requests_log, indent=2), encoding="utf-8"
    )
    LOG.info("captured %d network events", len(requests_log))
    # Print summary
    statuses: dict[int, int] = {}
    for ev in requests_log:
        if ev["phase"] == "response":
            s = ev["status"]
            statuses[s] = statuses.get(s, 0) + 1
    print("Status counts:", statuses)
    for ev in requests_log:
        if ev["phase"] == "response" and "ips.js" in ev["url"]:
            print("IPS.JS response:", ev["status"], ev["url"])
        if ev["phase"] == "response" and ev["status"] in (403, 429):
            print("BLOCK:", ev["status"], ev["url"])
    return 0


if __name__ == "__main__":
    asyncio.run(main())
