"""渲染辅助函数。

原 ``hikari_core/data_source.py`` 的渲染辅助部分，数据常量见 ``core/constants.py``。
已移除 wows-numbers 爬虫函数（set_ShipRank_Numbers / search_accountId / search_color）
与无调用方的颜色辅助函数（select_prvalue_and_color / set_damageColor / set_winColor /
set_upinfo_color / set_clanRecord_params）。
"""

import traceback

from .constants import template_path


async def set_render_params(List):
    try:
        result = {'template_path': template_path, 'data': List}
        return result
    except Exception:
        traceback.print_exc()
