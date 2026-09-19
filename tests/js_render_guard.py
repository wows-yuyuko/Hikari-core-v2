"""浏览器端渲染冒烟测试：把每个模板**真的在浏览器里渲染一遍**，检查它没坏。

▍它现在检查什么（Jinja 已全面移除，不再做「双引擎比对」）
1. `window.__hikari_render_done` 必须是 `true`（截图服务等的就是它）；
2. 页面里**不能**出现 `#hikari-render-error`（渲染器报错时会写进去）；
3. 页高 > 0（探针能量到根容器）；
4. 文本段数 ≥ 该模板的**下限**（`MIN_SEGMENTS`）—— 这条是防「整块内容静默消失」
   那类事故的：模板只要少渲染一大块（空集合真值性、变量名写错…），段数就会掉下去；
5. `--compile-only`：全部模板在 Nunjucks 下编译通过（不需要数据，最便宜的兜底）。

▍为什么不做「逐像素比对」了
逐像素比对是**迁移期间**的手段：拿 git 历史里迁移前的模板（Jinja）跑一遍、和现在的
Nunjucks 产物比，证明"迁移没改观感"。那需要 jinja2，而它已从依赖里彻底移除。
迁移已经完成并验证过（13/13、0 像素），现在这条路没有第二个引擎可比 —— 想要"改模板后
仍逐像素一致"的门禁，得改成**固定数据快照**（把接口响应存成 fixture + 存参考图），
那是另一件事，见文件末尾的 TODO。

▍怎么跑
    python tests/js_render_guard.py                       # 内置用例（打真实接口）
    python tests/js_render_guard.py --compile-only         # 全模板编译检查（不需要数据）
    python tests/js_render_guard.py --list                 # 列出内置用例
    python tests/js_render_guard.py --template wws-ship-v6.html --data-file data.json
    python tests/js_render_guard.py --keep                 # 保留 HTML / DOM / 截图 便于肉眼看
    HIKARI_CHROME=/path/to/chrome python tests/js_render_guard.py

只依赖 pillow / 一个本机浏览器 —— **不 import hikari_core**（那会拉起 playwright 等重依赖），
改用「假包」把 core 下的真实模块直接加载进来。

▍需要鉴权的用例
私有的 `/api/...` 接口（近期战绩系模板）要真 token；没设就**跳过不判失败**。
    `$env:HIKARI_TOKEN='...'`（bash: `export HIKARI_TOKEN=...`）
"""

import argparse
import datetime
import html as html_module
import importlib
import json
import os
import re
import subprocess
import sys
import types
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / 'hikari_core' / 'core'
TEMPLATE_DIR = REPO / 'hikari_core' / 'Template'
TMP = REPO / '.workbuddy' / 'tmp' / 'js_render_guard'
# 私有接口（近期战绩系模板）要真 token；公开用例不需要，保持默认空
TOKEN = os.environ.get('HIKARI_TOKEN') or ''
# 截图共用的浏览器 profile（持久化 HTTP 缓存，理由见 screenshot 的注释）
CHROME_PROFILE = TMP / '_chrome_profile'

# 冻结 time.time()：模板里普遍有「数据更新：{{ time.time() }}」这类"当前时间"，
# 不冻住的话每次渲染都不同（比对/盯图时是噪声）。
FROZEN_TIME = 1789724000

# 文本段数下限（模板 → 最低段数）。取实测值的 ~80%：
# 数据每天在变、段数本来就有浮动，所以**只做下限**，不做精确比对 —— 它拦的是
# 「整块内容静默消失」这种事故（少渲染一整列/一整个区块），不是小改动。
MIN_SEGMENTS = {
    'wws-info-v6.html': 105,
    'wws-clan-v6.html': 78,
    'wws-ship-v6.html': 67,
    'ship-rank-v6.html': 176,
    'cw-rank-v6.html': 646,
    'wws-ships-v6.html': 2626,
    'wws-box-christmas-v6.html': 375,
    'wws-sx-v6.html': 83,
    'wws-info-recent-v6.html': 123,
    'wws-info-recent-random-v6.html': 120,
    'wws-info-recent-rank-v6.html': 45,
    'wws-ship-recent-v6.html': 40,
    'wws-info-recents-v6.html': 184,
}
MIN_SEGMENTS_DEFAULT = 1     # 自定义/未登记的模板：只要求"有文本"

DEFAULT_API = 'https://v3-api.wows.shinoaki.com'

# 测试账号 / 船（公开接口，不需要 token）
ACCOUNT = {'server': 'asia', 'accountId': '2022515210'}
SHIP_ID = '4179539728'
CLAN_ID = '2000022706'

# 内置用例：模板 ← 接口 + 参数
#   endpoint 里的 {xxx} 由 path_params 填；params 是查询串；
#   after 指向 AFTER_HOOKS：**复刻 feature 层对接口数据做的变换**（不是接口原样喂给模板）。
BUILTIN_CASES = [
    {
        'name': '用户信息页',
        'template': 'wws-info-v6.html',
        'endpoint': '/public/wows/account/user/info2',
        'params': dict(ACCOUNT),
        'search': '/public/wows/account/search/db/{accountId}',
    },
    {
        'name': '公会信息页',
        'template': 'wws-clan-v6.html',
        'endpoint': '/public/wows/clan/info',
        'params': {'server': ACCOUNT['server'], 'accountId': CLAN_ID},
        'after': 'latest_season',   # 复刻 features/clan/info.py 的注入
    },
    {
        'name': '单船页',
        'template': 'wws-ship-v6.html',
        'endpoint': '/public/wows/account/ship/info',
        'params': {**ACCOUNT, 'shipId': SHIP_ID},
        'after': 'ship_rank',   # 复刻 features/ship/info.py 的 result['data']['shipRank'] = rank
    },
    {
        'name': '单船排行榜',
        'template': 'ship-rank-v6.html',
        'endpoint': '/public/rank/yuyuko_ship/{server}',
        'path_params': {'server': ACCOUNT['server']},
        'params': {'shipId': SHIP_ID, 'page': 1},
        'after': 'ship_rank_page',   # 复刻 features/ship/rank.py 的 {'data','shipInfo'}
    },
    {
        'name': '军团战排行榜',
        'template': 'cw-rank-v6.html',
        'endpoint': '/public/wows/clan/rank/cw',
        'params': {'season': 0, 'server': 'global', 'page': 1, 'size': 100},
        'after': 'cw_rank',   # 复刻 features/clan/cw_rank.py 的 {'data','server','season'}
    },
    {
        'name': '战舰列表',
        'template': 'wws-ships-v6.html',
        'endpoint': '/public/wows/account/ship/info/query_list',
        'params': {**ACCOUNT, 'shipType': '', 'country': '', 'level': '', 'min': 0, 'max': 0},
        'after': 'ships_list',   # 复刻 features/account/ships.py 的 _normalize_ship_list + filter 描述
    },
    {
        'name': '圣诞箱船池',
        'template': 'wws-box-christmas-v6.html',
        'endpoint': '/public/wows/christmas/ship/box',
        'params': dict(ACCOUNT),
    },
    {
        'name': '扫雪收益',
        'template': 'wws-sx-v6.html',
        'endpoint': '/public/wows/christmas/ship/christmas',
        'params': dict(ACCOUNT),
    },
    # ---- 私有接口（/api/...，需要 HIKARI_TOKEN；没设 token 时整条跳过，不算失败）----
    {
        'name': '近期战绩（随机+排位）',
        'template': 'wws-info-recent-v6.html',
        'endpoint': '/api/wows/recent/day/info',
        'params': {**ACCOUNT, 'dateTime': '{today}', 'day': 7, 'shipId': 0},
        'requires_token': True,
    },
    {
        'name': '近期随机',
        'template': 'wws-info-recent-random-v6.html',
        'endpoint': '/api/wows/recent/day/info',
        'params': {**ACCOUNT, 'dateTime': '{today}', 'day': 7, 'shipId': 0},
        'requires_token': True,
    },
    {
        # ⚠ 这是**退化用例**：该账号近 90 天没有排位战绩，feature 实际不会选这个模板
        #   （它会走 recent 的「排位无数据」分支）。这里仍然拿同一份数据喂给 -rank 模板，
        #   只为验证「同一份数据下两个引擎渲染等价」，不代表真实排位数据。
        'name': '近期排位（退化：无排位战绩数据）',
        'template': 'wws-info-recent-rank-v6.html',
        'endpoint': '/api/wows/recent/day/info',
        'params': {**ACCOUNT, 'dateTime': '{today}', 'day': 90, 'shipId': 0},
        'requires_token': True,
    },
    {
        # 单船近期要一条「该账号这段时间真打过的船」，船号由 after_hook 现场取
        'name': '单船近期',
        'template': 'wws-ship-recent-v6.html',
        'after': 'ship_recent',
        'requires_token': True,
    },
    {
        'name': '单场近期',
        'template': 'wws-info-recents-v6.html',
        'endpoint': '/api/wows/recents/day/info',
        'params': {**ACCOUNT, 'dateTime': '{today}', 'day': 1, 'shipId': 0},
        'requires_token': True,
    },
    # ⚠ 以下模板**仍然没有用例**，原因都是「取不到这份数据」，不是来不及写：
    #   · wws-clan-cw-v6 的 /public/wows/clan/battle/info：对着**排行榜上真有军团战记录的
    #     军团**（season 也按排行榜给的值传）依然 data=null，接口这层就没数据；
    #   · wws-ban-v6 / wws-unban-v6 需要**真的被封禁**的国服账号（随手取的 id 一律 404
    #     「用户信息不存在」）；
    #   · select-clan / select-ship / bind-list / help-* 是纯选择列表，数据来自
    #     指令层的 Select_Data，接口直取即可，但它们的模板改写量为 0（编译检查足够）。
]


# ============================================================
# 一、加载 core 下的真实模块（不执行 hikari_core/__init__.py）
# ============================================================
def load_core_modules():
    """用「假包」把 hikari_core/core 当普通包加载。

    ▍为什么不直接 ``from hikari_core.core import js_render``：
      ``hikari_core/__init__.py`` 会 import Html_Render → playwright 等重依赖，
      门禁脚本应该只依赖 pillow + 一个本机浏览器就能跑。
      这里给 core 目录注册一个假包名，relative import（``from .constants import …``）
      照常解析，拿到的仍是**仓库里那份真代码**。
    """
    pkg_name = 'hikari_guard_pkg'
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(CORE)]
    sys.modules[pkg_name] = pkg
    importlib.invalidate_caches()
    return (
        importlib.import_module(f'{pkg_name}.constants'),
        importlib.import_module(f'{pkg_name}.render_helpers'),
        importlib.import_module(f'{pkg_name}.js_render'),
    )


# ============================================================
# 二、组装外壳（渲染发生在浏览器里）
# ============================================================
def render_js(js_render, template, data, template_dir):
    """只组装外壳 HTML —— 真正的渲染发生在浏览器里。"""
    return js_render.render_shell(
        template, data,
        root=template_dir,
        template_path_uri=template_dir.as_uri(),
        frozen_time=FROZEN_TIME,
    )


# ============================================================
# 三、无头浏览器
# ============================================================
def find_browser():
    override = os.environ.get('HIKARI_CHROME')
    if override and Path(override).exists():
        return override
    candidates = [
        r'C:/Program Files/Google/Chrome/Application/chrome.exe',
        r'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
        r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
        '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise SystemExit('找不到浏览器，请用环境变量 HIKARI_CHROME 指定可执行文件路径')


BROWSER = None


def chrome(args):
    return subprocess.run([BROWSER, *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def dump_dom(html_path: Path) -> str:
    """在无头浏览器里打开并取回渲染后的 DOM。

    ▍**取文本要走 DOM、不要抓原始 HTML 串**：外壳页面里内联着整份模板源码与数据，
      按标签粗暴切分会把它们/属性值当成"可见文本"，段数统计直接失真。
      过一遍浏览器只留真实渲染出来的节点，才和用户看到的是一回事。
    """
    return chrome(['--headless=new', '--disable-gpu', '--no-sandbox',
                   '--window-size=1560,900', '--virtual-time-budget=20000',
                   '--dump-dom', html_path.as_uri()]).stdout


def render_in_browser(html_path: Path):
    """在无头浏览器里打开并取回渲染后的 DOM，顺带把渲染器的报错捞出来。"""
    dom = dump_dom(html_path)
    # 渲染失败时 hikari-render.js 会把原因写进 #hikari-render-error（出错时页面不是白屏，
    # 而是带错误文本的页面），直接读它比翻控制台省事。
    hit = re.search(r'<pre id="hikari-render-error"[^>]*>([\s\S]*?)</pre>', dom)
    if hit:
        raise RuntimeError('浏览器端渲染失败: ' + re.sub(r'\s+', ' ', hit.group(1))[:300])
    return dom


def probe_render_done(shell_path: Path) -> str:
    """读出外壳页面里的 `window.__hikari_render_done` —— **截图服务等的就是它**。

    ▍为什么要单独探一探：截图服务（minimal_screens_hot_service）在任何等待之前会
      `wait_for_function('() => window.__hikari_render_done !== undefined')`，
      这个标记没被置上就会白等 15 秒然后截到空壳。门禁里其它检查都只看 DOM，
      看不到它，所以这里直接问浏览器要。
    ▍做法：用 `--allow-file-access-from-files` 把外壳放进 iframe，包装页就能读到
      它的 window（默认 file:// 之间是跨源的，读不到）。
    """
    page = shell_path.with_name('_flag_' + shell_path.name)
    page.write_text(
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
        f'<iframe id="f" src="{shell_path.as_uri()}" style="width:1400px;height:800px;border:0"></iframe>'
        '<script>var t=0;var h=setInterval(function(){t++;'
        'var w=document.getElementById("f").contentWindow;'
        'try{if(w&&w.__hikari_render_done!==undefined){clearInterval(h);'
        'document.title="FLAG::"+w.__hikari_render_done;}}'
        'catch(e){clearInterval(h);document.title="FLAG::err:"+e.message;}'
        'if(t>80){clearInterval(h);document.title="FLAG::timeout";}},250);</script>'
        '</body></html>', encoding='utf-8')
    try:
        dom = chrome(['--headless=new', '--disable-gpu', '--no-sandbox',
                      '--allow-file-access-from-files', '--window-size=1400,900',
                      '--virtual-time-budget=30000', '--dump-dom', page.as_uri()]).stdout
    finally:
        page.unlink(missing_ok=True)
    hit = re.search(r'<title>FLAG::(.*?)</title>', dom)
    return hit.group(1) if hit else '(探针没跑起来)'


def measure_height(html_path: Path) -> int:
    """量整页高度。

    ▍选择器要**按顺序回退**：不同模板的根容器不一样（info 系是 `.main-content`，
      ship-rank 是 `.page-box`），只认一个的话另一类模板直接量不到 → 逐像素比不了。
      最后兜底用文档滚动高度，任何模板都能量出来。
    """
    probe = ("<script>window.addEventListener('load',function(){setTimeout(function(){"
             "var m=document.querySelector('.main-content')||document.querySelector('.page-box');"
             "var h=m?Math.round(m.getBoundingClientRect().height)"
             ":Math.max(document.body.scrollHeight,document.documentElement.scrollHeight);"
             "document.title='H='+h;},1500);});</script>")
    probed = html_path.with_name('_h_' + html_path.name)
    probed.write_text(html_path.read_text(encoding='utf-8').replace('</body>', probe + '</body>'),
                      encoding='utf-8')
    try:
        dom = chrome(['--headless=new', '--disable-gpu', '--no-sandbox', '--window-size=1560,900',
                      '--virtual-time-budget=20000', '--dump-dom', probed.as_uri()]).stdout
    finally:
        probed.unlink(missing_ok=True)
    hit = re.search(r'<title>H=(\d+)</title>', dom)
    return int(hit.group(1)) if hit else -1


# 生产截图服务在截图前会注入「禁用动画」的样式（ECharts 默认带动画，否则可能截到
# 动画中间帧 → 图表区域出现假差异）。门禁必须同样处理，才和生产一致。
_NO_ANIMATION = ("<style>*,*::before,*::after{animation:none !important;"
                 "transition:none !important;}</style>")


def screenshot(html_path: Path, png_path: Path, height: int):
    """截一张图。

    ▍**先空拍一张预热，再拍正式那张**，并且所有截图共用一个持久化 profile
      （`_chrome_profile`，留着 HTTP 缓存）。原因：列表页有上百张远程缩略图，
      冷缓存下「图还没回来」和「图已回来」会拍出两张完全不同的图 ——
      实测同一个文件连拍两次能差 47 万像素，差异全在图片那一列，
      看着像模板坏了，其实只是加载竞态。热缓存下同一文件连拍两次是 0 差异。
    """
    probed = html_path.with_name("_s_" + html_path.name)
    probed.write_text(html_path.read_text(encoding='utf-8').replace(
        '</head>', _NO_ANIMATION + '</head>'), encoding='utf-8')
    warm = png_path.with_name('_warm_' + png_path.name)
    try:
        for target in (warm, png_path):
            chrome(['--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                    f'--user-data-dir={CHROME_PROFILE}',
                    f'--window-size=1560,{height + 20}', '--virtual-time-budget=30000',
                    f'--screenshot={target}', probed.as_uri()])
    finally:
        probed.unlink(missing_ok=True)
        warm.unlink(missing_ok=True)


# ============================================================
# 四、文本自检（段数下限）
# ============================================================
def visible_text_segments(html: str):
    """剥掉 script / style / 标签，返回可见文本段列表（顺序保留）。

    ▍入参是**浏览器序列化出来的 DOM**（两侧都过了 `dump_dom`，见那里的说明），
      所以先做一次字符引用反解、再把连续空白压成一个空格 —— 把「序列化」这一层
      噪声抹掉，剩下的差异才是真的文本差异。
    """
    body = re.sub(r'<script[\s\S]*?</script>', '', html)
    body = re.sub(r'<style[\s\S]*?</style>', '', body)
    segments = [s.strip() for s in re.sub(r'<[^>]+>', '\n', body).split('\n') if s.strip()]
    return [html_module.unescape(re.sub(r'\s+', ' ', s)) for s in segments]


def run_case(case, helpers, js_render, keep: bool, template_dir: Path):
    """跑单个用例：**只渲染 Nunjucks 那一侧**，然后做冒烟检查。

    返回 (是否通过, 明细行列表)。检查项见模块头：完成标记 / 无错误框 / 页高 / 文本段下限。
    """
    template = case['template']
    lines = []

    # 数据已由 fetch_case_data 拉取并套过 feature 层的变换（AFTER_HOOKS）
    data = case['data']
    helpers.enrich_banner_dark(data)
    helpers.enrich_poster_dark(data)

    shell = render_js(js_render, template, data, template_dir)
    if 'hikari-payload' not in shell:
        return False, ['外壳里没有内联载荷']

    workdir = TMP / re.sub(r'[^0-9A-Za-z]+', '_', template.replace('.html', ''))
    workdir.mkdir(parents=True, exist_ok=True)
    shell_path = workdir / 'shell.html'
    shell_path.write_text(shell, encoding='utf-8')

    # 1) 浏览器里渲染并取回 DOM（渲染器报错会写进 #hikari-render-error，这里直接抛）
    try:
        dom = render_in_browser(shell_path)
    except RuntimeError as err:
        return False, [f'浏览器渲染失败: {err}']

    # 2) 截图服务等的那个标记（没置上 → 生产会白等 15s 截到空壳）
    flag = probe_render_done(shell_path)
    flag_ok = flag == 'true'
    lines.append(f'渲染完成标记 __hikari_render_done: {flag}' + ('  ✓' if flag_ok else '  ✗'))

    # 3) 文本段数下限：拦「整块内容静默消失」
    segments = visible_text_segments(dom)
    floor = MIN_SEGMENTS.get(template, MIN_SEGMENTS_DEFAULT)
    text_ok = len(segments) >= floor
    lines.append(f'文本段: {len(segments)}（下限 {floor}）' + ('  ✓' if text_ok else '  ✗'))

    # 4) 页高探针（量不到根容器说明结构变了）
    height = measure_height(shell_path)
    height_ok = height > 0
    lines.append(f'页高: {height}' + ('  ✓' if height_ok else '  ✗（探针没量到根容器）'))

    # 5) 出图（人看用；--keep 才留）
    if height_ok:
        screenshot(shell_path, workdir / 'shell.png', height)

    if keep:
        lines.append(f'产物保留在: {workdir}')
    else:
        for name in ('shell.html', 'shell.png'):
            (workdir / name).unlink(missing_ok=True)

    return (flag_ok and text_ok and height_ok), lines


def fetch_json(url: str, params=None, method: str = 'GET', body=None):
    """拉一个接口并解析 JSON（请求头复刻生产客户端）。

    私有 `/api/...` 接口要真 token —— 见模块头的 HIKARI_TOKEN；公开用例不需要它。
    """
    if params:
        url = url + '?' + urllib.parse.urlencode(params)
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Yuyuko-Client-Type': 'BOT;js_render_guard',
    }
    if TOKEN:
        headers['Authorization'] = TOKEN
    payload = json.dumps(body).encode('utf-8') if body is not None else None
    request = urllib.request.Request(url, headers=headers, data=payload, method=method)
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _normalize_ship_list(data) -> list:
    """复刻 features/account/ships.py 的容器归一（value / list / shipInfoBattleList）。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('value', 'list', 'shipInfoBattleList'):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def _after_ship_rank_page(case, data, api):
    """复刻 features/ship/rank.py：`{'data': 排行榜, 'shipInfo': 图鉴信息}`。

    图鉴信息另外取：排行榜接口本身不带船名/图。imgSmall 缺失时按静态资源命名规则合成
    （渲染时 find_and_modify_shipinfo 会换成本地缓存路径）。
    """
    payload = fetch_json(api + '/public/wows/account/ship/info',
                         {**ACCOUNT, 'shipId': case['params']['shipId']})
    ship_info = dict(payload['data']['shipInfo'])
    server_type = str(ship_info.get('serverType') or '').lower()
    if not ship_info.get('imgSmall') and server_type and ship_info.get('shipId'):
        ship_info['imgSmall'] = (f'{api}/nahida-static/ship_cache/'
                                f'{server_type}-{ship_info["shipId"]}-small.png')
    return {'data': data, 'shipInfo': ship_info}


def _after_cw_rank(case, data, api):
    """复刻 features/clan/cw_rank.py：`{'data','server','season'}`。"""
    return {'data': data, 'server': case['params']['server'], 'season': case['params']['season']}


def _after_ships_list(case, data, api):
    """复刻 features/account/ships.py：容器归一 + 筛选条件描述。"""
    ship_list = _normalize_ship_list(data)
    return {
        'list': ship_list,
        'filter': {'shipType': '', 'country': '', 'level': '', 'min': 0, 'max': 0, 'desc': '全部'},
        'userInfo': data.get('userInfo') if isinstance(data, dict) else None,
        'battleTypeInfo': data.get('battleTypeInfo') if isinstance(data, dict) else None,
    }


def _after_ship_recent(case, data, api):
    """单船近期：复刻 features/ship/recent.py。

    ▍接口对「这段时间没打过的船」直接 412（当前日期无 recent 记录），所以船号不能写死 ——
      从近期战绩的 shipInfoBattleList 里现场取第一条真打过的船，再请求单船那份。
      （这个用例没有 endpoint，整份数据都由这里取。）
    """
    today = datetime.date.today().isoformat()
    base = {**ACCOUNT, 'dateTime': today, 'day': 7, 'shipId': 0}
    recent = fetch_json(api + '/api/wows/recent/day/info', base)
    ship_id = 0
    for row in recent['data'].get('shipInfoBattleList') or []:
        ship_id = (row.get('shipInfo') or {}).get('shipId') or 0
        if ship_id:
            break
    payload = fetch_json(api + '/api/wows/recent/day/list/info', {**base, 'shipId': ship_id})
    if payload.get('code') != 200 or not payload.get('data'):
        raise RuntimeError(f'单船近期取数失败: code={payload.get("code")} '
                           f'{payload.get("message")}（shipId={ship_id}）')
    return payload['data']


# feature 层对接口数据的变换（用例里的 'after' 指向这里）。**不是接口原样喂给模板**。
AFTER_HOOKS = {
    # features/ship/info.py：result['data']['shipRank'] = result['data']['rank']
    'ship_rank': lambda case, data, api: {**data, 'shipRank': data['rank']},
    'ship_recent': _after_ship_recent,
    # features/clan/info.py：把当前赛季注入数据（模板读 data['latest_season']）
    'latest_season': lambda case, data, api: {
        **data, 'latest_season': str(data['clanLeagueInfo']['lastSeason'])},
    'ship_rank_page': _after_ship_rank_page,
    'cw_rank': _after_cw_rank,
    'ships_list': _after_ships_list,
}


def fetch_case_data(case, api: str):
    """按用例配置拉真实数据（data-file 优先），再套上 feature 层的变换。"""
    if case.get('data_file'):
        # utf-8-sig：Windows 上 PowerShell/记事本存的 JSON 常带 BOM，用 utf-8 直接解析会报错
        data = json.loads(Path(case['data_file']).read_text(encoding='utf-8-sig'))
    elif not case.get('endpoint'):
        data = None          # 整份数据交给 after_hook 自己取（如单船近期要现场选船号）
    else:
        params = dict(case.get('params') or {})
        today = datetime.date.today().isoformat()
        for key, value in list(params.items()):
            if isinstance(value, str) and '{today}' in value:
                params[key] = value.replace('{today}', today)
        if case.get('search'):
            # 有些接口要先用昵称/id 换出正确的 server，再带着它请求（复刻生产调用顺序）
            found = fetch_json(api + case['search'].format(**params))
            if found.get('code') == 200 and found.get('data'):
                params['server'] = found['data'].get('server') or params['server']
        path = case['endpoint'].format(**(case.get('path_params') or {}))
        payload = fetch_json(api + path, params)
        if payload.get('code') != 200 or not payload.get('data'):
            raise SystemExit(f'{case["endpoint"]} 返回异常: '
                             f'code={payload.get("code")} {payload.get("message")}')
        data = payload['data']
    hook = AFTER_HOOKS.get(case.get('after'))
    return hook(case, data, api) if hook else data


def compile_all(template_dir: Path):
    """在浏览器里用本地 Nunjucks 逐个**编译**模板（不渲染、不需要数据、不需要浏览器以外的依赖）。

    ▍它是**最便宜的兜底**：语法错误、过滤器名写错、宏参数不匹配这类问题，
    编译阶段就会报，且不用等接口。语义类问题（少渲染一整块内容）交给上面那些数据用例。
    """
    templates = {}
    for path in sorted(list(template_dir.glob('*.html')) + list(template_dir.glob('partials/*.html'))):
        templates[path.relative_to(template_dir).as_posix()] = path.read_text(encoding='utf-8')
    payload = json.dumps({'templates': templates}, ensure_ascii=False).replace('<', '\\u003c')
    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">\n'
        f'<script src="{(template_dir / "nunjucks.min.js").as_uri()}"></script>\n'
        f'<script id="p" type="application/json">{payload}</script>\n'
        '<script>\n'
        'var tpls = JSON.parse(document.getElementById("p").textContent).templates;\n'
        'var env = new nunjucks.Environment({async:false, getSource:function(n){\n'
        '  return Object.prototype.hasOwnProperty.call(tpls,n)?{src:tpls[n],path:n,noCache:true}:null;}},'
        '{autoescape:false});\n'
        'var bad = [];\n'
        'for (var name in tpls) { try { env.getTemplate(name, true); } catch (e) {\n'
        '  bad.push(name + " :: " + String(e.message).split("\\n")[0]); } }\n'
        'document.title = "COMPILE::" + (bad.length ? bad.join(" ;; ") : "OK");\n'
        '</script></head><body></body></html>\n'
    )
    work = TMP / '_compile'
    work.mkdir(parents=True, exist_ok=True)
    page_path = work / 'compile.html'
    page_path.write_text(page, encoding='utf-8')
    dom = chrome(['--headless=new', '--disable-gpu', '--no-sandbox',
                  '--virtual-time-budget=20000', '--dump-dom', page_path.as_uri()]).stdout
    hit = re.search(r'<title>COMPILE::(.*?)</title>', dom, re.S)
    result = hit.group(1) if hit else '(探针没跑起来)'
    total = len(templates)
    if result == 'OK':
        print(f'编译检查: {total} 个模板全部通过  ✓')
        return True
    bad = [b.strip() for b in result.split(';;') if b.strip()]
    print(f'编译检查: {total} 个模板，{len(bad)} 个失败  ✗')
    for item in bad:
        print('   ' + item[:160])
    return False


def main():
    global BROWSER
    parser = argparse.ArgumentParser(description='浏览器端渲染冒烟测试（真的在浏览器里渲染一遍）')
    parser.add_argument('--template', help='只测这个模板（配合 --data-file）')
    parser.add_argument('--data-file', help='渲染数据 JSON（不填则打真实接口）')
    parser.add_argument('--api', default=DEFAULT_API, help='接口根地址')
    parser.add_argument('--template-dir', help='模板目录（默认仓库 Template/）')
    parser.add_argument('--list', action='store_true', help='列出内置用例后退出')
    parser.add_argument('--keep', action='store_true', help='保留中间产物便于排查')
    parser.add_argument('--compile-only', action='store_true',
                        help='只做全模板编译检查（不需要数据，用于还没有用例的模板）')
    args = parser.parse_args()

    if args.list:
        print('内置用例：')
        for case in BUILTIN_CASES:
            tags = []
            if case.get('after'):
                tags.append(f"after={case['after']}")
            if case.get('requires_token'):
                tags.append('需要 HIKARI_TOKEN')
            suffix = ('  [' + ' '.join(tags) + ']') if tags else ''
            print(f"  {case['template']:<28} {case['name']}{suffix}")
        return 0

    template_dir = Path(args.template_dir) if args.template_dir else TEMPLATE_DIR
    _constants, helpers, js_render = load_core_modules()
    TMP.mkdir(parents=True, exist_ok=True)
    BROWSER = find_browser()
    print(f'浏览器: {BROWSER}')
    print(f'JS 侧模板: {template_dir}')
    if args.compile_only:
        js_render.assert_assets(template_dir)
        ok = compile_all(template_dir)
        return 0 if ok else 1
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    print(f'截图 profile: {CHROME_PROFILE}（持久化 HTTP 缓存，避免远程图片加载竞态）')
    js_render.assert_assets(template_dir)

    cases = list(BUILTIN_CASES)
    if args.template:
        cases = [{'name': '自定义用例', 'template': args.template, 'data_file': args.data_file,
                  'endpoint': '', 'params': {}}]

    passed = 0
    skipped = 0
    for case in cases:
        print('=' * 72)
        print(f'用例: {case["name"]}  ←  {case["template"]}')
        print('=' * 72)
        if case.get('requires_token') and not TOKEN:
            # 私有 /api 接口要真 token。没设就**跳过而不是判失败** ——
            # 否则没有 token 的人跑门禁会看到一片 FAIL，误以为模板坏了。
            print('  跳过：这条用例走私有接口，需要环境变量 HIKARI_TOKEN\n')
            skipped += 1
            continue
        try:
            case['data'] = fetch_case_data(case, args.api)
        except SystemExit:
            raise
        except Exception as err:                       # noqa: BLE001
            print(f'  取数失败，跳过: {err}\n')
            skipped += 1
            continue
        ok, lines = run_case(case, helpers, js_render, args.keep, template_dir)
        for line in lines:
            print('  ' + line)
        print('  结果: ' + ('PASS' if ok else 'FAIL') + '\n')
        passed += ok

    total = len(cases)
    ran = total - skipped
    print('=' * 72)
    tail = f'（跳过 {skipped} 条）' if skipped else ''
    print(f'合计: {passed}/{ran} 通过{tail}')
    print('=' * 72)
    if ran == 0:
        # 别让「一条都没跑起来」看起来像通过（取数全失败时最容易这样）
        print('没有任何用例真正跑起来（全被跳过）—— 这不算通过')
        return 1
    return 0 if passed == ran else 1


if __name__ == '__main__':
    sys.exit(main())


# ============================================================
# TODO（想做更强的门禁时看这里）
# ============================================================
# 现在的检查是「冒烟级」：能拦住「渲染报错 / 整块内容消失 / 结构变了」，但拦不住
# 「某个数字格式变了」这类细粒度回归（那正是迁移期间逐像素比对能抓到的）。
# 想恢复那种强度、又不用 Jinja，正确做法是**固定数据 + 参考产物**：
#   1. 把各用例的接口响应存成 fixture（可按需裁剪条目数，别把 4MB 的列表页原样塞进仓库）；
#   2. 用例改为优先读 fixture，保证每次渲染的输入完全一致；
#   3. 存「参考指纹」（页高 + 文本段 sha256 + 截图缩略图 sha256），比对不过就 FAIL；
#   4. 提供 --update-golden 在**有意改动**后重刷参考值。
# 注意：拿真实接口数据做指纹是没用的 —— 账号战绩每天都在变，指纹每天都不同。
