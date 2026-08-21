import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Protocol, Tuple, runtime_checkable

from .config import hikari_config
from .data_source import servers
from .game.ban_search import get_BanInfo
from .game.box_check import check_christmas_box
from .game.help import async_update_template, check_version, get_help, async_update_ship_cache

# from .game.ocr import get_Random_Ocr_Pic
from .game.roll import roll_ship
from .game.sx import get_sx_info
from .moudle.publicAPI import get_ship_name
from .moudle.wws_bind import change_BindInfo, delete_BindInfo, get_BindInfo, set_BindInfo, set_special_BindInfo
from .moudle.wws_clan import get_ClanInfo
from .moudle.wws_clanrank import get_ClanRank
from .moudle.wws_cwrank import get_CwRank
from .moudle.wws_cw_recent import get_cw_recent
from .moudle.wws_info import get_AccountInfo
from .moudle.wws_real_game import add_listen_list, delete_listen_list, get_diff_ship, get_listen_list, reset_config
from .moudle.wws_recent import get_RecentInfo
from .moudle.wws_recents import get_RecentsInfo

# from .moudle.wws_record import get_record
from .moudle.wws_ship_info import get_ShipInfo
from .moudle.wws_ship_recent import get_ShipRecent
from .moudle.wws_shiprank import get_ShipRank


@runtime_checkable
class Func(Protocol):
    async def __call__(self, **kwargs):
        ...


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
]


rank_command_list = [
    command(('ship', '单船', '战舰'), get_ShipRank),
    command(('cw', '军团战', '公会战'), get_CwRank),
    command(('clan', '军团', '公会'), get_ClanRank),
]

clan_command_list = [
    command(('rank',), get_ClanRank),
]


first_command_list = [  # 同指令中越长的匹配词越靠前
    command(('check_version', '检查更新'), check_version),
    command(('更新样式',), async_update_template),
    command(('更新战舰',), async_update_ship_cache),
    command(('查询监控', '监控列表', '查询监听', '监听列表'), get_listen_list),
    command(('测试监控',), get_diff_ship),
    command(('添加监控',), add_listen_list),
    command(('删除监控',), delete_listen_list),
    command(('重置监控',), reset_config),
    command(('切换绑定', '更换绑定', '更改绑定'), change_BindInfo),
    command(('查询绑定', '绑定查询', '绑定列表', '查绑定'), get_BindInfo),
    command(('删除绑定',), delete_BindInfo),
    command(('特殊绑定',), set_special_BindInfo),
    command(('ship.rank', '单船排行榜', '战舰排行榜'), get_ShipRank),
    command(('cw.rank', '军团战排行榜', '公会战排行榜'), get_CwRank),
    command(('cw.recent', '军团战记录', '公会战记录'), get_cw_recent),
    command(('clan.rank', '军团排行榜', '公会排行榜'), get_ClanRank),
    command(('rank', '排行榜'), None, get_ShipRank, rank_command_list),
    command(('bind', '绑定', 'set'), set_BindInfo),
    command(('recents', '单场近期'), get_RecentsInfo),
    command(('recent', '近期'), None, get_RecentInfo, recent_command_list),
    command(('ship', '单船'), None, get_ShipInfo, ship_command_list),
    # command(("record", "历史记录"), None, get_record),
    command(('clan', '军团', '公会'), None, get_ClanInfo, clan_command_list),
    # command(("随机表情包",), get_Random_Ocr_Pic),
    command(('roll', '随机'), roll_ship),
    command(('sx', '扫雪'), get_sx_info),
    command(('ban', '封号记录'), get_BanInfo),
    command(('box', 'sd', '圣诞船池'), check_christmas_box),
    command(('搜船名', '查船名', '船名'), get_ship_name),
    command(('help', '帮助'), get_help),
]

# 各功能的参数用法提示，用于指令输错时的智能提示（key 为实际执行的功能函数）
_USAGE: Dict[Func, str] = {
    get_AccountInfo: '<服务器> <游戏昵称>',
    get_RecentInfo: '[天数或日期]',
    get_RecentsInfo: '',
    get_ShipInfo: '<船名>',
    get_ShipRecent: '<船名> [天数或日期]',
    get_ShipRank: '<服务器> <船名>',
    get_CwRank: '[服务器] [赛季]',
    get_cw_recent: '<服务器> <公会TAG> [赛季] [队数]',
    get_ClanRank: '<服务器> <公会TAG>',
    get_ClanInfo: '<服务器> <公会TAG>',
    set_BindInfo: '<服务器> <游戏昵称>',
    set_special_BindInfo: '<AID>',
    change_BindInfo: '[序号]',
    delete_BindInfo: '<序号>',
    get_BindInfo: 'me 或 @群友',
    check_christmas_box: '[服务器] [昵称] 或 me',
    get_sx_info: '[服务器] [昵称] 或 me',
    get_BanInfo: '[服务器] [昵称] 或 me',
    get_ship_name: '<国家> <舰种> <等级>',
    roll_ship: '[国家] [舰种] [等级]',
    get_listen_list: '',
    add_listen_list: '<服务器> <昵称> <备注>',
    delete_listen_list: '<序号>',
    get_diff_ship: '',
    reset_config: '',
    check_version: '',
    async_update_template: '',
    async_update_ship_cache: '',
    get_help: '',
}

# 相似度阈值：低于该值的指令词不进入建议列表
_SIMILARITY_THRESHOLD = 0.5

# 服务器关键词（小写），用于排除"服务器+昵称"等合法身份查询的 token
_SERVER_KEYWORDS = {kw.casefold() for m in servers for kw in m.keywords}


def _is_server_token(token) -> bool:
    return str(token).casefold() in _SERVER_KEYWORDS


def _is_identity_query(match_list) -> bool:
    """判断无指令关键词的输入是否为合法的身份查询（me / @ / 服务器+昵称）。

    此类输入会走默认的账号查询逻辑，不应触发智能提示。
    """
    if not match_list:
        return False
    lowered = [str(t).casefold() for t in match_list]
    if lowered == ['me']:
        return True
    if any(re.search(r'CQ:at,qq=\d+|<@!\d+', str(t)) for t in match_list):
        return True
    # 服务器+昵称：恰好两个 token 且其中一个是服务器关键词（顺序不限）
    if len(match_list) == 2 and sum(1 for t in lowered if t in _SERVER_KEYWORDS) == 1:
        return True
    return False


async def _match_level(match_list, command_List, default_func) -> Tuple[command, List, bool]:
    """匹配一层指令。

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
            for i, match_kw in enumerate(match_list):
                if match_kw.find(kw) + 1:
                    match_list[i] = str(match_kw).replace(kw, '')
                    if not match_list[i]:  # 为空时才删除，防止未加空格没有被split切割
                        match_list.remove('')
                    return com, match_list, True
    return command(None, default_func, None), match_list, False


async def findFunction_and_replaceKeywords(match_list, command_List, default_func) -> Tuple[command, List]:
    """字段列表匹配(保持原签名)，无匹配时 func 为 default_func。"""
    com, match_list, _ = await _match_level(match_list, command_List, default_func)
    return com, match_list


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


def render_suggest_message(suggestions: List[dict]) -> str:
    """将建议列表渲染为提示文案（指令使用匹配到的关键词，参数补充用法提示）。"""
    lines = []
    for item in suggestions:
        words = []
        for com in item['path']:
            kw = item.get('kw')
            # 命中哪个别名就展示哪个别名（如输入"单传"提示"单船"），否则展示主别名
            word = kw if kw and kw in com.keywords else com.keywords[0]
            words.append(word)
        usage = _USAGE.get(item['handler'], '')
        line = 'wws ' + ' '.join(words)
        if usage:
            line += ' ' + usage
        lines.append(line)
    cap = hikari_config.command_suggest_max
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
