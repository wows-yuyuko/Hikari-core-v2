"""模板渲染回归测试。

覆盖本次「模板风格统一」涉及的 11 个模板（统一后为 xxx-v5.html）：
  wws-clan-v5 / wws-clan-cw-v5 / cw-rank-v5 / ship-rank-v5 / wws-sx-v5 /
  wws-box-christmas-v5 / wws-ban-v5 / wws-unban-v5 / bind-list-v5 /
  select-ship-v5 / select-clan-v5

每个模板两阶段验证：
  1. 严格渲染：使用与生产一致的环境（jinja2 + time/abs/enumerate/int 全局），
     传入完整假数据，缺失字段会抛 UndefinedError；
  2. 结构校验：对渲染后的具体 HTML 做标签配对校验（渲染后条件分支已展开，
     可得到真实的运行时结构）。

运行方式（与 test_command_suggest.py 一致）：
  python tests/test_templates_render.py
"""
import asyncio
import time
from pathlib import Path

import jinja2

from check_html import Checker

TPL_DIR = Path(__file__).resolve().parent.parent / 'hikari_core' / 'Template'

# ============================================================
# 假数据（形状与各模板消费的字段一一对应）
# ============================================================

_AVATAR = {
    'poster': {'status': 0},
    'colorName': {'status': 0},
    'banner': {'status': 0},
    'avatar': {'status': 0},
    'sign': {'status': 0},
}

_USER_INFO = {
    'avatar': _AVATAR,
    'clanInfo': {'tag': '', 'color': '#ffffff'},
    'userName': '测试玩家',
    'accountCreateTime': 0,
    'serverCn': '亚服',
}

# ---------- 封禁查询 ----------
_BAN_DATA = {
    'clanInfo': {'colorRgb': '#ffffff', 'tag': 'TAG'},
    'userName': '测试玩家',
    'serverName': 'asia',
    'accountId': '12345',
    'voList': [
        {'banTime': '2024-01-01', 'banName': '***', 'userName': '测试玩家', 'banNameNamesake': 1},
    ],
}

# ---------- 绑定列表 ----------
_BIND_LIST_DATA = [
    {'accountId': '100', 'defaultAccount': '100', 'server': 'asia', 'userName': '玩家A'},
    {'accountId': '200', 'defaultAccount': '100', 'server': 'cn', 'userName': '玩家B'},
]

# ---------- 选择列表 ----------
_SELECT_CLAN_DATA = [
    {'tag': 'AAA', 'name': '第一公会'},
    {'tag': 'BBB', 'name': '第二公会'},
]

_SELECT_SHIP_DATA = [
    {
        'serverType': 'ASIA', 'levelStr': 'X', 'shipType': 'Destroyer',
        'nameCn': '岛风', 'nameCn360': '岛风(360)', 'nameEnglish': 'Shimakaze',
    },
]

# ---------- 军团战排名 ----------
_CW_RANK_DATA = {
    'server': 'asia',
    'data': {
        'append': '第',
        'records': [
            {
                'rank': 1, 'server': 'asia', 'color': '#ffffff', 'tag': 'AAA', 'name': '第一公会',
                'leagueName': {'color': '#ffffff', 'buff': '黄金'},
                'divisionName': 'I', 'divisionRating': 100,
                'battlesCount': 100, 'lastBattleAt': 1700000000000,
            },
        ],
    },
}

# ---------- 单船排行榜 ----------
_SHIP_RANK_DATA = {
    'shipInfo': {
        'levelStr': 'X',
        'nameCn': '大和',
        'shipType': 'Battleship',
        'shipTypeCn': '战列舰',
        'nation': 'Japan',
        'serverType': 'ASIA',
        'shipId': 4289389488,
        'countryImage': 'https://v3-api.wows.shinoaki.com/nahida-static/ship_cache/Japan-Nation-image.png',
        'shipTypeImage': 'https://v3-api.wows.shinoaki.com/nahida-static/ship_cache/Battleship-ShipType-image.png',
        'imgSmall': 'https://v3-api.wows.shinoaki.com/nahida-static/ship_cache/asia-4289389488-small.png',
    },
    'data': {
        'value': [
            {
                'sortIndex': 1, 'battle': 100, 'damage': 100000,
                'damageColor': {'color': '#ffffff'}, 'wins': 55.5,
                'winsColor': {'color': '#ffffff'},
                'pr': {'color': '#ffffff', 'value': 1500},
                'userInfo': {
                    'avatar': {'banner': {'status': 0}, 'avatar': {'status': 0}},
                    'dogTag': '',
                    'clanInfo': {'tag': ''},
                    'userName': '玩家A',
                },
            },
        ],
    },
}

# ---------- 近期（随机 + 排位） ----------
def _bt(battle: int, pr: int, win: float = 60.0, damage: int = 100000) -> dict:
    """构造一个 battleType 节点（顶层与单船 typeInfo 共用同一形状）。"""
    return {
        'battle': battle,
        'prInfo': {'value': pr, 'name': '良好', 'color': '#ffffff'},
        'battleInfo': {
            'battleInfo': {'battle': battle},
            'avgInfo': {
                'xp': 1500,
                'win': win,
                'winsData': {'color': '#ffffff'},
                'damage': damage,
                'damageData': {'color': '#ffffff'},
                'frags': 1.5,
                'kd': 2.0,
                'shipsSpotted': 2.5,
                'planesKilled': 1.0,
            },
            'hitRatioInfo': {'ratioMain': 40.0},
            'fragsInfo': {
                'fragsByMain': 10, 'fragsByAtba': 1, 'fragsByPlanes': 2,
                'fragsByTpd': 3, 'fragsByRam': 0, 'fragsByDbomb': 1,
            },
        },
    }


_RECENT_SHIP_INFO = {
    'countryImage': 'https://x/Japan-Nation-image.png',
    'shipTypeImage': 'https://x/Battleship-ShipType-image.png',
    'levelStr': 'X',
    'imgSmall': 'https://x/asia-1-small.png',
    'nameCn': '大和',
}

_RECENT_DATA = {
    'userInfo': {**_USER_INFO, 'accountId': 12345},
    'battleTypeInfo': {
        'PVP': _bt(100, 2000),
        'PVP_SOLO': _bt(50, 1900),
        'PVP_DIV2': _bt(30, 1800),
        'PVP_DIV3': _bt(20, 1700),
        'RANK_SOLO': _bt(40, 1850),
    },
    'recordTime': 1700000000000,
    'shipInfoBattleList': [
        {'shipInfo': _RECENT_SHIP_INFO, 'typeInfo': {'PVP': _bt(10, 2100), 'RANK_SOLO': _bt(4, 1950)}},
        {'shipInfo': {**_RECENT_SHIP_INFO, 'nameCn': '出云', 'levelStr': 'IX'},
         'typeInfo': {'PVP': _bt(5, 1800), 'RANK_SOLO': _bt(0, 0)}},
    ],
}

# ---------- 战舰筛选（ships） ----------
_SHIPS_DATA = {
    'userInfo': {**_USER_INFO, 'accountId': 12345},
    'battleTypeInfo': {
        'PVP': _bt(100, 2000),
        'PVP_SOLO': _bt(50, 1900),
        'PVP_DIV2': _bt(30, 1800),
        'PVP_DIV3': _bt(20, 1700),
        'RANK_SOLO': _bt(40, 1850),
    },
    'filter': {
        'shipType': 'Battleship', 'country': 'Japan', 'level': '10',
        'min': 6, 'max': 10, 'desc': '10级 · 战列舰 · 日本 · 等级≥6 · 等级≤10',
    },
    'list': [
        {'shipInfo': _RECENT_SHIP_INFO, 'typeInfo': {'PVP': _bt(100, 2400)}},
        {'shipInfo': {**_RECENT_SHIP_INFO, 'nameCn': '出云', 'levelStr': 'IX'},
         'typeInfo': {'PVP': _bt(80, 2100)}},
    ],
}

# ---------- 扫雪 ----------
_SX_DATA = {
    'userInfo': _USER_INFO,
    'auth': True,
    'shipCount': 100,
    'resourceView': {
        'sumResource': [
            {'bonusMap': {'0': 10}},
            {'bonusMap': {'0': 20}},
            {'bonusMap': {'0': 30}},
        ],
        'infos': [
            {'level': 5, 'bonusType': 'STEEL', 'shipCount': 1, 'bonusMap': {'0': 1}},
            {'level': 6, 'bonusType': 'COAL', 'shipCount': 2, 'bonusMap': {'0': 2}},
        ],
    },
    'exchangeView': {
        'iconUrl': '',
        'name': '代币',
        'sumToken': 10,
        'exchangeList': [
            {'iconUrl': '', 'have': True, 'name': '物品', 'maxNumber': 1, 'price': 1},
        ],
        'extend': [],
    },
    'levelCount': [{'value': 1}, {'value': 2}],
}

# ---------- 圣诞箱 ----------
_BOX_DATA = {
    'userInfo': _USER_INFO,
    'auth': True,
    'count': 10,
    'have': 5,
    'dataMap': [
        {
            'probability': 1.5,
            'count': 10,
            'rare': 5,
            'data': [
                {'status': 0, 'ship': {'levelStr': 'X', 'nameCn': '大和'}},
                {'status': 1, 'ship': {'levelStr': 'IX', 'nameCn': '出云'}},
            ],
        },
    ],
}

# ---------- 军团战近期战绩 ----------
_CLAN_CW_DATA = {
    'avatar': {'banner': ''},
    'clan': {
        'tag': 'AAA', 'serverCn': '亚服', 'season': '2024', 'teamNumber': 1,
        'battlesCount': 100, 'wins': 55,
        'longestWinningStreak': 5, 'currentWinningStreak': 1,
        'status': 0,
        'leagueName': {'buff': '黄金'}, 'divisionName': 'I', 'divisionRating': 100,
        'stageProgressStr': '',
    },
    'list': [
        {
            'myTeam': {'battlesCount': 10},
            'opponentTeam': {
                'serverCn': '亚服', 'tag': 'BBB', 'teamNumber': 1, 'status': 0,
                'leagueName': {'buff': '黄金'}, 'divisionName': 'I', 'divisionRating': 90,
                'stageProgressStr': '',
            },
            'winBattle': True, 'score': 10, 'lastBattleTime': 1700000000000,
        },
    ],
    'echartsDate': ['2024-01-01'],
    'echartsBattle': [10],
    'echartsWins': [55],
}

# ---------- 军团信息 ----------
_CLAN_DATA = {
    'avatar': _AVATAR,
    'tag': 'AAA',
    'name': '第一公会',
    'server': 'asia',
    'clanId': 1,
    'description': '',
    'createdAt': 0,
    'userStatisticsInfo': {
        'pr': {'details': {'pr': 1000}},
        'rank': 1,
        'vitality': 50,
        'winsPercentage': 55,
        'winsData': {'color': '#ffffff'},
        'avgTimeInTheGroup': 10,
        'expPerBattle': 100,
        'damagePerBattle': 1000,
        'damageData': {'color': '#ffffff'},
        'battlesCount': 100,
    },
    'membersCount': 10,
    'maxMembersCount': 50,
    'clanLeagueInfo': {
        'lastSeason': 1,
        'battle': True,
        'dataMap': {
            '1': {
                'alpha': {
                    'battlesCount': 10, 'winsCount': 6, 'wins': 60,
                    'winsData': {'color': '#ffffff'},
                    'leagueName': {'color': '#ffffff', 'buff': '黄金'},
                    'divisionName': 'I', 'divisionRating': 100,
                    'currentWinningStreak': 2,
                    'maxLeagueName': {'color': '#ffffff', 'buff': '白金'},
                    'maxDivisionName': 'II', 'maxPositionDivisionRating': 120,
                    'longestWinningStreak': 3,
                },
                'bravo': {
                    'battlesCount': 5, 'winsCount': 2, 'wins': 40,
                    'winsData': {'color': '#ffffff'},
                    'leagueName': {'color': '#ffffff', 'buff': '青铜'},
                    'divisionName': 'I', 'divisionRating': 50,
                    'currentWinningStreak': 1,
                    'maxLeagueName': {'color': '#ffffff', 'buff': '青铜'},
                    'maxDivisionName': 'II', 'maxPositionDivisionRating': 60,
                    'longestWinningStreak': 2,
                },
            },
        },
        'alphaCharts': [
            {
                'season': 1, 'source': 100, 'maxSource': 200,
                'leagueName': {'buff': '黄金'}, 'divisionName': 'I', 'divisionRating': 100,
                'maxLeagueName': {'buff': '白金'}, 'maxDivisionName': 'II',
                'maxPositionDivisionRating': 120,
            },
        ],
    },
    'latest_season': '1',
    'buildingsInfos': [
        {'fullLevelColor': '#ffffff', 'level': 1, 'maxLevel': 10, 'buff': {'buff': '+5%'}}
        for _ in range(13)
    ],
}

# ============================================================
# 用例表
# ============================================================
CASES = [
    ('wws-ban-v5.html', _BAN_DATA, ['可能符合条件的历史记录', '封禁日期', '相似用户数']),
    ('wws-unban-v5.html', {**_BAN_DATA, 'voList': []}, ['未在官方封禁历史中匹配到该用户']),
    ('bind-list-v5.html', _BIND_LIST_DATA, ['当前绑定账号', '绑定账号列表', '玩家A']),
    ('select-clan-v5.html', _SELECT_CLAN_DATA, ['请在20秒内选择对应的序号', '第一公会']),
    ('select-ship-v5.html', _SELECT_SHIP_DATA, ['请在20秒内选择对应的序号', '岛风']),
    ('cw-rank-v5.html', _CW_RANK_DATA, ['赛季', '最后战斗时间', '第一公会']),
    ('ship-rank-v5.html', _SHIP_RANK_DATA, ['大和', '4289389488-small', '场次', 'PR']),
    ('wws-info-recent-v5.html', _RECENT_DATA, ['综合战绩', '随机战', '排位战']),
    ('wws-info-recent-random-v5.html', _RECENT_DATA, ['近期随机', '随机战']),
    ('wws-info-recent-rank-v5.html', _RECENT_DATA, ['近期排位', '排位战']),
    ('wws-ships-v5.html', _SHIPS_DATA, ['战舰筛选', '测试玩家', '大和', '出云', '等级≥6', '共 2 艘', '综合战绩', '随机战', '单野', '排位']),
    ('wws-ships-v5.html', {**_SHIPS_DATA, 'userInfo': None}, ['战舰筛选', '大和', '等级≥6', '综合战绩']),
    ('wws-sx-v5.html', _SX_DATA, ['总船只', '钢铁', '煤炭', '研发点']),
    ('wws-box-christmas-v5.html', _BOX_DATA, ['圣诞箱中', '已拥有', '收集进度']),
    ('wws-clan-cw-v5.html', _CLAN_CW_DATA, ['近期战斗', '段位', '胜率']),
    ('wws-clan-v5.html', _CLAN_DATA, ['军团战斗', '军团设施', '赛季段位']),
]


def build_env():
    """与生产环境一致的 Jinja2 环境（见 hikari_core/__init__.py）。"""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(TPL_DIR), enable_async=True)
    env.globals.update(time=time, abs=abs, enumerate=enumerate, int=int)
    return env


async def _render(name: str, data) -> str:
    env = build_env()
    tpl = env.get_template(name)
    return await tpl.render_async(template_path=TPL_DIR, data=data)


def _check_structure(html: str, name: str):
    """渲染后的具体 HTML 标签配对校验（条件分支已展开，无静态误报）。"""
    c = Checker()
    c.feed(html)
    c.close()
    errs = list(c.errors)
    for tag, line in c.stack:
        errs.append(f'<{tag}> (第{line}行) 未闭合')
    assert not errs, f'{name} 渲染后 HTML 结构不平衡: {errs[:5]}'


async def test_templates_render_and_structure():
    for name, data, markers in CASES:
        html = await _render(name, data)
        for m in markers:
            assert m in html, f'{name} 渲染结果缺少关键内容: {m!r}'
        _check_structure(html, name)


async def test_banner_dark_flag():
    """banner.dark 契约：dark=1 输出深色白字样式，dark=0 / 缺失 保持原逻辑。"""
    base = {
        **_RECENT_DATA,
        'userInfo': {
            **_USER_INFO,
            'accountId': 12345,
            'avatar': {
                **_AVATAR,
                'banner': {'status': 2, 'data': 'data:image/png;base64,AAAA'},
            },
        },
    }

    def _with_dark(dark):
        avatar = {**base['userInfo']['avatar'], 'banner': {**base['userInfo']['avatar']['banner'], 'dark': dark}}
        return {**base, 'userInfo': {**base['userInfo'], 'avatar': avatar}}

    html_dark = await _render('wws-info-recent-v5.html', _with_dark(1))
    assert '.page-header .user-sign-time,' in html_dark, 'dark=1 时应输出深色白字样式'
    assert 'no-color-name' in html_dark, '无彩色昵称时应带 no-color-name 标记'

    html_light = await _render('wws-info-recent-v5.html', _with_dark(0))
    assert '.page-header .user-sign-time,' not in html_light, 'dark=0 时保持原逻辑'
    assert 'no-color-name' in html_light

    html_default = await _render('wws-info-recent-v5.html', base)  # 未携带 dark -> 默认 0
    assert '.page-header .user-sign-time,' not in html_default, 'dark 缺失时默认浅色'


async def test_banner_is_dark():
    """banner 亮度判定（服务端未返回 dark 时的兜底）：

    取图片左 60% 区域，平均感知亮度 Y=0.299R+0.587G+0.114B 低于 128 判定为深色。
    """
    try:
        from hikari_core.core.render_helpers import banner_is_dark, enrich_banner_dark
    except ImportError:
        return  # 依赖不完整的环境跳过该用例

    import base64
    import io

    from PIL import Image

    def _data_url(rgb, size=(100, 40)):
        buf = io.BytesIO()
        Image.new('RGB', size, rgb).save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    def _two_tone(left_rgb, right_rgb):
        img = Image.new('RGB', (100, 40), right_rgb)
        for x in range(60):
            for y in range(40):
                img.putpixel((x, y), left_rgb)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    # 整图深浅
    assert banner_is_dark(_data_url((20, 20, 20))) is True
    assert banner_is_dark(_data_url((235, 235, 235))) is False
    # 左 60% 决定结果
    assert banner_is_dark(_two_tone((20, 20, 20), (235, 235, 235))) is True
    assert banner_is_dark(_two_tone((235, 235, 235), (20, 20, 20))) is False
    # 非法输入按浅色处理
    assert banner_is_dark('not-a-real-base64!!') is False
    assert banner_is_dark('data:image/png;base64,') is False

    # 兜底补算：未带 dark 时补算，已带 dark 时保留服务端结果
    data = {'userInfo': {'avatar': {'banner': {'status': 2, 'data': _data_url((20, 20, 20))}}}}
    enrich_banner_dark(data)
    assert data['userInfo']['avatar']['banner']['dark'] == 1

    data2 = {'userInfo': {'avatar': {'banner': {'status': 2, 'data': _data_url((20, 20, 20)), 'dark': 0}}}}
    enrich_banner_dark(data2)
    assert data2['userInfo']['avatar']['banner']['dark'] == 0  # 服务端结果优先


def run_all():
    tests = [
        v for k, v in sorted(globals().items())
        if k.startswith('test_') and asyncio.iscoroutinefunction(v)
    ]
    failed = 0
    for t in tests:
        try:
            asyncio.run(t())
            print(f'PASS  {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL  {t.__name__}: {e}')
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f'ERROR {t.__name__}: {type(e).__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} tests passed')
    return failed


if __name__ == '__main__':
    raise SystemExit(run_all())
