import asyncio
import base64
import struct
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from playwright.async_api import Error as BrowserError
from playwright.async_api import Page, async_playwright

from warera_rankings.domain import RankingError, RankingRow, WeeklyRanking
from warera_rankings.image import italian_number, load_avatar, render_html, render_image
from warera_rankings.job import export


@pytest.fixture(autouse=True)
def membership_source(monkeypatch):
    async def members(http):
        return frozenset({"69e60890fe61f8ad03b860ba"})

    monkeypatch.setattr("warera_rankings.image.load_confindustria_members", members)


@pytest.fixture
def ranking():
    return WeeklyRanking(
        week_start=datetime(2026, 9, 28, tzinfo=UTC),
        week_end=datetime(2026, 10, 5, tzinfo=UTC),
        donations_until=datetime(2026, 10, 5, tzinfo=UTC),
        generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        wealth_observed_at=datetime(2026, 10, 5, tzinfo=UTC),
        coverage="week_boundary_reached",
        donor_count=170,
        candidate_count=50,
        donation_count=587,
        donated_total="13963.859",
        rows=[
            RankingRow(
                position=position,
                player_id=f"player-{position}",
                username="Player con un nome molto lungo " * 3 if position == 1 else "Alice",
                avatar_url=None,
                level=26,
                donated="123.456",
                donation_count=2,
                wealth_total="1200",
                company_value="200",
                wealth_without_companies="1000",
                ratio_percent="12.346",
            )
            for position in range(1, 11)
        ],
    )


def test_template_preserves_order_formats_numbers_and_escapes_names(ranking):
    ranking.rows[0].username = '<script>alert("x")</script>'
    html = render_html(ranking, {}, frozenset())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "12,346%" in html
    assert "Livello 26" in html
    assert "28.09.2026 — 04.10.2026" in html
    assert html.index("&lt;script&gt;") < html.index("Alice")
    assert "RISULTATO PROVVISORIO" not in html


def test_empty_and_provisional_ranking_is_explicit(ranking):
    ranking.rows = []
    ranking.coverage = "history_unverified"
    html = render_html(ranking, {}, frozenset())
    assert "Nessun player con rapporto calcolabile" in html
    assert "RISULTATO PROVVISORIO" in html
    assert italian_number(None) == "—"
    assert italian_number(Decimal("1000.1")) == "1.000,100"


@pytest.mark.parametrize("scenario", ["valid", "http-error", "timeout", "html", "too-large"])
def test_avatar_download_is_bounded_and_failures_use_fallback(scenario):
    def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(
            404 if scenario == "http-error" else 200,
            headers={"content-type": "text/html" if scenario == "html" else "image/png"},
            content=b"x" * 2_000_001 if scenario == "too-large" else b"avatar",
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            assert await load_avatar(http, None) is None
            assert await load_avatar(http, "file:///etc/passwd") is None
            avatar = await load_avatar(http, "https://example.test/avatar.png")
            if scenario == "valid":
                assert avatar == "data:image/png;base64,YXZhdGFy"
            else:
                assert avatar is None

    asyncio.run(check())


def test_chromium_renders_png_without_clipping(ranking, tmp_path):
    ranking.rows[0].player_id = "69e60890fe61f8ad03b860ba"
    ranking.rows[1].username = "Giancarlo_Devasini"

    async def check():
        target = await render_image(ranking, tmp_path / "ranking.png")
        png = target.read_bytes()
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        assert width == 1200
        assert height > 1000
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": 1200, "height": 900})
                await page.set_content(
                    render_html(ranking, {}, frozenset({"69e60890fe61f8ad03b860ba"}))
                )
                assert await page.locator("tbody tr").count() == 10
                names = page.locator(".username")
                gold = await page.locator(".edition").evaluate("el => getComputedStyle(el).color")
                assert await names.nth(0).evaluate("el => getComputedStyle(el).color") == gold
                assert await names.nth(1).evaluate("el => getComputedStyle(el).color") == (
                    "rgb(238, 243, 248)"
                )
                assert await page.evaluate("document.documentElement.scrollWidth") == 1200
                for cell in await page.locator("td").all():
                    bounds = await cell.bounding_box()
                    assert bounds["x"] >= 0
                    assert bounds["x"] + bounds["width"] <= 1200
            finally:
                await browser.close()
        assert list(tmp_path.iterdir()) == [target]

    asyncio.run(check())


def test_failed_screenshot_preserves_previous_png(ranking, tmp_path, monkeypatch):
    target = tmp_path / "ranking.png"
    target.write_bytes(b"previous")

    async def fail(*args, **kwargs):
        raise BrowserError("screenshot failed")

    monkeypatch.setattr("playwright.async_api.Locator.screenshot", fail)
    with pytest.raises(RankingError, match="Generazione PNG"):
        asyncio.run(render_image(ranking, target))
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


def test_broken_image_content_falls_back_to_initial(ranking, tmp_path, monkeypatch):
    ranking.rows[0].avatar_url = "https://example.test/broken.png"
    invalid_avatar = "data:image/png;base64," + base64.b64encode(b"broken").decode()

    async def avatar(*args):
        return invalid_avatar

    original = Page.evaluate

    async def evaluate(page, expression, *args, **kwargs):
        result = await original(page, expression, *args, **kwargs)
        assert await original(page, "document.images.length") == 0
        return result

    monkeypatch.setattr("warera_rankings.image.load_avatar", avatar)
    monkeypatch.setattr(Page, "evaluate", evaluate)
    asyncio.run(render_image(ranking, tmp_path / "ranking.png"))


def test_image_command_renders_empty_ranking_without_changing_json(ranking, tmp_path, monkeypatch):
    from warera_rankings.image import main

    ranking.rows = []
    source = export(ranking, tmp_path)
    original = source.read_bytes()
    target = tmp_path / "custom.png"
    monkeypatch.delenv("WARERA_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["warera-ranking-image", str(source), "--output", str(target)])
    main()
    assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert source.read_bytes() == original


def test_membership_failure_generates_new_png_with_white_names(ranking, tmp_path, monkeypatch):
    from warera_rankings.memberships import load_confindustria_members

    ranking.rows[0].player_id = "69e60890fe61f8ad03b860ba"
    target = tmp_path / "ranking.png"
    target.write_bytes(b"previous")
    client_type = httpx.AsyncClient
    original_evaluate = Page.evaluate

    def client(**kwargs):
        return client_type(
            transport=httpx.MockTransport(lambda request: httpx.Response(503)), **kwargs
        )

    async def evaluate(page, expression, *args, **kwargs):
        result = await original_evaluate(page, expression, *args, **kwargs)
        colors = await original_evaluate(
            page,
            "[...document.querySelectorAll('.username')].map(el => getComputedStyle(el).color)",
        )
        assert colors == ["rgb(238, 243, 248)"] * len(ranking.rows)
        return result

    monkeypatch.setattr("warera_rankings.image.httpx.AsyncClient", client)
    monkeypatch.setattr(
        "warera_rankings.image.load_confindustria_members", load_confindustria_members
    )
    monkeypatch.setattr(Page, "evaluate", evaluate)
    asyncio.run(render_image(ranking, target))
    assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert list(tmp_path.iterdir()) == [target]
