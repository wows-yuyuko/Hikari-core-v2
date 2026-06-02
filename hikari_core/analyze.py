import html
import re
import time
import traceback
from datetime import datetime
from typing import Optional

from loguru import logger

from .command_select import select_command
from .data_source import levels, nations, servers, shiptypes
from .game.ban_search import get_BanInfo
from .game.box_check import check_christmas_box
from .game.roll import roll_ship
from .game.sx import get_sx_info
from .model import Hikari_Model
from .moudle.publicAPI import get_ship_name
from .moudle.wws_bind import change_BindInfo, delete_BindInfo, get_BindInfo, set_BindInfo, set_special_BindInfo
from .moudle.wws_clan import get_ClanInfo
from .moudle.wws_cw_recent import get_cw_recent
from .moudle.wws_cwrank import get_CwRank
from .moudle.wws_info import get_AccountInfo
from .moudle.wws_real_game import add_listen_list, delete_listen_list
from .moudle.wws_recent import get_RecentInfo
from .moudle.wws_recents import get_RecentsInfo
from .moudle.wws_ship_info import get_ShipInfo
from .moudle.wws_ship_recent import get_ShipRecent
from .moudle.wws_shiprank import get_ShipRank
from .utils import match_keywords


async def analyze_command(hikari: Hikari_Model) -> Hikari_Model:
    try:
        if hikari.Status == 'init':
            if not hikari.Input.Command_Text:
                return hikari.error('请发送wws help查看帮助')
            hikari.Input.Command_Text = html.unescape(str(hikari.Input.Command_Text)).strip()
            hikari = await extract_with_special_name(hikari)
            hikari.Function, hikari.Input.Command_List = await select_command(hikari.Input.Command_List)
            if hikari.Input.AccountName:
                hikari.Input.Command_List.insert(0, hikari.Input.AccountName)
            hikari = await extract_with_me_or_at(hikari)
            hikari = await extract_with_function(hikari)
        return hikari
    except Exception:
        logger.error(traceback.format_exc())
        return hikari.error('解析指令时发生错误，请确认输入参数无误')


async def extract_with_special_name(hikari: Hikari_Model) -> Hikari_Model:
    try:
        match = re.search(r'(\(|（)(.*?)(\)|）)', hikari.Input.Command_Text)
        if match:
            hikari.Input.AccountName = match.group(2)
            hikari.Input.Command_List = hikari.Input.Command_Text.replace(match.group(0), '').split()
        else:
            hikari.Input.Command_List = hikari.Input.Command_Text.split()
        return hikari
    except Exception:
        logger.error(traceback.format_exc())
        return hikari.error('解析指令时发生错误，请确认输入参数无误')


async def extract_with_me_or_at(hikari: Hikari_Model) -> Hikari_Model:
    try:
        if hikari.UserInfo.Platform in ['QQ', 'QQ_CHANNEL', 'QQ_OFFICIAL']:
            await _apply_qq_official_default(hikari)
            for i in hikari.Input.Command_List:
                if str(i).lower() == 'me':
                    hikari.Input.Search_Type = 1
                    hikari.Input.Platform = hikari.UserInfo.Platform
                    hikari.Input.PlatformId = hikari.UserInfo.PlatformId
                    hikari.Input.Command_List.remove(i)
                    break
                match = _match_at_mention(i, hikari.UserInfo.Platform)
                if match:
                    hikari.Input.Search_Type = 2
                    hikari.Input.Platform = hikari.UserInfo.Platform
                    hikari.Input.PlatformId = str(match.group(1))
                    hikari.Input.Command_List.remove(i)
                    break
        return hikari
    except Exception:
        logger.error(traceback.format_exc())
        return hikari.error('解析指令时发生错误，请确认输入参数无误')


async def _apply_qq_official_default(hikari: Hikari_Model) -> None:
    """在 QQ_OFFICIAL 平台，无服务器参数时默认使用 'me' 模式。"""
    if hikari.UserInfo.Platform != 'QQ_OFFICIAL':
        return
    analyze_command_list = hikari.Input.Command_List.copy()
    analyze_server, _ = await match_keywords(analyze_command_list, servers)
    if not analyze_server:
        hikari.Input.Search_Type = 1
        hikari.Input.Platform = hikari.UserInfo.Platform
        hikari.Input.PlatformId = hikari.UserInfo.PlatformId


def _match_at_mention(text: str, platform: str) -> Optional[re.Match]:
    """根据平台提取 @提及 中的用户 ID。"""
    patterns = {
        'QQ': r'CQ:at,qq=(\d+)',
        'QQ_CHANNEL': r'<@!(\d+)',
    }
    pattern = patterns.get(platform)
    return re.search(pattern, text) if pattern else None


# ============================================================
# extract_with_function 的辅助函数
# ============================================================

def _set_identity(hikari: Hikari_Model) -> None:
    """将 Platform 和 PlatformId 设置为当前用户的信息。"""
    hikari.Input.Platform = hikari.UserInfo.Platform
    hikari.Input.PlatformId = hikari.UserInfo.PlatformId


def _pop_digits_from_list(command_list: list) -> list:
    """从列表中移除并返回所有 ≤3 位的数字元素。"""
    to_delete = []
    for item in command_list:
        if str(item).isdigit() and len(str(item)) <= 3:
            to_delete.append(item)
    for item in to_delete:
        command_list.remove(item)
    return to_delete


# ============================================================
# 各功能组处理函数
# ============================================================

async def _handle_account_recent(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_AccountInfo / get_RecentInfo / get_RecentsInfo / get_ShipInfo / get_ShipRecent。"""
    hikari.Input.Recent_Date = time.strftime('%Y-%m-%d', time.localtime())

    if hikari.Function == get_RecentInfo and datetime.now().hour < 7:
        hikari.Input.Recent_Day = 1

    if hikari.Function in [get_RecentInfo, get_RecentsInfo, get_ShipRecent]:
        _extract_day_and_date_params(hikari)

    if hikari.Function in [get_AccountInfo, get_RecentInfo, get_RecentsInfo]:
        return await _parse_account_query_params(hikari)
    elif hikari.Function in [get_ShipInfo, get_ShipRecent]:
        return await _parse_ship_query_params(hikari)
    return hikari


def _extract_day_and_date_params(hikari: Hikari_Model) -> None:
    """从命令列表中提取天数或日期参数并存入 Input。"""
    to_delete = []
    for item in hikari.Input.Command_List:
        if str(item).isdigit() and len(str(item)) <= 3:
            hikari.Input.Recent_Day = int(item)
            to_delete.append(item)
        try:
            time.strptime(str(item), '%Y-%m-%d')
            hikari.Input.Recent_Date = str(item)
            to_delete.append(item)
            hikari.Input.Recent_Day = 0
        except ValueError:
            continue
    for item in to_delete:
        hikari.Input.Command_List.remove(item)


async def _parse_account_query_params(hikari: Hikari_Model) -> Hikari_Model:
    """解析 Search_Type == 3 时的 服务器 + 游戏昵称 参数。"""
    if hikari.Input.Search_Type != 3:
        return hikari
    if len(hikari.Input.Command_List) != 2:
        return hikari.error('您似乎准备用游戏昵称查询水表，请检查参数中是否包含服务器和游戏昵称，以空格分隔，顺序不限')
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if hikari.Input.Server:
        hikari.Input.AccountName = str(hikari.Input.Command_List[0])
    else:
        return hikari.error('服务器名输入错误')
    return hikari


async def _parse_ship_query_params(hikari: Hikari_Model) -> Hikari_Model:
    """解析单船查询的 服务器 + 游戏昵称 + 船名 参数。"""
    if hikari.Input.Search_Type == 3:
        if len(hikari.Input.Command_List) != 3:
            return hikari.error('您似乎准备用服务器+昵称查询单船战绩，请检查参数是否缺少或溢出，以空格分隔，顺序不限')
        hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
        if hikari.Input.Server:
            hikari.Input.AccountName = str(hikari.Input.Command_List[0])
            hikari.Input.ShipInfo.nameCn = str(hikari.Input.Command_List[1])
        else:
            return hikari.error('服务器参数输入错误')
    elif len(hikari.Input.Command_List) == 1:
        hikari.Input.ShipInfo.nameCn = str(hikari.Input.Command_List[0])
    else:
        return hikari.error('您似乎准备用me或@查询单船战绩，请检查参数是否缺少或溢出，以空格分隔，顺序不限')
    return hikari


async def _handle_bind(hikari: Hikari_Model) -> Hikari_Model:
    """处理所有绑定操作：查询 / 设置 / 特殊绑定 / 切换 / 删除。"""
    if hikari.Function == get_BindInfo:
        if hikari.Input.Search_Type not in [1, 2]:
            return hikari.error('参数似乎出了问题呢，请使用me或@群友')
        return hikari

    if hikari.Function in [set_BindInfo, set_special_BindInfo]:
        return await _handle_set_bind(hikari)

    if hikari.Function in [change_BindInfo, delete_BindInfo]:
        return await _handle_change_delete_bind(hikari)

    return hikari


async def _handle_set_bind(hikari: Hikari_Model) -> Hikari_Model:
    """处理 set_BindInfo 和 set_special_BindInfo。"""
    if hikari.Input.Search_Type != 3 and len(hikari.Input.Command_List) != 2:
        return hikari.error('参数似乎输错了呢，请确保后面跟随服务器+游戏昵称')

    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if not hikari.Input.Server:
        return hikari.error('服务器名输入错误')

    if hikari.Function == set_BindInfo:
        hikari.Input.AccountName = str(hikari.Input.Command_List[0])
    elif hikari.Function == set_special_BindInfo and hikari.Input.Command_List[0].isdigit():
        hikari.Input.AccountId = int(hikari.Input.Command_List[0])
    else:
        return hikari.error('请在网页版复制正确的特殊绑定指令，地址：https://wows.mgaia.top')

    _set_identity(hikari)
    return hikari


async def _handle_change_delete_bind(hikari: Hikari_Model) -> Hikari_Model:
    """处理 change_BindInfo 和 delete_BindInfo。"""
    if len(hikari.Input.Command_List) not in [0, 1]:
        return hikari.error('请检查是否仅输入了要切换的序号，也可为空进入选择列表')

    if len(hikari.Input.Command_List) == 1:
        digits = _pop_digits_from_list(hikari.Input.Command_List)
        if digits:
            hikari.Input.Select_Index = int(digits[0])

    _set_identity(hikari)
    return hikari


async def _handle_ban_box(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_BanInfo / get_sx_info / check_christmas_box。"""
    if hikari.Input.Search_Type != 3:
        return hikari
    if len(hikari.Input.Command_List) != 2:
        return hikari.error('您似乎准备用游戏昵称查询，请检查参数中是否包含服务器和游戏昵称，以空格分隔，顺序不限')
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if hikari.Input.Server:
        hikari.Input.AccountName = str(hikari.Input.Command_List[0])
    elif hikari.Function == get_BanInfo and hikari.Input.Server != 'cn':
        return hikari.error('服务器名输入错误,目前仅支持国服查询')
    return hikari


async def _handle_ship_name_roll(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_ship_name 和 roll_ship — 匹配国家、舰种、等级。"""
    hikari.Input.ShipInfo.country, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, nations)
    if not hikari.Input.ShipInfo.country and hikari.Function == get_ship_name:
        return hikari.error('请检查国家名是否正确')

    hikari.Input.ShipInfo.shipType, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, shiptypes)
    if not hikari.Input.ShipInfo.shipType and hikari.Function == get_ship_name:
        return hikari.error('请检查船只类别是否正确')

    hikari.Input.ShipInfo.level, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, levels)
    if not hikari.Input.ShipInfo.level and hikari.Function == get_ship_name:
        return hikari.error('请检查船只等级是否正确')
    return hikari


async def _handle_ship_rank(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_ShipRank。"""
    if len(hikari.Input.Command_List) != 2:
        return hikari.error('请检查参数中是否包含服务器和船名，以空格分隔，顺序不限')
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if hikari.Input.Server:
        hikari.Input.ShipInfo.nameCn = str(hikari.Input.Command_List[0])
    else:
        return hikari.error('服务器名输入错误')
    return hikari


async def _handle_listen_add(hikari: Hikari_Model) -> Hikari_Model:
    """处理 add_listen_list。"""
    if len(hikari.Input.Command_List) != 3:
        return hikari.error('请检查参数中是否包含服务器、游戏昵称、备注昵称，以空格分隔，顺序不限')
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if not hikari.Input.Server:
        return hikari.error('服务器名输入错误')
    hikari.Input.AccountName = str(hikari.Input.Command_List[0])
    return hikari


async def _handle_listen_delete(hikari: Hikari_Model) -> Hikari_Model:
    """处理 delete_listen_list。"""
    if len(hikari.Input.Command_List) != 1:
        return hikari.error('请检查是否仅输入了要删除的监控序号')
    if str(hikari.Input.Command_List[0]).isdigit() and len(str(hikari.Input.Command_List[0])) < 3:
        hikari.Input.Select_Index = int(hikari.Input.Command_List[0])
    else:
        return hikari.error('请确认输入序号是否正确')
    return hikari


async def _handle_clan_info(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_ClanInfo。"""
    if hikari.Input.Search_Type != 3:
        return hikari
    if len(hikari.Input.Command_List) != 2:
        return hikari.error('您似乎准备用公会TAG查询水表，请检查参数中是否包含服务器和公会TAG，以空格分隔，顺序不限')
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if hikari.Input.Server:
        hikari.Input.ClanName = str(hikari.Input.Command_List[0])
    else:
        return hikari.error('服务器名输入错误')
    return hikari


async def _handle_cw(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_CwRank 和 get_cw_recent。"""
    if hikari.Function == get_CwRank:
        return await _handle_cw_rank(hikari)
    elif hikari.Function == get_cw_recent:
        return await _handle_cw_recent(hikari)
    return hikari


async def _handle_cw_rank(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_CwRank — 服务器 + 可选赛季号。"""
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if len(hikari.Input.Command_List) == 1:
        digits = _pop_digits_from_list(hikari.Input.Command_List)
        if digits:
            hikari.Input.CwSeasonId = int(digits[0])
    elif len(hikari.Input.Command_List) > 1:
        return hikari.error('您似乎准备查询CW排行榜，请确认是否仅输入了赛季和服务器，留空为最新赛季和全服')
    return hikari


async def _handle_cw_recent(hikari: Hikari_Model) -> Hikari_Model:
    """处理 get_cw_recent — 按名称搜索或按身份搜索。"""
    if hikari.Input.Search_Type == 3:
        return await _parse_cw_recent_by_name(hikari)
    else:
        return await _parse_cw_recent_by_identity(hikari)


async def _parse_cw_recent_by_name(hikari: Hikari_Model) -> Hikari_Model:
    """通过 服务器 + 公会TAG 解析 CW 近期战绩参数。"""
    hikari.Input.Server, hikari.Input.Command_List = await match_keywords(hikari.Input.Command_List, servers)
    if not hikari.Input.Server:
        return hikari.error('服务器名输入错误')

    hikari.Input.ClanName = str(hikari.Input.Command_List[0])
    remaining = len(hikari.Input.Command_List)

    if remaining == 2:
        hikari.Input.CwSeasonId = int(hikari.Input.Command_List[1])
    elif remaining == 3:
        hikari.Input.CwSeasonId = int(hikari.Input.Command_List[1])
        hikari.Input.Recent_Day = int(hikari.Input.Command_List[2])
    else:
        return hikari.error('请检查参数中是否包含服务器、公会TAG、赛季数字、团队数字(可选)')
    return hikari


async def _parse_cw_recent_by_identity(hikari: Hikari_Model) -> Hikari_Model:
    """通过当前用户身份（me/@）解析 CW 近期战绩参数。"""
    hikari.Input.Server = hikari.UserInfo.Platform
    hikari.Input.ClanId = hikari.UserInfo.PlatformId

    remaining = len(hikari.Input.Command_List)
    if remaining == 1:
        hikari.Input.CwSeasonId = int(hikari.Input.Command_List[0])
    elif remaining == 2:
        hikari.Input.CwSeasonId = int(hikari.Input.Command_List[0])
        hikari.Input.Recent_Day = int(hikari.Input.Command_List[1])
    else:
        return hikari.error('请检查参数中是否赛季数字、团队数字(可选)')
    return hikari


# ============================================================
# 功能分发表与主分发函数
# ============================================================

_HANDLERS = {
    get_AccountInfo: _handle_account_recent,
    get_RecentInfo: _handle_account_recent,
    get_RecentsInfo: _handle_account_recent,
    get_ShipInfo: _handle_account_recent,
    get_ShipRecent: _handle_account_recent,
    get_BindInfo: _handle_bind,
    set_BindInfo: _handle_bind,
    set_special_BindInfo: _handle_bind,
    change_BindInfo: _handle_bind,
    delete_BindInfo: _handle_bind,
    get_BanInfo: _handle_ban_box,
    get_sx_info: _handle_ban_box,
    check_christmas_box: _handle_ban_box,
    get_ship_name: _handle_ship_name_roll,
    roll_ship: _handle_ship_name_roll,
    get_ShipRank: _handle_ship_rank,
    add_listen_list: _handle_listen_add,
    delete_listen_list: _handle_listen_delete,
    get_ClanInfo: _handle_clan_info,
    get_CwRank: _handle_cw,
    get_cw_recent: _handle_cw,
}


async def extract_with_function(hikari: Hikari_Model) -> Hikari_Model:
    """根据 hikari.Function 将指令分发到对应的解析处理函数。"""
    try:
        handler = _HANDLERS.get(hikari.Function)
        if handler:
            return await handler(hikari)
        return hikari
    except Exception:
        logger.error(traceback.format_exc())
        return hikari.error('解析指令时发生错误，请确认输入参数无误')
