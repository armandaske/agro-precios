"""
Playwright-based scraper for the SIAP "Cierre de la producción agrícola" page.

This script automates the process of downloading the Excel report for a
specified year and crop without relying on Selenium.  Playwright
provides a lightweight, modern alternative for controlling a headless
browser and capturing downloads.

Example usage:

    python scraper_cierre_agricola_playwright.py --year 2024 --crop "Aguacate"

Dependencies:
    • playwright (install via `pip install playwright`) and the appropriate
      browser binaries (install with `playwright install` once).

On the first run you must install the browser engines:

    from playwright.sync_api import sync_playwright
    sync_playwright().start()
    # or run `playwright install chromium` from the command line.

The script waits for the report to download and saves it into the
directory specified by `--download-dir` (defaults to `downloads`).
"""

import argparse
import asyncio
import os
from playwright.async_api import async_playwright


async def download_cierre_agricola(year: int | str, crop: str, download_dir: str = "downloads") -> str:
    """Download the agricultural production Excel report using Playwright.

    Args:
        year: Year to filter by (e.g. 2024).
        crop: Visible text of the crop in the drop‑down list.
        download_dir: Directory where the Excel file should be saved.

    Returns:
        The absolute path to the downloaded Excel file.
    """
    os.makedirs(download_dir, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        await page.goto("https://nube.agricultura.gob.mx/cierre_agricola/")

        # Wait for the year drop‑down to have options and select the desired year
        await page.wait_for_selector("#anioagric option")
        await page.select_option("#anioagric", label=str(year))

        # Wait for the crop list to populate (more than one option) and select crop
        await page.wait_for_selector("#cultivo option:nth-child(2)")
        await page.select_option("#cultivo", label=crop)

        # Click the "Consultar" button to load the results
        await page.click("#Consultar")
        # Wait for results area to appear
        await page.wait_for_selector("#Resultado")

        # Trigger download by clicking the "Generar" button
        async with page.expect_download() as download_info:
            await page.click("#Excel")
        download = await download_info.value
        # Save the file to the specified directory
        file_path = os.path.join(download_dir, download.suggested_filename)
        await download.save_as(file_path)

        await context.close()
        await browser.close()
        return os.path.abspath(file_path)


async def main_async(year: int | str, crop: str, download_dir: str = "downloads") -> None:
    path = await download_cierre_agricola(year, crop, download_dir)
    print(f"Downloaded report saved to: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download agricultural production reports via Playwright.")
    parser.add_argument("--year", required=True, help="Year to download (e.g., 2024)")
    parser.add_argument("--crop", required=True, help="Crop name as it appears in the drop‑down list.")
    parser.add_argument(
        "--download-dir", default="downloads", help="Directory to save the downloaded file."
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.year, args.crop, args.download_dir))


if __name__ == "__main__":
    main()