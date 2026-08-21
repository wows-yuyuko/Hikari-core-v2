"""指令路由与智能提示单元测试（无网络依赖，仅调用路由层）。

可直接运行:  python tests/test_command_suggest.py
也可通过 pytest 运行: pytest tests/test_command_suggest.py
"""

import asyncio

from hikari_core.commands.router import (
    get_AccountInfo,
    get_RecentInfo,
    get_ShipInfo,
    get_ShipRank,
    route_command,
    render_suggest_message,
    select_command,
)
from hikari_core.core.config import hikari_config


# ============================================================
# 路由行为回归
# ============================================================

async def test_normal_command_still_routes():
    """正常指令路由不被智能提示影响。"""
    func, rest, suggest = await route_command(['ship', '大和'])
    assert func is not None and func != get_AccountInfo
    assert suggest == []


async def test_select_command_keeps_old_signature():
    """select_command 保持原签名（兼容外部引用）。"""
    func, rest = await select_command(['recent', '3'])
    assert func == get_RecentInfo


async def test_identity_query_no_suggest():
    """服务器+昵称 的合法账号查询不应触发智能提示。"""
    func, rest, suggest = await route_command(['asia', 'nahida_official'])
    assert func == get_AccountInfo
    assert suggest == []


async def test_me_query_no_suggest():
    """me 查询自身账号不应触发智能提示。"""
    func, rest, suggest = await route_command(['me'])
    assert func == get_AccountInfo
    assert suggest == []


async def test_second_level_match_no_suggest():
    """二级指令正常命中（recent ship）不产生建议。"""
    func, rest, suggest = await route_command(['recent', 'ship', '大和'])
    assert func is not None and func != get_AccountInfo
    assert suggest == []


# ============================================================
# 智能提示
# ============================================================

async def test_chinese_typo_suggests_correct():
    """中文错别字（单传→单船）给出正确指令提示。"""
    func, rest, suggest = await route_command(['单传', '大和'])
    assert func == get_AccountInfo
    assert suggest, '错别字应产生建议'
    msg = render_suggest_message(suggest)
    assert '单船' in msg
    assert '<船名>' in msg  # 应提示参数用法


async def test_english_typo_suggests_recent():
    """英文拼写错误（recebt→recent）给出提示。"""
    func, rest, suggest = await route_command(['recebt'])
    assert suggest
    handlers = {s['handler'] for s in suggest}
    assert get_RecentInfo in handlers


async def test_typo_clan_suggests_gonghui():
    """工会 已收敛为 公会，输错时给出公会/军团相关提示。"""
    func, rest, suggest = await route_command(['工会', '排行榜'])
    assert suggest, '工会 应触发公会的智能提示'
    msg = render_suggest_message(suggest)
    assert '公会' in msg or '军团' in msg


async def test_prefix_input_suggests():
    """前缀输入（查询→查询绑定）给出提示。"""
    func, rest, suggest = await route_command(['查询'])
    assert suggest
    msg = render_suggest_message(suggest)
    assert '绑定' in msg


async def test_second_level_typo_suggests():
    """二级指令输错（ship ... recebt → recent）也能提示。"""
    func, rest, suggest = await route_command(['ship', '大和', 'recebt'])
    assert suggest, '二级指令错别字应产生建议'
    msg = render_suggest_message(suggest)
    assert 'recent' in msg or '近期' in msg


async def test_no_suggest_for_garbage():
    """完全无关的输入不产生建议（回落原账号查询逻辑）。"""
    func, rest, suggest = await route_command(['qwertyuiop'])
    assert suggest == []
    assert func == get_AccountInfo


# ============================================================
# 可配置项：去重 / 条数上限
# ============================================================

async def test_dedupe_mechanism():
    """去重开关：get_ShipRank 同时被 '单船排行榜' 与 'ship.rank' 精确命中。

    开启去重时同一功能只提示一条；关闭时多条同效果别名可同时提示。
    """
    from hikari_core.commands.router import _suggest, first_command_list

    tokens = ['单船排行榜', 'ship.rank']
    hikari_config.command_suggest_dedupe = True
    sug_on = _suggest(tokens, first_command_list)
    assert sum(1 for s in sug_on if s['handler'] == get_ShipRank) == 1

    hikari_config.command_suggest_dedupe = False
    sug_off = _suggest(tokens, first_command_list)
    assert sum(1 for s in sug_off if s['handler'] == get_ShipRank) >= 2
    hikari_config.command_suggest_dedupe = True


async def test_max_limit_caps_suggestions():
    """最大提示条数生效（设为 1 时只提示 1 条）。"""
    hikari_config.command_suggest_max = 1
    try:
        func, rest, suggest = await route_command(['recebt'])
        assert len(suggest) <= 1
    finally:
        hikari_config.command_suggest_max = 3


async def test_max_zero_disables_suggest():
    """最大条数设为 0 时关闭智能提示。"""
    hikari_config.command_suggest_max = 0
    try:
        func, rest, suggest = await route_command(['recebt'])
        assert suggest == []
        assert func == get_AccountInfo  # 回落原逻辑
    finally:
        hikari_config.command_suggest_max = 3


async def test_render_message_format():
    """提示文案包含指令与参数用法。"""
    func, rest, suggest = await route_command(['单传'])
    msg = render_suggest_message(suggest)
    assert msg.startswith('未识别的指令')
    assert 'wws ' in msg
    assert 'wws help' in msg


# ============================================================
# 中英文模式
# ============================================================

async def test_english_mode_hints_english():
    """英文模式下提示英文指令与英文参数用法。"""
    hikari_config.command_language = 'en'
    try:
        func, rest, suggest = await route_command(['单传'])
        assert suggest
        msg = render_suggest_message(suggest)
        assert 'Did you mean' in msg
        assert 'wws ship <ship name>' in msg
        assert '单船' not in msg  # 英文模式不展示中文别名
    finally:
        hikari_config.command_language = 'zh'


async def test_english_mode_english_typo():
    """英文模式下英文拼写错误提示英文指令。"""
    hikari_config.command_language = 'en'
    try:
        func, rest, suggest = await route_command(['shep', '大和'])
        assert suggest
        msg = render_suggest_message(suggest)
        assert 'wws ship <ship name>' in msg
    finally:
        hikari_config.command_language = 'zh'


async def test_zh_mode_unchanged():
    """默认中文模式行为不变。"""
    hikari_config.command_language = 'zh'
    func, rest, suggest = await route_command(['单传', '大和'])
    msg = render_suggest_message(suggest)
    assert '你是不是想输入' in msg
    assert 'wws 单船 <船名>' in msg


async def test_english_alias_routes():
    """新增英文别名可直接路由（英文模式下的指令入口）。"""
    from hikari_core.commands.router import (
        async_update_ship_cache,
        get_BindInfo,
        get_ship_name,
    )

    cases = [
        (['search_ship'], get_ship_name),
        (['bind_list'], get_BindInfo),
        (['update_ship'], async_update_ship_cache),
    ]
    for tokens, expect in cases:
        func, rest, suggest = await route_command(list(tokens))
        assert func == expect, f'{tokens} -> {func}'
        assert suggest == []


async def test_help_templates_render():
    """中英文帮助 H5 模板可正常渲染（无网络）。"""
    from hikari_core import env

    cases = [
        ('help-zh.html', 'Hikari 指令帮助'),
        ('help-en.html', 'Hikari Commands'),
    ]
    for name, keyword in cases:
        tpl = env.get_template(name)
        html = await tpl.render_async(data={'version_info': 'Version 1.2.5 | Latest 9.9'})
        assert keyword in html, name
        assert 'wws ship' in html, name


# ============================================================
# 独立运行入口
# ============================================================

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
