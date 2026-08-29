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

from .constants import template_path

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


async def set_render_params(List):
    try:
        enrich_banner_dark(List)
        result = {'template_path': template_path, 'data': List}
        return result
    except Exception:
        traceback.print_exc()
