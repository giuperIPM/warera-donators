import argparse
import asyncio
import base64
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from playwright.async_api import Error as BrowserError
from playwright.async_api import async_playwright
from pydantic import ValidationError

from .domain import RankingError, WeeklyRanking
from .memberships import load_confindustria_members


def italian_number(value: Decimal | None, places: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:,.{places}f}".translate(str.maketrans({",": ".", ".": ","}))


async def load_avatar(http: httpx.AsyncClient, url: str | None) -> str | None:
    if not url or not url.startswith(("https://", "http://")):
        return None
    try:
        async with http.stream("GET", url) as response:
            response.raise_for_status()
            media_type = response.headers.get("content-type", "").split(";")[0].strip()
            if media_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                return None
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > 2_000_000:
                    return None
            return f"data:{media_type};base64,{base64.b64encode(content).decode()}"
    except httpx.HTTPError:
        return None


def render_html(ranking: WeeklyRanking, avatars: dict[str, str | None]) -> str:
    environment = Environment(
        loader=PackageLoader("warera_rankings", "templates"),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    environment.filters["number"] = italian_number
    return environment.get_template("weekly.html").render(
        ranking=ranking,
        avatars=avatars,
        confindustria_members=load_confindustria_members(),
        last_day=ranking.week_end - timedelta(days=1),
    )


async def render_image(ranking: WeeklyRanking, target: Path) -> Path:
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as http:
        avatars = await asyncio.gather(*(load_avatar(http, row.avatar_url) for row in ranking.rows))
    html = render_html(
        ranking, dict(zip((row.player_id for row in ranking.rows), avatars, strict=True))
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".png", delete=False) as file:
            temporary = Path(file.name)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(
                    viewport={"width": 1200, "height": 900},
                    device_scale_factor=1,
                    java_script_enabled=False,
                )
                await page.route("**/*", lambda route: route.abort())
                await page.set_content(html, wait_until="load")
                await page.evaluate("""async () => {
                    await document.fonts.ready;
                    await Promise.all([...document.images].map(async img => {
                        try { await img.decode(); } catch { img.remove(); }
                    }));
                }""")
                await page.locator("main").screenshot(path=temporary, type="png")
            finally:
                await browser.close()
        temporary.replace(target)
    except BrowserError as error:
        raise RankingError(
            "Generazione PNG fallita: verificare Chromium con python -m playwright install chromium"
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera il PNG da una classifica JSON salvata")
    parser.add_argument("json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        ranking = WeeklyRanking.model_validate_json(args.json.read_text(encoding="utf-8"))
        target = asyncio.run(render_image(ranking, args.output or args.json.with_suffix(".png")))
    except (RankingError, ValidationError, OSError) as error:
        parser.exit(1, f"Errore: {error}\n")
    print(target)


if __name__ == "__main__":
    main()
