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
    get_ShipRecent,
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


async def test_case_insensitive_routing():
    """指令匹配大小写不敏感：SHIP / Rank 应正常路由，不再落到兜底账号查询。"""
    cases = [
        (['SHIP', '大和'], get_ShipInfo),
        (['Rank', 'ship', '大和'], get_ShipRank),
        (['recent', 'SHIP', '大和'], get_ShipRecent),
        (['单船', '大和'], get_ShipInfo),
    ]
    for tokens, expect in cases:
        func, rest, suggest = await route_command(list(tokens))
        assert func == expect, f'{tokens} -> {func}'
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


async def test_update_command_routes():
    """wws update：me / 服务器+昵称 / me 缺省 的路由与参数解析；不抢占 update_ship / update_style。"""
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command
    from hikari_core.commands.router import async_update_ship_cache, async_update_template, update_user_cache

    async def parse(text):
        hikari = Hikari_Model(
            UserInfo=UserInfo_Model(Platform='QQ', PlatformId='10000'),
            Input=Input_Model(Command_Text=text),
        )
        return await analyze_command(hikari)

    # wws me update
    h = await parse('me update')
    assert h.Status == 'init' and h.Function == update_user_cache
    assert h.Input.Search_Type == 1

    # wws update（me 缺省）
    h = await parse('update')
    assert h.Function == update_user_cache
    assert h.Input.Search_Type == 1

    # wws asia nahida_official update
    h = await parse('asia nahida_official update')
    assert h.Status == 'init' and h.Function == update_user_cache
    assert h.Input.Search_Type == 3
    assert h.Input.Server == 'asia'
    assert h.Input.AccountName == 'nahida_official'

    # 参数缺失 → 报错
    h = await parse('asia update')
    assert h.Status == 'error'

    # 不抢占 update_ship / update_style
    assert (await route_command(['update_ship']))[0] == async_update_ship_cache
    assert (await route_command(['update_style']))[0] == async_update_template


async def test_admin_flow():
    """管理员：统一验证+写入入口 + 全局缓存 + 直接发送校验串自动添加 + 系统指令门禁。"""
    import shutil
    import tempfile
    from pathlib import Path

    import hikari_core.core.admin as admin_mod
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command
    from hikari_core.features.system import async_update_template, check_version

    tmp = Path(tempfile.mkdtemp(prefix='hikari_admin_test_'))
    orig_get_cache = admin_mod.get_cache_file
    admin_mod.get_cache_file = lambda: tmp

    import hikari_core.features.system as sys_mod

    orig_update_template = sys_mod.update_template
    sys_mod.update_template = lambda: True  # 避免管理员放行时真实联网更新模板

    def make(text, platform_id='10000'):
        return Hikari_Model(
            UserInfo=UserInfo_Model(Platform='QQ', PlatformId=platform_id),
            Input=Input_Model(Command_Text=text),
        )

    try:
        admin_mod.load_admin_cache()
        # 初始：无 admin.txt → 非管理员，无待校验串
        assert admin_mod.is_admin('10000') is False
        assert admin_mod.get_pending_check_token() is None

        # 独立生成器：32 位校验串写入 checkAdmin.txt
        token = admin_mod.generate_check_admin()
        assert len(token) == 32
        assert admin_mod.get_pending_check_token() == token

        # 统一入口：错误串 → False（不写不删）
        assert admin_mod.verify_and_add_admin('10000', 'wrong') is False
        assert not (tmp / 'admin.txt').exists()
        assert (tmp / 'checkAdmin.txt').exists()
        assert admin_mod.is_admin('10000') is False

        # 统一入口：正确串 → True（写 admin.txt、删 checkAdmin.txt、进缓存）
        assert admin_mod.verify_and_add_admin('10000', token) is True
        assert '10000' in (tmp / 'admin.txt').read_text(encoding='utf-8')
        assert not (tmp / 'checkAdmin.txt').exists()
        assert admin_mod.is_admin('10000') is True  # 缓存命中

        # 统一入口：已是管理员（缓存命中）→ 直接 True，不再走校验
        assert admin_mod.verify_and_add_admin('10000', 'whatever') is True

        # 已有 admin.txt → 生成器不再生成
        assert admin_mod.generate_check_admin() == ''

        # 启动缓存加载：手动追加 ID 后 load_admin_cache 生效
        with open(tmp / 'admin.txt', 'a', encoding='utf-8') as f:
            f.write('20000\n')
        admin_mod.load_admin_cache()
        assert admin_mod.is_admin('20000') is True
        assert admin_mod.is_admin('99999') is False

        # 直接发送校验串 → analyze_command 自动验证+写入（无指令前缀）
        (tmp / 'admin.txt').unlink()
        admin_mod.load_admin_cache()
        token2 = admin_mod.generate_check_admin()
        assert len(token2) == 32
        h = await analyze_command(make(token2, platform_id='30000'))
        assert h.Status == 'success'
        assert '管理员添加成功' in str(h.Output.Data)
        assert '30000' in (tmp / 'admin.txt').read_text(encoding='utf-8')
        assert not (tmp / 'checkAdmin.txt').exists()
        assert admin_mod.is_admin('30000') is True

        # 管理员发送普通消息 → 不被校验拦截，走正常解析（未识别）
        h = await analyze_command(make('qwertyuiop', platform_id='30000'))
        assert h.Status == 'error'
        assert '未识别' in str(h.Output.Data)

        # 非管理员 + 无待校验串 → 正常解析（未识别）
        (tmp / 'admin.txt').unlink()
        admin_mod.load_admin_cache()
        h = await analyze_command(make('qwertyuiop', platform_id='99999'))
        assert h.Status == 'error'

        # 门禁：非管理员触发 check_version / update_style 被拦截（不联网）
        h = await analyze_command(make('check_version', platform_id='99999'))
        assert h.Function == check_version
        h = await check_version(h)
        assert h.Status == 'error' and '仅管理员' in str(h.Output.Data)

        h = await analyze_command(make('update_style', platform_id='99999'))
        h = await async_update_template(h)
        assert h.Status == 'error' and '仅管理员' in str(h.Output.Data)

        # 门禁：管理员放行 update_style（打桩 update_template → 成功）
        with open(tmp / 'admin.txt', 'w', encoding='utf-8') as f:
            f.write('30000\n')
        admin_mod.load_admin_cache()
        h = await analyze_command(make('update_style', platform_id='30000'))
        h = await async_update_template(h)
        assert h.Status == 'success'
    finally:
        admin_mod.get_cache_file = orig_get_cache
        sys_mod.update_template = orig_update_template
        shutil.rmtree(tmp, ignore_errors=True)


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
# 单船查询参数解析（多词英文船名）
# ============================================================

async def test_ship_parse_me_mode_joins_remaining_tokens():
    """me 模式（显式 me 或未指定服务器默认查自己）把剩余 token 合并为船名，支持多词英文船名。"""
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command

    async def parse(text):
        hikari = Hikari_Model(
            UserInfo=UserInfo_Model(Platform='QQ', PlatformId='10000'),
            Input=Input_Model(Command_Text=text),
        )
        return await analyze_command(hikari)

    # 无 me：默认查自己，多词英文船名合并
    h = await parse('ship Jean Bart')
    assert h.Status == 'init' and h.Function == get_ShipInfo
    assert h.Input.Search_Type == 1
    assert h.Input.ShipInfo.nameCn == 'Jean Bart'

    # 显式 me 同样合并
    h = await parse('ship me Jean Bart')
    assert h.Input.ShipInfo.nameCn == 'Jean Bart'

    # 单字中文船名不受影响
    h = await parse('ship 大和')
    assert h.Input.ShipInfo.nameCn == '大和'

    # server 模式行为不变
    h = await parse('ship asia 玩家名 大和')
    assert h.Input.Search_Type == 3
    assert h.Input.AccountName == '玩家名'
    assert h.Input.ShipInfo.nameCn == '大和'

    # recent 组合：多词船名 + 天数
    h = await parse('ship Jean Bart recent 30')
    assert h.Function == get_ShipRecent
    assert h.Input.ShipInfo.nameCn == 'Jean Bart'
    assert h.Input.Recent_Day == 30

    # 缺船名
    h = await parse('ship')
    assert h.Status == 'error'


# ============================================================
# 括号分组昵称（(AI deal) 含空格昵称）
# ============================================================

async def test_paren_group_nickname_with_spaces():
    """半角括号包裹的含空格昵称合并为单个 token：cn (AI deal) recent → AccountName='AI deal'。"""
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command

    async def parse(text):
        hikari = Hikari_Model(
            UserInfo=UserInfo_Model(Platform='QQ', PlatformId='10000'),
            Input=Input_Model(Command_Text=text),
        )
        return await analyze_command(hikari)

    # 服务器 + 括号昵称 + recent（昵称含空格被括号包裹）
    h = await parse('cn (AI deal) recent')
    assert h.Status == 'init' and h.Function == get_RecentInfo
    assert h.Input.Server == 'cn'
    assert h.Input.AccountName == 'AI deal'

    # 括号昵称用于水表查询（无指令关键词）
    h = await parse('asia (Jean Bart)')
    assert h.Function == get_AccountInfo
    assert h.Input.Server == 'asia'
    assert h.Input.AccountName == 'Jean Bart'

    # 不带括号的普通昵称不受影响
    h = await parse('cn 西行寺 recent')
    assert h.Input.AccountName == '西行寺'

    # 单 token 括号：(AI) -> AI
    h = await parse('cn (AI) recent')
    assert h.Input.AccountName == 'AI'

    # 船名查询不受影响（单 token 内部括号不合并）
    h = await parse('ship 大和')
    assert h.Input.ShipInfo.nameCn == '大和'


# ============================================================
# me 缺省与未识别提示
# ============================================================

async def test_me_omission_defaults_to_self():
    """me 可缺省：有指令匹配且未指定服务器时默认查自己；服务器+昵称模式不受影响。"""
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command
    from hikari_core.commands.router import get_BindInfo, get_sx_info

    async def parse(text):
        hikari = Hikari_Model(
            UserInfo=UserInfo_Model(Platform='QQ', PlatformId='10000'),
            Input=Input_Model(Command_Text=text),
        )
        return await analyze_command(hikari)

    # 娱乐：wws sx 有指令匹配 → 默认查自己
    h = await parse('sx')
    assert h.Status == 'init' and h.Function == get_sx_info
    assert h.Input.Search_Type == 1

    # 近期：wws recent 30 有指令匹配 → 默认查自己
    h = await parse('recent 30')
    assert h.Status == 'init'
    assert h.Input.Search_Type == 1

    # 服务器+昵称 不受影响
    h = await parse('asia 玩家名')
    assert h.Input.Search_Type == 3

    # 绑定列表 me 仍可用
    h = await parse('bind_list me')
    assert h.Status == 'init' and h.Function == get_BindInfo
    assert h.Input.Search_Type == 1


async def test_bare_me_allowed():
    """wws me 单独使用正常（查询自己水表）。"""
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command

    hikari = Hikari_Model(
        UserInfo=UserInfo_Model(Platform='QQ', PlatformId='10000'),
        Input=Input_Model(Command_Text='me'),
    )
    hikari = await analyze_command(hikari)
    assert hikari.Status == 'init'
    assert hikari.Function == get_AccountInfo
    assert hikari.Input.Search_Type == 1


async def test_unmatched_word_gives_hint():
    """无指令匹配且非身份查询的输入（wws 测试）给出未识别提示，而非静默查自己。"""
    from hikari_core import Hikari_Model, Input_Model, UserInfo_Model
    from hikari_core.commands.parser import analyze_command

    for text in ['测试', '大和']:
        hikari = Hikari_Model(
            UserInfo=UserInfo_Model(Platform='QQ', PlatformId='10000'),
            Input=Input_Model(Command_Text=text),
        )
        hikari = await analyze_command(hikari)
        assert hikari.Status == 'error', text
        assert '未识别' in str(hikari.Output.Data), text


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
