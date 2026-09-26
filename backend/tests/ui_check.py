"""Browser check of the live dashboard (needs `python -m airframe serve` running and Microsoft Edge installed).

Clicks through every tab, runs the Part 2 and Part 3 flows through the UI, records console errors and saves screenshots.
usage: python tests/ui_check.py [out_dir] [--dark]
"""

import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8000/"
out = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "out/ui")
out.mkdir(parents=True, exist_ok=True)
dark = "--dark" in sys.argv
errors = []
EXT = Path(__file__).resolve().parent.parent / "catalog" / "extensions.json"
backup = EXT.read_bytes() if EXT.exists() else None   # the Part 3 flow adopts a synthetic entry; restore afterwards

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, color_scheme="dark" if dark else "light")
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_selector("text=Login attempts and outcomes", timeout=30000)
    page.wait_for_timeout(1500)
    sfx = "_dark" if dark else ""
    page.screenshot(path=str(out / f"1_overview{sfx}.png"), full_page=True)

    page.get_by_role("button", name="Open incident & propose fix →").click()
    page.wait_for_selector("text=What the air shows", timeout=15000)
    page.get_by_role("button", name="Explain & propose fix").click()
    page.wait_for_selector("text=The one check that confirms it", timeout=60000)
    page.get_by_role("button", name="✓ Approve").click()
    page.wait_for_selector("text=(measured live)", timeout=15000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(out / f"2_incident{sfx}.png"), full_page=True)

    page.locator("nav.tabs button", has_text="Devices").click()
    page.wait_for_selector("text=Every client seen", timeout=10000)
    page.locator("table.t tbody tr").first.click()
    page.wait_for_selector("[role=dialog] .story li", timeout=10000)
    page.wait_for_timeout(500)
    page.screenshot(path=str(out / f"3_device{sfx}.png"))
    page.keyboard.press("Escape")

    page.locator("nav.tabs button", has_text="Air & sensors").click()
    page.wait_for_selector("text=Access points × networks", timeout=10000)
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / f"4_air{sfx}.png"), full_page=True)

    page.locator("nav.tabs button", has_text="Learning").click()
    page.wait_for_selector("text=How Part 3 works", timeout=10000)
    if page.get_by_role("button", name="Draft catalog entry").count() == 0:
        page.get_by_role("button", name="Inject 25 synthetic events (reason 250)").click()
        page.wait_for_selector("button:has-text('Draft catalog entry')", timeout=15000)
    page.get_by_role("button", name="Draft catalog entry").first.click()
    page.wait_for_selector("text=Back-test:", timeout=60000)
    page.get_by_role("button", name="✓ Approve & add to catalog").first.click()
    page.wait_for_selector("text=Adopted as", timeout=15000)
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / f"5_learning{sfx}.png"), full_page=True)

    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("nav.tabs button", has_text="Overview").click()
    page.wait_for_timeout(800)
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    page.screenshot(path=str(out / f"6_mobile{sfx}.png"))
    browser.close()

if backup is None:
    EXT.unlink(missing_ok=True)
else:
    EXT.write_bytes(backup)
print("catalog/extensions.json restored (restart the server to drop the synthetic entry from memory)")
print("console errors:", errors or "none")
print("horizontal overflow on mobile:", overflow)
print("screenshots:", sorted(x.name for x in out.glob("*.png")))
