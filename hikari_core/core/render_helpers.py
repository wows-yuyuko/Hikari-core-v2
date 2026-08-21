"""渲染辅助函数（PR 颜色、排行榜解析等）。

原 ``hikari_core/data_source.py`` 的渲染辅助部分，数据常量见 ``core/constants.py``。
"""

import re
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


async def set_ShipRank_Numbers(data, server, shipId):
    try:
        info_list = []
        for each in data:
            index = int(each.select('td')[0].string)
            clan_name = each.select('td[style="text-align: left;  "] a')
            if len(clan_name) > 1:
                tag = clan_name[0].string.replace('[', '').replace(']', '')
                userName = clan_name[1].string
                url = clan_name[1].attrs['href']
            else:
                tag = None
                userName = clan_name[0].string
                url = clan_name[0].attrs['href']
            accountId = await search_accountId(url)
            battles = int(each.select('td span')[0].string.replace(' ', ''))
            pr = int(each.select('td span')[1].string.replace(' ', ''))
            prColor = await search_color(each.select('td span')[1].attrs['style'])
            wins = float(each.select('td span')[2].string.replace('%', ''))
            winsColor = await search_color(each.select('td span')[2].attrs['style'])
            frags = float(each.select('td span')[3].string)
            fragsColor = await search_color(each.select('td span')[3].attrs['style'])
            maxFrags = int(each.select('td span')[4].string)
            damage = int(each.select('td span')[5].string.replace(' ', ''))
            damageColor = await search_color(each.select('td span')[5].attrs['style'])
            maxDamage = int(each.select('td span')[6].string.replace(' ', ''))
            xp = int(each.select('td span')[7].string.replace(' ', ''))
            maxXp = int(each.select('td span')[8].string.replace(' ', ''))
            # planesDestroyed = float(each.select('td span')[9].string)
            # planesDestroyedColor = await search_color(each.select('td span')[9].attrs['style'])
            # maxPlanesDestroyed = int(each.select('td span')[10].string)
            info = {
                'accountId': accountId,
                'battles': battles,
                'damage': damage,
                'damageColor': damageColor,
                'frags': frags,
                'fragsColor': fragsColor,
                'index': index,
                'maxDamage': maxDamage,
                'maxFrags': maxFrags,
                'maxXp': maxXp,
                'pr': pr,
                'prColor': prColor,
                'server': server,
                'shipId': shipId,
                'wins': wins,
                'winsColor': winsColor,
                'xp': xp,
                'tag': tag,
                'userName': userName,
            }
            info_list.append(info)
        return info_list

    except Exception:
        traceback.print_exc()
        return None


async def set_clanRecord_params():
    return


async def search_accountId(str):
    try:
        match = re.search(r'/player/(.*?),', str)
        if match:
            return int(match.group(1).strip())
        else:
            return None
    except Exception:
        traceback.print_exc()
        return None


async def search_color(str):
    try:
        match = re.search(r'color:(.*?);', str)
        if match:
            return match.group(1).strip()
        else:
            return None
    except Exception:
        traceback.print_exc()
        return None


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
