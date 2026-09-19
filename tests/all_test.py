"""全量指令真执行测试（联网）：逐条真实请求 yuyuko，**流程全部执行完毕后**统一输出报告。

每条用例走 ``init_hikari`` 完整链路（整词路由 + 身份/参数解析 + 功能函数**真正联网执行**），
执行阶段只把结果收集进列表（不逐条打印），全部跑完后一次性输出：

    命令：用户输入的完整命令文本
    匹配：路由解析命中的功能函数名（如 get_RecentInfo）
    结果：Status（success / failed / wait / error）+ 数据摘要

判定口径：
- ``failed``：查询无果 / API 数据层（如账号未绑定、找不到玩家、该日无战绩）→ 计入但不判失败；
- ``error``：本地解析 / 渲染 / 网络异常 → 判为失败，报告末尾汇总；
- ``wait``：进入多选（船名/列表），自动选第 1 项回调后再记录一次。

**排除**（仅写操作/有副作用指令，避免测试破坏线上数据或本地环境）：
``bind``（覆盖绑定）、``delete_bind``/``change_bind``（真删/真切换）、
``special_bind``、``update``、``check_version``（会 git pull 改仓库！）、
``update_style`` / ``update_ship``（大下载/写模板缓存）。
ban / 封号记录 已纳入用例（仅国服可查：服务器 cn + 昵称 西行寺雨季）。

运行前请按实际环境修改下方接入配置（token 有效、me 类需平台账号已绑定）。

▍用法：就一个全局开关 `RENDER_MODE`（在下面的接入配置里，直接改那行）

    RENDER_MODE = 'none'    # 只打 API 看数据摘要（最快，验解析/取数）
    RENDER_MODE = 'html'    # 走模板：渲染出 HTML（不开浏览器、不截图）
    RENDER_MODE = 'image'   # 走模板：渲染 + 截图出图（需要 playwright 浏览器）

就是 config 里两个开关的组合：
    none  → auto_rendering=False              （不碰模板）
    html  → auto_rendering=True,  auto_image=False
    image → auto_rendering=True,  auto_image=True

▍产物（RENDER_MODE 非 none 时）
每条用例的产物写进 `OUT_DIR`：
    <序号>-<命令片段>.html    渲染用的 HTML —— **自带渲染器**，浏览器直接打开就是成品页
    <序号>-<命令片段>.jpg     出图模式的截图（png/webp 跟随 config.image_type）
"""

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hikari_core import callback_hikari, init_hikari, get_cache_file  # noqa: E402
from hikari_core.core.config import hikari_config, set_hikari_config  # noqa: E402

# ============================================================
# 接入配置（按实际环境修改）
# ============================================================
PLATFORM = 'QQ'  # 平台类型（QQ / QQ_OFFICIAL 等）
PLATFORM_ID = '2622749113'  # 发送者 ID（me 类需要该账号已绑定）
GROUP_ID = '967546463'  # 群号
BOT_ID = '0'
# 环境变量优先（与 tests/js_render_guard.py 共用同一个 HIKARI_TOKEN），不设就用下面的默认值
TOKEN = os.environ.get('HIKARI_TOKEN') or '2622749113:TAN9iMARSDJbzLVOUK1a9cTSiKtb32GIbpr'
PROXY = None
GAME_PATH = ''  # 空 = 默认 data/wows-yuyuko

# ============================================================
# 全局开关：是否走模板输出
# ============================================================
#   'none'  只打 API 看数据摘要（最快）—— 验解析 / 取数用这个
#   'html'  走模板渲染，产物是 HTML（不开浏览器、不截图）
#   'image' 走模板渲染 + 截图出图（需要 playwright 浏览器）
RENDER_MODE = 'image'

# 产物目录（RENDER_MODE 非 none 时，每条用例的 html / 图写到这里）
OUT_DIR = get_cache_file() / 'all_test'

# 档位 → config 里那两个开关（(auto_rendering, auto_image)）
RENDER_MODES = {
    'none': (False, False),
    'html': (True, False),
    'image': (True, True),
}
IMAGE_EXT = {'jpeg': 'jpg', 'png': 'png', 'webp': 'webp'}

# ============================================================
# 真执行用例：全部指令的只读组合（写操作指令已排除）
# ============================================================
CASES = [
    # ---- 水表 / 身份三态 ----
    'asia nahida_official',  # 服务器+昵称
    '亚服 nahida_official',  # 中文服务器别名
    'me',  # 绑定账号
    # ---- 近期战绩（天数 / 日期 / 随机 / 排位）----
    'asia nahida_official recent',
    'asia nahida_official recent 7',
    '近期 7',  # me 缺省 + 中文别名
    'me recent 15',
    'recent 2024-05-30',  # 指定日期（该日无战绩 → failed，属数据层）
    'asia nahida_official recent 随机 7',
    'recent_random 7',
    '近期随机',
    'recent_rank 7',  # 无排位战绩 → failed，属数据层
    '近期排位 7',
    # ---- 单船 / 单船近期（含多词船名走 me、双分支顺序）----
    'asia nahida_official ship 得梅因',
    'ship 大和',
    '单船 大和',
    'asia nahida_official ship 得梅因 recent 7',
    'ship 大和 recent 7',
    'recent ship 大和 7',
    'ship Jean Bart recent 2024-05-30',
    # ---- 单场近期 ----
    'asia nahida_official recents',
    '单场近期 7',
    # ---- 排行榜 ----
    'ship.rank asia 得梅因',
    'rank ship cn 大和',
    '单船排行榜 cn 大和',
    # ---- 军团 / 公会 ----
    'clan asia yu_ri',
    '军团 asia yu_ri',
    'clan.rank asia yu_ri',
    'rank clan asia yu_ri',
    'cw.rank asia 25',
    '公会战排行榜 cn 25',
    'cw.recent cn 团子大家族 25',
    '公会战记录 cn 团子大家族 25',
    # ---- 战舰列表筛选 ----
    'ships bb 10 japan min 6 max 10',
    'asia nahida_official ships bb 10 japan',
    # ---- 娱乐（只读）----
    'asia nahida_official sx',
    'sx',
    'asia nahida_official sd',
    'box me',
    'roll',
    'roll 日本 BB 10',
    'roll 泛亚 DD',
    'search_ship 日本 战列舰 10',
    '搜船名 美国 BB 10',
    # ---- 封号记录（仅国服：cn 西行寺雨季）----
    'ban cn 西行寺雨季',
    '封号记录 cn 西行寺雨季',
    '封号记录 国服 西行寺雨季',
    # ---- 绑定（只读）/ 帮助 ----
    'bind_list me',
    '查询绑定 me',
    'help',
]


def _resolve_mode():
    """把全局开关 RENDER_MODE 翻成 config 用的两个开关，返回 (档位, auto_rendering, auto_image)。

    档位写错就直接报错退出 —— 这个常量是手改的，写错字静默跑成 none 会白跑一轮。
    """
    if RENDER_MODE not in RENDER_MODES:
        raise SystemExit(f'RENDER_MODE={RENDER_MODE!r} 不认识，只能是 '
                         f'{" / ".join(RENDER_MODES)}')
    auto_rendering, auto_image = RENDER_MODES[RENDER_MODE]
    return RENDER_MODE, auto_rendering, auto_image


def _slug(text: str, limit: int = 40) -> str:
    """命令文本 → 能当文件名的片段（中文/字母数字保留，其余压成下划线）。"""
    cleaned = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff.-]+', '_', text.strip())
    return cleaned.strip('_.')[:limit] or 'case'


def _dump_artifacts(out_dir: Path, index: int, text: str, fn: str, step: int,
                    hikari, image_type: str):
    """把一条用例这一次执行的产物落盘，返回写出的文件列表。

    ▍产物有两个来源，**都要留**：
      · `hikari.template_content`（local_test=True 时由 output_hikari 填）→ 渲染用的 HTML。
        注意它是**自带渲染器的外壳**（数据 + 模板源码 + hikari-render.js），
        浏览器直接打开就是成品页 —— 这也是排模板问题最方便的东西。
      · `hikari.Output.Data`：出图模式是图片字节；只渲染模式就是同一份 HTML。
    """
    written = []
    base = f'{index:02d}-{_slug(text)}' + (f'-s{step}' if step > 1 else '')
    data = hikari.Output.Data
    html = getattr(hikari, 'template_content', '') or ''
    if not html and isinstance(data, str) and 'hikari-render.js' in data:
        html = data
    if html:
        target = out_dir / f'{base}.html'
        target.write_text(html, encoding='utf-8')
        written.append(target)
    if isinstance(data, (bytes, bytearray)):
        target = out_dir / f'{base}.{IMAGE_EXT.get(image_type, "jpg")}'
        target.write_bytes(bytes(data))
        written.append(target)
    return written


def _summarize(hikari) -> str:
    """把执行结果压成一行摘要。"""
    data = hikari.Output.Data
    if hikari.Status == 'success':
        if isinstance(data, bytes):
            return f'图片 {len(data)} 字节'
        if isinstance(data, str):
            if hikari.Output.Template:
                return f'渲染 {hikari.Output.Template}（{len(data)} 字符）'
            return data[:200].replace('\n', ' ')
        if isinstance(data, dict):
            return f'数据 dict keys={list(data)[:10]}'
        if isinstance(data, list):
            return f'数据 list[{len(data)}]'
        return repr(data)[:200]
    if hikari.Status == 'wait':
        return '进入多选：' + (str(data)[:120].replace('\n', ' '))
    return str(data)[:200].replace('\n', ' ')


async def _execute(text: str):
    """真执行单条命令。

    Returns:
        (功能名, [(status, 摘要), ...], [(第几步, hikari), ...])
        第三步留给调用方落盘产物（`--render` 非 none 时用）—— 在这里直接写文件会把
        「执行」和「输出」搅在一起，也不方便只跑报告。
    """
    hikari = await init_hikari(
        platform=PLATFORM, PlatformId=PLATFORM_ID, BotId=BOT_ID,
        command_text=text, GroupId=GROUP_ID,
    )
    fn = getattr(hikari.Function, '__name__', 'None')
    steps = [(hikari.Status, _summarize(hikari))]
    seen = [(1, hikari)]
    if hikari.Status == 'wait':
        # 多选流程：自动选第 1 项后回调（用例已排除写操作指令，选择均为只读查询）
        hikari.Input.Select_Index = 1
        hikari = await callback_hikari(hikari)
        steps.append((hikari.Status, _summarize(hikari)))
        seen.append((2, hikari))
    return fn, steps, seen


def _build_report(results) -> str:
    """把收集到的全部执行结果渲染成一份报告（一次性输出）。"""
    lines = []
    total = len(results)
    stat = {'success': 0, 'failed': 0, 'wait': 0, 'error': 0}
    for entry in results:
        lines.append(f"[{entry['index']:02d}/{total}] 命令: {entry['text']}")
        if entry['exception']:
            lines.append('        匹配: -')
            lines.append(f"        结果: error | 异常 {entry['exception']}")
            stat['error'] += 1
            continue
        lines.append(f"        匹配: {entry['fn']}")
        for status, summary in entry['steps']:
            stat[status] = stat.get(status, 0) + 1
            mark = '   <<< ERROR' if status == 'error' else ''
            lines.append(f'        结果: {status} | {summary}{mark}')

    lines.append('')
    lines.append('================ 汇总 ================')
    lines.append(f'用例总数 {total}：success={stat["success"]}  failed={stat["failed"]}  '
                 f'wait={stat["wait"]}  error={stat["error"]}')
    error_entries = [e for e in results if e['exception'] or any(s == 'error' for s, _ in e['steps'])]
    if error_entries:
        lines.append('')
        lines.append(f'错误（error）用例 {len(error_entries)} 条——请检查解析/渲染/网络：')
        for e in error_entries:
            lines.append(f'  {e["text"]}  [{e.get("fn", "-")}]  {e["exception"] or e["steps"]}')
    else:
        lines.append('无 error，全部指令真执行通过（failed 属数据层无结果，不影响）')
    return '\n'.join(lines)


async def main() -> int:
    mode, auto_rendering, auto_image = _resolve_mode()

    set_hikari_config(
        token=TOKEN, proxy=PROXY, use_broswer='chromium', http2=False,
        local_test=True, auto_rendering=auto_rendering, auto_image=auto_image,
        game_path=GAME_PATH, yuyuko_type='QQ_CHANNEL',
    )

    out_dir = Path(OUT_DIR)
    if mode != 'none':
        out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    artifacts = []
    for i, text in enumerate(CASES, 1):
        entry = {'index': i, 'text': text, 'fn': None, 'steps': [], 'exception': None}
        try:
            entry['fn'], entry['steps'], seen = await _execute(text)
            if mode != 'none':
                # 产物就地落盘（不攒到最后）：出图模式的图片有几 MB，攒着容易白占内存
                for step_no, hikari in seen:
                    artifacts.extend(_dump_artifacts(
                        out_dir, i, text, entry['fn'] or '-', step_no,
                        hikari, hikari_config.image_type))
        except Exception as e:  # noqa: BLE001
            entry['exception'] = f'{type(e).__name__}: {e}'
        results.append(entry)
        await asyncio.sleep(0.2)  # 轻微节流，避免触发频控

    # —— 全部流程执行完毕，统一输出报告 ——
    print(f'平台 {PLATFORM}/{PLATFORM_ID}  bot={BOT_ID} 群={GROUP_ID}  '
          f'渲染={mode}（auto_rendering={auto_rendering} auto_image={auto_image}）  '
          f'共 {len(results)} 条用例（写操作指令已排除）')
    if mode != 'none':
        print(f'渲染产物 {len(artifacts)} 个 → {out_dir.resolve()}')
    print(_build_report(results))

    error_count = sum(
        1 for e in results
        if e['exception'] or any(s == 'error' for s, _ in e['steps'])
    )
    return 1 if error_count else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
