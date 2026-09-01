from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

from ..core.admin import add_admin
from ..core.config import hikari_config
from ..core.constants import servers
from ..core.model import Func
from ..features.account.info import get_AccountInfo
from ..features.account.recent import get_RecentInfo, get_RecentRandom, get_RecentRank
from ..features.account.recents import get_RecentsInfo
from ..features.account.ships import get_Ships
from ..features.api import get_ship_name
from ..features.bind import (
    change_BindInfo,
    delete_BindInfo,
    get_BindInfo,
    set_BindInfo,
    set_special_BindInfo,
    update_user_cache,
)
from ..features.clan.cw_recent import get_cw_recent
from ..features.clan.cw_rank import get_CwRank
from ..features.clan.info import get_ClanInfo
from ..features.clan.rank import get_ClanRank
from ..features.fun import check_christmas_box, get_BanInfo, get_sx_info, roll_ship
from ..features.ship.info import get_ShipInfo
from ..features.ship.rank import get_ShipRank
from ..features.ship.recent import get_ShipRecent
from ..features.system import async_update_ship_cache, async_update_template, check_version, get_help


@dataclass
class command:
    keywords: Tuple[str, ...]  # 指令字段
    func: Func = None  # 匹配到的方法，为空进入二级指令匹配
    default_func: Func = None  # 二级指令未匹配到时返回选择的默认方法
    second_select: list = None  # 二级指令列表


ship_command_list = [
    command(('recent', '近期'), get_ShipRecent),
]

recent_command_list = [
    command(('ship', '单船'), get_ShipRecent),
    command(('随机', 'random', 'pvp'), get_RecentRandom),
    command(('排位', 'rank'), get_RecentRank),
]


rank_command_list = [
    command(('ship', '单船', '战舰'), get_ShipRank),
    command(('cw', '军团战', '公会战'), get_CwRank),
    command(('clan', '军团', '公会'), get_ClanRank),
]

clan_command_list = [
    command(('rank',), get_ClanRank),
]


first_command_list = [  # 同指令中越长的匹配词越靠前；含英文别名的指令需在可能冲突的词之前
    command(('check_version', '检查更新'), check_version),
    command(('update_style', '更新样式'), async_update_template),
    command(('update_ship', '更新战舰'), async_update_ship_cache),
    # update 含于 update_ship / update_style，需排在其后
    command(('update',), update_user_cache),
    command(('change_bind', '切换绑定', '更换绑定', '更改绑定'), change_BindInfo),
    command(('bind_list', '查询绑定', '绑定查询', '绑定列表', '查绑定'), get_BindInfo),
    command(('delete_bind', '删除绑定'), delete_BindInfo),
    command(('special_bind', '特殊绑定'), set_special_BindInfo),
    # add_admin 用于添加管理员（校验串仅启动时生成一次，建议私信发送）
    command(('add_admin',), add_admin),
    # search_ship 含 'ship' 子串，需排在 ship / ship.rank 之前
    command(('search_ship', '搜船名', '查船名', '船名'), get_ship_name),
    command(('ship.rank', '单船排行榜', '战舰排行榜'), get_ShipRank),
    command(('cw.rank', '军团战排行榜', '公会战排行榜'), get_CwRank),
    command(('cw.recent', '军团战记录', '公会战记录'), get_cw_recent),
    command(('clan.rank', '军团排行榜', '公会排行榜'), get_ClanRank),
    # 近期随机/近期排位 含 'rank'/'近期' 子串，需排在 rank / recent 之前
    command(('recent_random', '近期随机', '随机近期'), get_RecentRandom),
    command(('recent_rank', '近期排位', '排位近期'), get_RecentRank),
    command(('rank', '排行榜'), None, get_ShipRank, rank_command_list),
    command(('bind', '绑定', 'set'), set_BindInfo),
    command(('recents', '单场近期'), get_RecentsInfo),
    # ships 含 'ship' 子串，需排在 ship / ship.rank 之前
    command(('ships',), get_Ships),
    command(('recent', '近期'), None, get_RecentInfo, recent_command_list),
    command(('ship', '单船'), None, get_ShipInfo, ship_command_list),
    # command(("record", "历史记录"), None, get_record),
    command(('clan', '军团', '公会'), None, get_ClanInfo, clan_command_list),
    # command(("随机表情包",), get_Random_Ocr_Pic),
    command(('roll', '随机'), roll_ship),
    command(('sx', '扫雪'), get_sx_info),
    command(('ban', '封号记录'), get_BanInfo),
    command(('box', 'sd', '圣诞船池'), check_christmas_box),
    command(('help', '帮助'), get_help),
]

# 各功能的参数用法提示（中英双语），用于指令输错时的智能提示（key 为实际执行的功能函数）
_USAGE: Dict[Func, Dict[str, str]] = {
    get_AccountInfo: {'zh': '<服务器> <游戏昵称>', 'en': '<server> <nickname>'},
    get_RecentInfo: {'zh': '[天数或日期]', 'en': '[days or date]'},
    get_RecentRandom: {'zh': '[天数或日期]', 'en': '[days or date]'},
    get_RecentRank: {'zh': '[天数或日期]', 'en': '[days or date]'},
    get_RecentsInfo: {'zh': '', 'en': ''},
    get_Ships: {'zh': '<等级/地区/类型> [min N] [max N]', 'en': '<tier/nation/type> [min N] [max N]'},
    get_ShipInfo: {'zh': '<船名>', 'en': '<ship name>'},
    get_ShipRecent: {'zh': '<船名> [天数或日期]', 'en': '<ship name> [days or date]'},
    get_ShipRank: {'zh': '<服务器> <船名>', 'en': '<server> <ship name>'},
    get_CwRank: {'zh': '[服务器] [赛季]', 'en': '[server] [season]'},
    get_cw_recent: {'zh': '<服务器> <公会TAG> [赛季] [队数]', 'en': '<server> <clan tag> [season] [team]'},
    get_ClanRank: {'zh': '<服务器> <公会TAG>', 'en': '<server> <clan tag>'},
    get_ClanInfo: {'zh': '<服务器> <公会TAG>', 'en': '<server> <clan tag>'},
    set_BindInfo: {'zh': '<服务器> <游戏昵称>', 'en': '<server> <nickname>'},
    set_special_BindInfo: {'zh': '<AID>', 'en': '<AID>'},
    add_admin: {'zh': '<32位校验串>', 'en': '<32-char token>'},
    update_user_cache: {'zh': 'me 或 <服务器> <游戏昵称>', 'en': 'me or <server> <nickname>'},
    change_BindInfo: {'zh': '[序号]', 'en': '[index]'},
    delete_BindInfo: {'zh': '<序号>', 'en': '<index>'},
    get_BindInfo: {'zh': 'me', 'en': 'me'},
    check_christmas_box: {'zh': '[服务器] [昵称] 或 me', 'en': '[server] [nickname] or me'},
    get_sx_info: {'zh': '[服务器] [昵称] 或 me', 'en': '[server] [nickname] or me'},
    get_BanInfo: {'zh': '[服务器] [昵称] 或 me', 'en': '[server] [nickname] or me'},
    get_ship_name: {'zh': '<国家> <舰种> <等级>', 'en': '<nation> <type> <tier>'},
    roll_ship: {'zh': '[国家] [舰种] [等级]', 'en': '[nation] [type] [tier]'},
    check_version: {'zh': '', 'en': ''},
    async_update_template: {'zh': '', 'en': ''},
    async_update_ship_cache: {'zh': '', 'en': ''},
    get_help: {'zh': '', 'en': ''},
}

# 相似度阈值：低于该值的指令词不进入建议列表
_SIMILARITY_THRESHOLD = 0.5

# 服务器关键词（小写），用于排除"服务器+昵称"等合法身份查询的 token
_SERVER_KEYWORDS = {kw.casefold() for m in servers for kw in m.keywords}


def _is_server_token(token) -> bool:
    return str(token).casefold() in _SERVER_KEYWORDS


def _is_identity_query(match_list) -> bool:
    """判断无指令关键词的输入是否为合法的身份查询（me / 服务器+昵称）。

    此类输入会走默认的账号查询逻辑，不应触发智能提示。
    """
    if not match_list:
        return False
    lowered = [str(t).casefold() for t in match_list]
    if lowered == ['me']:
        return True
    # 服务器+昵称：恰好两个 token 且其中一个是服务器关键词（顺序不限）
    if len(match_list) == 2 and sum(1 for t in lowered if t in _SERVER_KEYWORDS) == 1:
        return True
    return False


async def _match_level(match_list, command_List, default_func) -> Tuple[command, List, bool]:
    """匹配一层指令（大小写不敏感的子串匹配）。

    Args:
        match_list (List): 待匹配列表
        command_List (List): 匹配字符列表
        default_func (Func): 未命中时的默认功能

    Returns:
        (命中的 command, 剩余列表, 是否命中)
        未命中时返回 command(None, default_func, None)，其 func 为 default_func
    """
    for com in command_List or []:
        for kw in com.keywords or ():
            kw_l = str(kw).casefold()
            for i, match_kw in enumerate(match_list):
                mk = str(match_kw)
                idx = mk.casefold().find(kw_l)
                if idx + 1:
                    # 大小写不敏感删除命中的关键词（对齐 match_keywords）
                    match_list[i] = mk[:idx] + mk[idx + len(kw):]
                    if not match_list[i]:  # 为空时才删除，防止未加空格没有被split切割
                        match_list.remove('')
                    return com, match_list, True
    return command(None, default_func, None), match_list, False


def _flatten_entries(command_List) -> List[Tuple[Tuple[command, ...], Tuple[str, ...], Func]]:
    """将指令列表展开为 (路径, 关键词, 实际功能) 条目，包含分支默认与二级指令。"""
    entries: List[Tuple[Tuple[command, ...], Tuple[str, ...], Func]] = []
    for com in command_List or []:
        if com.func is not None:
            entries.append(((com,), com.keywords or (), com.func))
        else:
            if com.default_func is not None:
                entries.append(((com,), com.keywords or (), com.default_func))
            for sub in com.second_select or []:
                entries.append(((com, sub), sub.keywords or (), sub.func or sub.default_func))
    return entries


def _token_similarity(a, b) -> float:
    """两个指令词的相似度（0~1）。

    - 完全相同: 1.0
    - 前缀重合（用户只输入了命令前半段）: 0.5 + 0.5 * 重合长度 / 较长长度
    - 其余（错别字/漏字/英文拼写错误）: difflib 字符序列相似度
    """
    a, b = str(a).casefold(), str(b).casefold()
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    if common > 0:
        return 0.5 + 0.5 * common / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


def _suggest(match_list, command_List) -> List[dict]:
    """对未匹配的 token 列表计算相似命令建议。

    规则：
    - 服务器关键词（如 亚服/asia）等合法身份查询 token 不参与相似度匹配；
    - 每个条目取与任一 token 的最高相似度，低于阈值的剔除；
    - 相同实际功能的条目只保留相似度最高的一条（command_suggest_dedupe 可关闭）；
    - 数量上限 command_suggest_max（设为 0 则关闭智能提示）。

    Returns:
        建议列表，每项 {'path': (command...), 'handler': Func, 'score': float, 'kw': 命中的关键词}
    """
    if not match_list or hikari_config.command_suggest_max <= 0:
        return []
    scored = []
    for path, keywords, handler in _flatten_entries(command_List):
        best, best_kw = 0.0, None
        for kw in keywords:
            for token in match_list:
                if _is_server_token(token):
                    continue
                s = _token_similarity(token, kw)
                if s > best:
                    best, best_kw = s, kw
        if best >= _SIMILARITY_THRESHOLD:
            scored.append({'path': path, 'handler': handler, 'score': best, 'kw': best_kw})
    # 相似度降序，路径短的优先（二级指令路径更长，同等分时优先一级）
    scored.sort(key=lambda e: (-e['score'], len(e['path'])))
    if hikari_config.command_suggest_dedupe:
        deduped, seen = [], set()
        for e in scored:
            if e['handler'] in seen:
                continue
            seen.add(e['handler'])
            deduped.append(e)
        scored = deduped
    return scored[: hikari_config.command_suggest_max]


def _display_alias(com, kw) -> str:
    """按当前语言选择展示用的指令别名。

    - 英文模式：优先展示该指令的第一个英文别名（如 ship / rank / monitor_list）；
    - 中文模式：展示命中的别名（如输入 单传 提示 单船）。
    """
    if hikari_config.command_language == 'en':
        for k in com.keywords or ():
            if str(k).isascii():
                return k
    if kw and kw in (com.keywords or ()):
        return kw
    return com.keywords[0] if com.keywords else ''


def render_suggest_message(suggestions: List[dict]) -> str:
    """将建议列表渲染为提示文案（按 command_language 输出中/英文）。"""
    is_en = hikari_config.command_language == 'en'
    lines = []
    for item in suggestions:
        words = [_display_alias(com, item.get('kw')) for com in item['path']]
        usage = (_USAGE.get(item['handler'], {}) or {}).get('en' if is_en else 'zh', '')
        line = 'wws ' + ' '.join(w for w in words if w)
        if usage:
            line += ' ' + usage
        lines.append(line)
    cap = hikari_config.command_suggest_max
    if is_en:
        head = f'Unrecognized command. Did you mean (max {cap} shown):\n'
        tail = '\nMore help: send "wws help"'
    else:
        head = f'未识别的指令，你是不是想输入（最多显示 {cap} 条）：\n'
        tail = '\n更多帮助请发送：wws help'
    return head + '\n'.join('  ' + l for l in lines) + tail


async def route_command(search_list) -> Tuple[Func, List, List[dict]]:
    """带智能提示的指令路由。

    与 select_command 行为一致，但未匹配到指令时额外返回相似命令建议列表
    （每项 {'path': ..., 'handler': ..., 'score': ..., 'kw': ...}），
    供上层生成"你是不是想输入"提示。

    Returns:
        (匹配到的功能函数, 剩余参数列表, 建议列表)
    """
    suggestions: List[dict] = []
    first, search_list, first_matched = await _match_level(search_list, first_command_list, get_AccountInfo)
    if first_matched and first.func is None:
        if first.second_select:
            sub, search_list, sub_matched = await _match_level(search_list, first.second_select, first.default_func)
            if not sub_matched:
                # 二级指令未命中：对剩余 token 计算该指令分支下的子命令建议，
                # 效果与分支兜底功能相同的建议无意义，剔除
                suggestions = [
                    s for s in _suggest(search_list, first.second_select)
                    if s['handler'] != first.default_func
                ]
            return sub.func, search_list, suggestions
        return first.default_func, search_list, []
    if not first_matched:
        # 一级完全未命中：合法身份查询（me/@/服务器+昵称）不触发智能提示
        if not _is_identity_query(search_list):
            suggestions = _suggest(search_list, first_command_list)
    return first.func, search_list, suggestions


async def select_command(search_list) -> Tuple[Func, List]:
    """兼容原签名：仅返回 (功能函数, 剩余参数列表)。"""
    func, search_list, _ = await route_command(search_list)
    return func, search_list
