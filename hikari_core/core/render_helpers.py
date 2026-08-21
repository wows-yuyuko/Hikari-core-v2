"""渲染辅助函数（PR 颜色等）。

原 ``hikari_core/data_source.py`` 的渲染辅助部分，数据常量见 ``core/constants.py``。
已移除 wows-numbers 爬虫相关函数（set_ShipRank_Numbers / search_accountId / search_color）。
"""

import traceback

from .constants import color_data, pr_select, template_path


async def set_render_params(List):
    try:
        result = {'template_path': template_path, 'data': List}
        return result
    except Exception:
        traceback.print_exc()


async def select_prvalue_and_color(pr):
    describe, color = None, None
    if pr:
        for select in pr_select:
            if pr > select['value']:
                describe = select['name']
                color = select['color']
    return describe, color


async def set_clanRecord_params():
    return


async def set_damageColor(type, value):
    try:
        if type == 'Destroyer':
            if not value or value < 33000:
                return color_data['Bad']
            elif value < 40000:
                return color_data['Good']
            elif value < 55000:
                return color_data['Great']
            elif value < 64000:
                return color_data['Unicum']
            else:
                return color_data['Super Unicum']
        elif type == 'Cruiser':
            if not value or value < 47000:
                return color_data['Bad']
            elif value < 55000:
                return color_data['Good']
            elif value < 83000:
                return color_data['Great']
            elif value < 95000:
                return color_data['Unicum']
            else:
                return color_data['Super Unicum']
        elif type == 'AirCarrier':
            if not value or value < 60000:
                return color_data['Bad']
            elif value < 71000:
                return color_data['Good']
            elif value < 84000:
                return color_data['Great']
            elif value < 113000:
                return color_data['Unicum']
            else:
                return color_data['Super Unicum']
        elif type == 'BattleShip':
            if not value or value < 64000:
                return color_data['Bad']
            elif value < 72000:
                return color_data['Good']
            elif value < 97000:
                return color_data['Great']
            elif value < 108000:
                return color_data['Unicum']
            else:
                return color_data['Super Unicum']
    except Exception:
        traceback.print_exc()
        return None


async def set_winColor(value):
    try:
        if not value or value < 45:
            return color_data['Bad']
        elif value < 50:
            return color_data['Below Average']
        elif value < 55:
            return color_data['Average']
        elif value < 60:
            return color_data['Good']
        elif value < 65:
            return color_data['Great']
        elif value < 70:
            return color_data['Unicum']
        else:
            return color_data['Super Unicum']
    except Exception:
        traceback.print_exc()
        return None


async def set_upinfo_color(value):
    try:
        if not value or value < 0:
            return color_data['Bad']
        elif value > 0:
            return color_data['Good']
        else:
            return None
    except Exception:
        traceback.print_exc()
        return None
