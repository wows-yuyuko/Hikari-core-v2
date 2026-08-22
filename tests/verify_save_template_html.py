"""save_template_html 功能验证脚本（不启动浏览器，auto_image=False）。

运行: python tests/verify_save_template_html.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hikari_core import Hikari_Model, output_hikari, set_hikari_config  # noqa: E402

BAN_DATA = {
    'clanInfo': {'colorRgb': '#ffffff', 'tag': 'TAG'},
    'userName': '测试玩家',
    'serverName': 'asia',
    'accountId': '12345',
    'voList': [
        {'banTime': '2024-01-01', 'banName': '***', 'userName': '测试玩家', 'banNameNamesake': 1},
    ],
}


async def main():
    cache_dir = Path(__file__).resolve().parent.parent / 'data' / 'verify_tmp'
    cache_dir.mkdir(parents=True, exist_ok=True)
    set_hikari_config(local_test=True, save_template_html=True, auto_image=False, game_path=str(cache_dir))

    hikari = Hikari_Model()
    hikari.Status = 'success'
    hikari.Output.Template = 'wws-ban-v5.html'
    hikari.Output.Data = BAN_DATA

    result = await output_hikari(hikari)

    saved = cache_dir / 'template_html' / 'wws-ban-v5.html'
    assert saved.exists(), f'未生成HTML: {saved}'
    text = saved.read_text(encoding='utf-8')
    assert '可能符合条件的历史记录' in text, 'HTML内容不完整'
    assert 'main-v5.css' in text, 'HTML缺少样式引用'
    print(f'PASS 已保存: {saved} ({len(text)} bytes)')
    print(f'      模板状态: {result.Status}')
    # 关闭开关后不再保存
    set_hikari_config(local_test=True, save_template_html=False, auto_image=False, game_path=str(cache_dir))
    saved.unlink()
    hikari2 = Hikari_Model()
    hikari2.Status = 'success'
    hikari2.Output.Template = 'wws-ban-v5.html'
    hikari2.Output.Data = BAN_DATA
    await output_hikari(hikari2)
    assert not saved.exists(), 'save_template_html=False 时不应保存'
    print('PASS 关闭开关后不再保存')


if __name__ == '__main__':
    asyncio.run(main())
