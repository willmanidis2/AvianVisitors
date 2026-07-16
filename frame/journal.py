#!/usr/bin/env python3
"""AvianVisitors frame - "journal page" layout.

An alternative to shooting the live collage: renders a quiet, book-like page
locally - a longhand date header, a 3-column grid of the day's species (one
cell each), and the day's count for each bird written in a handwriting script
at the illustration's lower right, like a collector's pencil annotation.

Enabled with `journal = true` in ~/.birdframe/config.toml. The page is
composed at the full panel size, so display.py skips its mat_and_center
recomposition in this mode. Illustrations come from the mic's cutout API;
fonts ship in fonts/ beside this file (Libre Baskerville + Caveat, both OFL).
"""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"

PANEL_W, PANEL_H = 1200, 1600
A5_H = PANEL_H * 0.7071
A5_W = A5_H / 1.41421

INK = "#1a1a1c"
COLS, MAX_ROWS = 3, 3  # cells shown before the page trails off to "& n more"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _date_line(now: datetime) -> str:
    return f"{now.strftime('%A')}, the {_ordinal(now.day)} of {now.strftime('%B')}"


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face {{ font-family:'LB'; src:url('file://{fonts}/LibreBaskerville-Regular.ttf'); }}
  @font-face {{ font-family:'LB'; font-style:italic; src:url('file://{fonts}/LibreBaskerville-Italic.ttf'); }}
  @font-face {{ font-family:'Hand'; src:url('file://{fonts}/Caveat.ttf'); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{pw}px; height:{ph}px; background:#fff; color:{ink};
         font-family:'LB', Georgia, serif; -webkit-font-smoothing:antialiased; }}
  .opening {{ position:absolute; left:{ox}px; top:{oy}px; width:{ow}px; height:{oh}px;
             padding:52px 40px 0; overflow:hidden; }}
  header {{ text-align:center; margin-bottom:64px; }}
  .eyebrow {{ font-size:14px; letter-spacing:.32em; text-transform:uppercase; }}
  .date {{ font-size:34px; font-style:italic; margin-top:16px; }}
  .grid {{ display:grid; grid-template-columns:repeat({cols}, 1fr); column-gap:36px; row-gap:52px; }}
  .cell {{ text-align:center; }}
  .imgbox {{ position:relative; height:190px; }}
  .imgbox img {{ width:100%; height:100%; object-fit:contain; }}
  .ct {{ position:absolute; right:2px; bottom:-6px; font-family:'Hand', cursive;
        font-weight:600; font-size:44px; line-height:1; transform:rotate(-4deg); }}
  .name {{ margin-top:20px; font-size:14px; letter-spacing:.18em; text-transform:uppercase; }}
  .more {{ text-align:center; font-style:italic; font-size:19px; margin-top:52px; }}
  .empty {{ text-align:center; font-style:italic; font-size:22px; margin-top:120px; }}
</style></head><body><div class="opening">
<header><div class="eyebrow">Heard Today</div><div class="date">{date}</div></header>
{body}
</div></body></html>"""


def _cell(base_url: str, sci: str, com: str, n: int) -> str:
    img = f"{base_url.rstrip('/')}/avian/api/cutout.php?sci={sci.replace(' ', '%20')}"
    count = f'<span class="ct">{n}</span>' if n > 1 else ""
    return (f'<div class="cell"><div class="imgbox"><img src="{img}">{count}</div>'
            f'<div class="name">{com}</div></div>')


def build_html(base_url: str, species: list, now: datetime | None = None) -> str:
    now = now or datetime.now()
    # oldest activity first, so the page reads top-down like the day did
    species = sorted(species, key=lambda s: s.get("last_seen", ""))
    shown = species[: COLS * MAX_ROWS]
    rest = len(species) - len(shown)
    if shown:
        cells = "".join(_cell(base_url, s["sci"], s["com"], int(s.get("n", 1))) for s in shown)
        body = f'<div class="grid">{cells}</div>'
        if rest > 0:
            body += f'<div class="more">&amp; {rest} more</div>'
    else:
        body = '<div class="empty">nothing yet today</div>'
    ox, oy = round((PANEL_W - A5_W) / 2), round((PANEL_H - A5_H) / 2)
    return PAGE.format(fonts=FONTS, pw=PANEL_W, ph=PANEL_H, ink=INK, ox=ox, oy=oy,
                       ow=round(A5_W), oh=round(A5_H), cols=COLS,
                       date=_date_line(now), body=body)


def shoot_journal(base_url: str, out: str, species: list, timeout_ms: int = 45000) -> None:
    """Render the journal page and screenshot it to `out` at panel size."""
    src = Path(os.path.expanduser(out)).with_suffix(".html")
    src.write_text(build_html(base_url, species))
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(
                viewport={"width": PANEL_W, "height": PANEL_H}).new_page()
            page.goto(f"file://{src}", wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except Exception:
                pass  # a straggling image request shouldn't sink the whole render
            page.wait_for_timeout(300)
            page.screenshot(path=str(out))
        finally:
            browser.close()
