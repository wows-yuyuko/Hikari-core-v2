"""用 playwright 对 11 个统一后的模板做真实渲染截图（视觉冒烟验证）。

用法: python tests/screenshot_templates.py [输出目录]
"""
import asyncio
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

from test_templates_render import CASES, _render

CHROME = (
    Path(__file__).resolve().parent.parent
    / 'tests' / 'data' / 'wows-yuyuko' / 'browsers'
    / 'chromium-1140' / 'chrome-win' / 'chrome.exe'
)

# 与 core/template_registry.py 一致的视口宽度（模板为 v5 统一风格）
VIEWPORTS = {
    'wws-ban-v5.html': 900,
    'wws-unban-v5.html': 900,
    'bind-list-v5.html': 900,
    'select-clan-v5.html': 360,
    'select-ship-v5.html': 680,
    'cw-rank-v5.html': 1300,
    'ship-rank-v5.html': 1300,
    'wws-sx-v5.html': 920,
    'wws-box-christmas-v5.html': 920,
    'wws-clan-cw-v5.html': 1200,
    'wws-clan-v5.html': 1200,
}

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / 'hikari_tpl_shots'


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        executable_path=str(CHROME),
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-web-security',
            '--allow-file-access-from-files',
        ],
        timeout=30000,
    )
    for name, data, _markers in CASES:
        html = await _render(name, data)
        tmp = OUT / f'{name}.html'
        tmp.write_text(html, encoding='utf-8')
        page = await browser.new_page(viewport={'width': VIEWPORTS.get(name, 900), 'height': 900})
        try:
            await page.goto(tmp.as_uri(), wait_until='networkidle', timeout=15000)
            await page.wait_for_timeout(300)
            shot = OUT / f'{name}.png'
            await page.screenshot(path=str(shot), full_page=True)
            print(f'OK  {shot.name}')
        except Exception as e:  # noqa: BLE001
            print(f'ERR {name}: {type(e).__name__}: {e}')
        finally:
            await page.close()
    await browser.close()
    await pw.stop()


if __name__ == '__main__':
    asyncio.run(main())
