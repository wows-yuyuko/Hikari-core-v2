"""渲染辅助函数。

原 ``hikari_core/data_source.py`` 的渲染辅助部分，数据常量见 ``core/constants.py``。
已移除 wows-numbers 爬虫函数（set_ShipRank_Numbers / search_accountId / search_color）
与无调用方的颜色辅助函数（select_prvalue_and_color / set_damageColor / set_winColor /
set_upinfo_color / set_clanRecord_params）。
"""

import base64
import hashlib
import io
import traceback

from PIL import Image

from .constants import servers, template_path

# 服务器别名 → 中文名。用户接口给的是 '亚服' 这类中文（原样返回），
# 公会接口给的是 'asia' 这类键名，头部公共组件要显示成和用户页一样的中文。
# 真值仍来自 constants.servers，不另立一份表。
_SERVER_CN = {
    alias.lower(): chinese
    for server in servers
    for chinese in [next((k for k in server.keywords if not k.isascii()), server.match_keywords)]
    for alias in server.keywords
}


def server_cn(value) -> str:
    """服务器键名 / 别名统一成中文名（asia → 亚服），未知值原样返回。"""
    if value is None:
        return ''
    text = str(value)
    return _SERVER_CN.get(text.lower(), text)


# banner 深色判定阈值：左 60% 区域平均感知亮度（Y=0.299R+0.587G+0.114B，0-255）
# 低于该值判定为深色（dark=1），模板将文字改为白色形成反差。
BANNER_DARK_THRESHOLD = 128.0

# 兜底计算结果的缓存（内容 md5 -> bool），避免同一 banner 每次渲染都重复解码
_BANNER_DARK_CACHE = {}
_BANNER_DARK_CACHE_MAX = 256


def _compute_banner_is_dark(data_url: str) -> bool:
    """解码 banner 图片，统计左 60% 区域的平均感知亮度，低于阈值视为深色。

    支持 data URL（``data:image/...;base64,...``）与裸 base64；
    解析/解码失败时按浅色处理，保持原有逻辑。
    """
    try:
        payload = data_url
        if payload.startswith('data:'):
            payload = payload.split(',', 1)[1]
        if not payload:
            return False
        raw = base64.b64decode(payload, validate=False)
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert('RGB')
            width, height = img.size
            if width <= 0 or height <= 0:
                return False
            # 只统计文字所在的左 60% 区域
            left = img.crop((0, 0, int(width * 0.6), height))
            left.thumbnail((48, 48))  # 缩小采样，降低计算量
            pixels = list(left.getdata())
        if not pixels:
            return False
        total = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels)
        return total / len(pixels) < BANNER_DARK_THRESHOLD
    except Exception:
        # 解析失败按浅色处理，保持原逻辑
        return False


def banner_is_dark(data_url: str) -> bool:
    """带缓存的 banner 深色判定（按内容 md5 缓存结果）。"""
    key = hashlib.md5(data_url.encode('utf-8', 'ignore')).hexdigest()
    if key in _BANNER_DARK_CACHE:
        return _BANNER_DARK_CACHE[key]
    result = _compute_banner_is_dark(data_url)
    if len(_BANNER_DARK_CACHE) >= _BANNER_DARK_CACHE_MAX:
        _BANNER_DARK_CACHE.clear()
    _BANNER_DARK_CACHE[key] = result
    return result


def enrich_banner_dark(data) -> None:
    """递归遍历渲染数据：为 ``status == 2`` 且未携带 ``dark`` 字段的 banner 补算深色标记。

    服务端已返回 ``dark``（0=浅色 / 1=深色）时优先采用服务端结果；
    模板按 ``banner.dark == 1`` 启用深色白字样式。
    """

    def _recurse(obj):
        if isinstance(obj, dict):
            banner = obj.get('banner')
            if isinstance(banner, dict) and banner.get('status') == 2 and 'dark' not in banner:
                data_url = banner.get('data')
                if isinstance(data_url, str) and data_url:
                    banner['dark'] = 1 if banner_is_dark(data_url) else 0
            for value in obj.values():
                _recurse(value)
        elif isinstance(obj, list):
            for item in obj:
                _recurse(item)

    _recurse(data)


# poster 的 dark 不是布尔而是一个 0-100 的**透明度**比例，语义是「越淡」。
# ▍服务端口径（已与服务器对齐，别改）：值就是「透明度」
#     0   = 完全不透明 → 背景图**完全显示**（最实）
#     100 = 完全透明   → 背景图**完全看不见**
#   0 / 100 是两端点，中间线性（50 = 半透明）。
# 与 banner 的 0/1 深色标记语义完全无关，两者不要混用。
# 缺省按 0（完全显示）——历史数据不带这个字段，等价于「保持原来的观感」。
POSTER_DARK_DEFAULT = 0
POSTER_DARK_MIN = 0
POSTER_DARK_MAX = 100


def _poster_dark_ratio(value) -> int:
    """把服务端给的 poster.dark 归一化到 0-100 的整数（透明度，越大越淡）。

    服务端语义：0 = 完全显示（不透明）/ 100 = 完全透明。这里原样保留该口径，
    只做「夹到 0-100 + 转 int」的收口，不翻转数值 —— 翻转发生在模板 / 预览里
    （它们要的是 CSS 不透明度，所以算 `100 - dark`）。

    缺省 / 非数字 / 解析失败一律回落到 0（完全显示）——历史数据不带这个字段，
    这么做等价于「保持原来的观感」。夹取保证脏数据不会写出非法 CSS。
    """
    if value is None or isinstance(value, bool):
        return POSTER_DARK_DEFAULT
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return POSTER_DARK_DEFAULT
    try:
        ratio = int(round(float(value)))
    except (TypeError, ValueError):
        return POSTER_DARK_DEFAULT
    return max(POSTER_DARK_MIN, min(POSTER_DARK_MAX, ratio))


def enrich_poster_dark(data) -> None:
    """递归遍历渲染数据：把 poster 的 ``dark`` 归一到 0-100 的透明度。

    模板侧只做「缺省按 0」的兜底，脏值（负数 / 超 100 / 字符串）由这里统一收口，
    归一化后仍是 int，可以直接参与数值比较。
    只处理 status > 0 的 poster —— 不显示的槽位归一化没有意义。
    """

    def _recurse(obj):
        if isinstance(obj, dict):
            poster = obj.get('poster')
            if isinstance(poster, dict) and poster.get('status') not in (None, 0):
                poster['dark'] = _poster_dark_ratio(poster.get('dark'))
            for value in obj.values():
                _recurse(value)
        elif isinstance(obj, list):
            for item in obj:
                _recurse(item)

    _recurse(data)


# ----------------------------------------------------------
# BA 风格文字 logo（公会没头像时用 tag 生成）用的字宽表
# ----------------------------------------------------------
# Microsoft YaHei Bold（msyhbd.ttc）在 100px 下的 advance 宽度换算成 em，逐字实测
# （组件 ba-logo-v6.css 的 font-family 第一顺位就是 Microsoft YaHei）。
# 表里没有的字符（CJK、日文等）一律按 1.0em 算 —— 东亚全角字本来就是 1em。
# 重新测量某个字：
#   python -c "from PIL import ImageFont; f=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',100); print(f.getlength('W')/100)"
_BA_EM = {
    "A": 0.75, "B": 0.68, "C": 0.67, "D": 0.79, "E": 0.57, "F": 0.56, "G": 0.77, "H": 0.82, "I": 0.34,
    "J": 0.47, "K": 0.69, "L": 0.55, "M": 1.03, "N": 0.85, "O": 0.82, "P": 0.66, "Q": 0.82, "R": 0.7,
    "S": 0.6, "T": 0.63, "U": 0.78, "V": 0.71, "W": 1.08, "X": 0.7, "Y": 0.65, "Z": 0.65, "a": 0.58,
    "b": 0.67, "c": 0.52, "d": 0.66, "e": 0.58, "f": 0.41, "g": 0.66, "h": 0.65, "i": 0.3, "j": 0.3,
    "k": 0.6, "l": 0.3, "m": 0.98, "n": 0.65, "o": 0.66, "p": 0.67, "q": 0.66, "r": 0.42, "s": 0.49,
    "t": 0.41, "u": 0.65, "v": 0.58, "w": 0.85, "x": 0.59, "y": 0.57, "z": 0.51, "0": 0.62, "1": 0.62,
    "2": 0.62, "3": 0.62, "4": 0.62, "5": 0.62, "6": 0.62, "7": 0.62, "8": 0.62, "9": 0.62, "-": 0.44,
    "_": 0.45, ".": 0.29, "/": 0.42, ":": 0.29, "+": 0.62, "!": 0.31, "?": 0.55, "&": 0.92, "'": 0.22,
    "\"": 0.42, "(": 0.33, ")": 0.33, "[": 0.33, "]": 0.33, "~": 0.62, "*": 0.5, "#": 0.62, "@": 1,
    ",": 0.29, ";": 0.29, "=": 0.62,
}


def ba_text_em(text: str) -> float:
    """估算一段文字在 Microsoft YaHei Bold 下的 advance 宽度（单位 em）。

    只给模板估 logo 尺寸 / 居中偏移用，不追求和浏览器逐像素一致；
    字表见 ``_BA_EM``，换字体（或换系统）时重测这张表即可。
    """
    return sum(_BA_EM.get(ch, 1.0) for ch in str(text))

async def set_render_params(List):
    try:
        enrich_banner_dark(List)
        enrich_poster_dark(List)
        result = {'template_path': template_path, 'data': List}
        return result
    except Exception:
        traceback.print_exc()
