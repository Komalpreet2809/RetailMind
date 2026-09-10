"""
RetailMind :: overflow audit.

Walks every page, opens every expander, and reports any element whose content is
larger than its box while its overflow is hidden or clipped -- i.e. content a
reader can see part of and can never reach the rest of.

This exists because three separate versions of the stylesheet silently cut
content: EXPLAIN plans clipped inside expanders, month labels sliced in half at
the bottom of a chart card, and dataframes with their scrollbars removed. Eyeballing
a screenshot found two of those and missed the third, so the check is automated.

  python scripts/audit_overflow.py [base_url] [width]
"""

import asyncio
import sys

PAGES = ["/", "/segments", "/retention", "/campaigns", "/query_lab", "/plan_doctor"]

PROBE = """
() => {
  const bad = [];
  const clips = new Set(['hidden', 'clip']);
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 12) return;

    const overX = el.scrollWidth  - el.clientWidth;
    const overY = el.scrollHeight - el.clientHeight;
    const hidX = clips.has(cs.overflowX);
    const hidY = clips.has(cs.overflowY);
    if ((overX > 2 && hidX) || (overY > 2 && hidY)) {
      // A parent that scrolls makes this reachable, so it is not a defect.
      let p = el.parentElement, rescued = false;
      while (p && p !== document.body) {
        const ps = getComputedStyle(p);
        if (['auto','scroll'].includes(ps.overflowX) || ['auto','scroll'].includes(ps.overflowY)) {
          rescued = true; break;
        }
        p = p.parentElement;
      }
      if (rescued) return;
      bad.push({
        tag: el.tagName.toLowerCase(),
        testid: el.getAttribute('data-testid') || '',
        cls: (el.className || '').toString().slice(0, 40),
        overX: overX > 2 ? overX : 0,
        overY: overY > 2 ? overY : 0,
        text: (el.textContent || '').trim().slice(0, 48),
      });
    }
  });
  // Deduplicate: a clipped ancestor reports the same text as its child.
  const seen = new Set();
  return bad.filter(b => {
    const k = b.testid + '|' + b.overX + '|' + b.overY + '|' + b.text;
    if (seen.has(k)) return false;
    seen.add(k); return true;
  });
}
"""


async def main():
    from playwright.async_api import async_playwright

    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8519"
    widths = [int(w) for w in (sys.argv[2:] or [1440, 1100, 900])]

    total = 0
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for width in widths:
            print(f"\n=== {width}px " + "=" * 40)
            for path in PAGES:
                pg = await b.new_page(viewport={"width": width, "height": 950})
                await pg.goto(base + path, wait_until="networkidle", timeout=300000)
                await pg.wait_for_timeout(14000)

                # Expanders hide most of the wide content on this site.
                for _ in range(2):
                    for sm in await pg.query_selector_all('[data-testid="stExpander"] summary'):
                        try:
                            await sm.click(timeout=2500)
                        except Exception:
                            pass
                    await pg.wait_for_timeout(1200)
                await pg.wait_for_timeout(2500)

                bad = await pg.evaluate(PROBE)
                hscroll = await pg.evaluate(
                    "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                total += len(bad)
                mark = "OK " if not bad and hscroll <= 0 else "!! "
                print(f"  {mark}{path:14s} clipped={len(bad):<3} page-h-scroll={hscroll}px")
                for x in bad[:6]:
                    print(f"       {x['testid'] or x['tag']:26s} "
                          f"x+{x['overX']:<5} y+{x['overY']:<5} {x['text'][:40]!r}")
                await pg.close()
        await b.close()

    print(f"\n  {'PASS - nothing clipped' if total == 0 else f'FAIL - {total} clipped elements'}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
