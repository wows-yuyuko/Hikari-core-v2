"""把渲染数据里的用户 / 军团头像、横幅、海报等**远程图片**落到本地缓存。

▍为什么需要这一层
  客户端不再请求服务端内联 base64（请求头里的 ``Base64UserInfoImg`` 已去掉），
  ``userInfo.avatar.{avatar,banner,poster}.data`` 这类槽位回到了**远程图片 URL**。
  直接交给浏览器有两个代价：
    · 截图进程必须真能访问那些 CDN（q.qlogo.cn / nahida-static / 用户自定义外链）；
    · 排行榜一页 50 个玩家 ×（头像 + 横幅 + dogTag）≈ 上百个远程请求，
      ``wait_until='networkidle'`` 很难平息，很容易把 ``goto`` 拖到超时。
  所以统一在 Python 侧先把 URL 落盘，再把字段替换成 ``file://`` 本地路径，
  浏览器只读本地文件 —— 与 ``shipInfo`` 走 ship_cache 是同一个思路。

▍目录布局（按归属者分目录，归属由 **URL 路径** 判定）
    <缓存>/user-cache/
      user-<accountId>/   用户图：路径形如 /nahida-static/avatar/<accountId>-…
                                        /nahida-static/root/<accountId>.png
      clan-<clanId>/      军团图：路径形如 /nahida-static/wows-clan/<clanId>-…
      _shared/            通用图（**不是上面三种路径的一律归这里**，集中一处）
                          例：nahida-static/avatar-template/wwn-banner.jpg（默认模板图）
                              wows.shinoaki.com/v2.jpg（全局默认海报）
                              q.qlogo.cn/headimg_dl?…（外链头像）

  ▍为什么必须按路径判而不是按"被几个人引用"猜：路径是**图片自身的属性**，同一次渲染里
    谁引用它、引用几次都不影响结论；按引用数猜会随数据漂移（同张图这次算独有、下次算共享）。
  ▍为什么要有 ``_shared``：实测排行榜一页 50 人里，``avatar-template/*`` 两张默认模板图
    被全 50 人共用。若给每人各存一份是 57 → 155 个文件（放大 2.7×），而它们本来就没人"拥有"。
  ▍查找顺序 ``<归属者>/`` → ``_shared/``：防归属判定变化导致的重复下载。

▍槽位的两种形状（**都只按父键/键名白名单识别，不靠值猜**）
  1. ``{'status': int, 'data': str}``，父键 avatar / banner / poster
     例：``data['userInfo']['avatar']['banner']['data']``；
  2. **裸字符串 URL**，键名 ``dogTag``
     例：``data['userInfo']['dogTag']`` → ``nahida-static/root/<accountId>.png``。
     ▍dogTag 是用户接口独有的**头像兜底图**，排行榜每行都在用它当图片
       （ship-rank-v6.html 的 background-image），很容易被漏掉。
  同一层的 ``colorName``（CSS 渐变串）、``sign``（签名文本）、
  ``glassmorphismCard``（"000-100" 这种档位串）**形状一样但不是图片**，靠值判断必然误伤。

▍文件名规则（两种，由 URL 决定）
  1. **默认：直接用 URL 里的原文件名**（``459948.png`` / ``2022515210-banner.jpg.jpg`` /
     ``wwn-banner.jpg`` / ``v2.jpg``）。没有 md5 前缀，看目录就知道是什么图。
     原文件名没有图片后缀时（如 ``headimg_dl``）才按响应内容补一个。
  2. **具名来源（见 ``_NAMED_SOURCES`` 注册表）**：``<来源>-<来源内 id>[-<变体>]<扩展名>``，
     例 ``qq-30436880-640.jpg``。
     ▍为什么这些要单独命名：QQ 头像的 URL 是 ``q.qlogo.cn/headimg_dl?dst_uin=…``，
       路径最后一段恒为 ``headimg_dl`` —— 全部用户同名，光看文件名认不出是谁的头像。
       id 取 URL 查询串里的 ``dst_uin``（QQ 号）：**只依赖 URL 本身**，与图片摆在数据里的
       位置无关，和「归属看 URL 路径」是同一条原则。``spec`` 一并写进名字，否则同一个人的
       不同尺寸（``spec=100`` / ``spec=640``）会互相覆盖、截出糊图。
     ▍加新平台（微信 / B站 / …）只需往 ``_NAMED_SOURCES`` 加一行，不用改其它逻辑。

  ▍不用 md5 前缀的前提（**往注册表加平台时要注意**）：同一个目录里不能有两个不同 URL
    用同一个文件名。用户 / 军团目录天然满足（原文件名里带 id，且一目录一人）；
    ``_shared`` 靠「服务端模板名固定」+「外部平台进 ``_NAMED_SOURCES``」来保证。
    真出现两个不同 URL 撞同名，是**静默取到错图**——排查时看 ``file://`` 路径对不上就知道了。

▍什么时候**不**下载（按 status 闸门，别白下用不到的图）
  槽位都是「模板按 ``status`` 决定画不画」，所以下载前先看一眼 status：
    · ``{status, data}`` 槽位（avatar / banner / poster）：**只在 ``status > 0`` 时下**。
      ``status == 0`` 表示这块不显示（公会侧那句注释就是这么写的：整块隐藏）——
      实测 ``clanInfo.avatar.avatar/banner`` 就是 status 0 却带着 URL。
    · ``dogTag``：它是「没有自定义头像」时的**回落图**，所以只在 ``avatar.status == 0``
      时才下（判据同用户信息页模板：``status > 0`` 就用 avatar 图、否则回落 dogTag；
      槽位缺席 / status 缺失按 0 算）。
      ▍排行榜行模板现在写的是 ``status == 2`` 才用 avatar 图（status == 1 也用 dogTag），
        与这里不一致；**排行榜那个不用管，模板后面会修**，所以这里仍按 ``== 0`` 判。
  ▍「跳过」= 不下载、不替换，**原 URL 原样留着**：模板真没画就用不到，画到了浏览器也能
    远程取到，所以这个闸门只省流量、不改观感。

▍缓存策略
  文件名 = ``md5(url)[:10]-<清洗过的原文件名><扩展名>`` —— **缓存键就是 URL**，
  命中不看内容、不比 hash、不发条件请求。是否还在有效期只看文件 mtime：
  ``now - mtime < TTL`` 算命中，否则重下并**原地覆盖同名文件**（不涨文件数）。
  TTL 走配置 ``hikari_config.user_image_cache_ttl_minutes``（**分钟**，默认 10080 = 7 天），
  ``<= 0`` = 永不过期。过期刷新失败时**继续用旧图**，而不是退回远程地址。

▍有意不做的事
  · **不碰 base64 / data: URL** —— 那是 ``enrich_banner_dark`` 的输入，提前转成文件会让
    「深色 banner 判白字」静默失效（不报错，只是颜色错）。
  · **不碰 shipInfo 的图片** —— 那走 ship_cache（见 ``find_and_modify_shipinfo``）。
  · **下载失败 / 拿回来的不是图片** → 有旧缓存就继续用旧图（过期图也比远程地址稳，
    截图机器不一定能访问那些 CDN），确实没有可用的才保留原 URL；缓存层坏掉不连累渲染。
"""

import asyncio
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlparse

import httpx
from loguru import logger

from .cache_utils import get_cache_file
from .config import hikari_config

# 缓存子目录名（与 ship_cache 同级，都在 get_cache_file() 下）
USER_CACHE_DIRNAME = 'user-cache'

# 没有归属者、或被多个归属者共用时的落点
SHARED_DIRNAME = '_shared'

# ▍「这张图属于某个用户 / 军团」的判据：**只看 URL 路径前缀**。
#   服务端的用户图只有这三种路径格式，其余（模板图、外链、默认海报）一律算通用图。
#   前缀按路径前缀匹配，与 host 无关（yuyuko_url 是配置项，可能换域名）。
#       /nahida-static/avatar/     <accountId>-*.jpg     用户头像 / 横幅
#       /nahida-static/root/       <accountId>.png       用户 dogTag 兜底图
#       /nahida-static/wows-clan/  <clanId>-*.jpg        军团头像 / 横幅
_USER_IMAGE_PATH_PATHS = (
    ('/nahida-static/avatar/', 'user'),
    ('/nahida-static/root/', 'user'),
    ('/nahida-static/wows-clan/', 'clan'),
)

# 路径里紧跟前缀的 id（如 2515210-banner.jpg.jpg / 2022515210.png）
_PATH_ID_RE = re.compile(r'(\d{3,})')

# 缓存存活时间的兜底默认值（分钟）；正常走 hikari_config.user_image_cache_ttl_minutes
DEFAULT_TTL_MINUTES = 10080  # 7 天

# {status, data} 形状的图片槽：只认这三个父键
_IMAGE_PARENT_KEYS = frozenset({'avatar', 'banner', 'poster'})

# 裸字符串 URL 的图片键（用户头像兜底图）
_FLAT_IMAGE_KEYS = frozenset({'dogTag'})

# 同时下载数：排行榜一页 50 个玩家最多上百张，8 路够快也不会把源站打疼
_MAX_CONCURRENCY = 8
_TIMEOUT = 20.0
_MAX_BYTES = 12 * 1024 * 1024  # 单张图超过 12MB 视为异常，不落盘

_URL_EXT_RE = re.compile(r'\.(?:png|jpe?g|gif|webp|bmp)$', re.I)
_UNSAFE_NAME_RE = re.compile(r'[^0-9A-Za-z_-]')

# ▍具名来源注册表：这些平台的头像不在 nahida-static 那三种路径下，但确实是「某人在某平台的头像」，
#   用可读的 ``<来源>-<来源内 id>[-<变体>]`` 命名，别让所有 QQ 头像都叫 ``headimg_dl``。
#   加新平台（微信 / B站 / …）在这里加一行即可。
#     元组含义：(来源名, 域名后缀, id 参数名, 要一并写进文件名的其它参数)
_NAMED_SOURCES = (
    ('qq', ('q.qlogo.cn',), 'dst_uin', ('spec',)),
)


def _is_remote_url(value) -> bool:
    return isinstance(value, str) and value.startswith(('http://', 'https://'))


def _bucket_name(owner: Optional[str]) -> str:
    """归属者 → 目录名。id 来自接口，必须清洗（不能让它带出 ``/`` 或 ``..``）。"""
    if not owner:
        return SHARED_DIRNAME
    safe = _UNSAFE_NAME_RE.sub('_', str(owner))[:64]
    return safe or SHARED_DIRNAME


def is_user_image_url(url: str) -> bool:
    """这张图是否属于某个用户 / 军团（即路径落在那三种格式里）。"""
    path = urlparse(url).path
    return any(path.startswith(prefix) for prefix, _ in _USER_IMAGE_PATH_PATHS)


def user_owner_from_url(url: str) -> Optional[str]:
    """从 URL 路径取出归属者（``user-<accountId>`` / ``clan-<clanId>``）。

    ▍为什么以 URL 为准而不是数据里的位置：路径里直接写着 id，是**图片自身的属性**；
      数据里的位置只说明"这次渲染把它画在谁身上"。取不到 id 时返回 None，
      调用方会退回数据里的最近祖先。
    """
    path = urlparse(url).path
    for prefix, kind in _USER_IMAGE_PATH_PATHS:
        if not path.startswith(prefix):
            continue
        hit = _PATH_ID_RE.match(path[len(prefix):])
        return f'{kind}-{hit.group(1)}' if hit else None
    return None


def iter_image_slots(data) -> Iterator[Tuple[Optional[str], dict, str]]:
    """递归产出 ``(归属者, 容器, 键名)``；就地改 ``容器[键名]`` 即可生效。

    归属者形如 ``user-2022515210`` / ``clan-2000022706``，取往上最近一个带
    ``accountId``（优先）或 ``clanId`` 的节点；都没有则为 None（→ ``_shared``）。
    """
    yield from _walk_slots(data, None)


def _walk_slots(obj, owner: Optional[str]):
    if isinstance(obj, dict):
        if obj.get('accountId') not in (None, ''):
            owner = f'user-{obj["accountId"]}'
        elif obj.get('clanId') not in (None, ''):
            owner = f'clan-{obj["clanId"]}'
        for key, value in obj.items():
            if key in _IMAGE_PARENT_KEYS and isinstance(value, dict) and 'data' in value:
                # status > 0 才会被模板画出来；status == 0 = 这块不显示，别白下
                if _slot_status(value) > 0:
                    yield owner, value, 'data'
            elif key in _FLAT_IMAGE_KEYS and isinstance(value, str):
                # dogTag 是「没有自定义头像」时的回落图，只有模板真会用到才下
                if _needs_dog_tag(obj):
                    yield owner, obj, key
            else:
                yield from _walk_slots(value, owner)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_slots(item, owner)


def _slot_status(slot) -> int:
    """``{status, data}`` 槽位的 status；槽位缺席 / 取不到 / 非数字一律当 0。"""
    if not isinstance(slot, dict):
        return 0
    try:
        return int(slot.get('status') or 0)
    except (TypeError, ValueError):
        return 0


def _needs_dog_tag(user_info) -> bool:
    """dogTag 还要不要下载 —— 只在「没有自定义头像」时下，即 ``avatar.status == 0``。

    判据取用户信息页模板的语义：``status > 0`` 才用 ``avatar.data``，否则回落 dogTag
    （槽位缺席 / status 缺失也按 0 处理 → 需要 dogTag）。
    ▍排行榜行模板目前写的是 ``status == 2`` 才用 avatar 图（也就是 status == 1 也用
      dogTag），与这里不一致 —— **排行榜那边不用管，模板后面会修**，所以这里只按
      ``== 0`` 判。在那个模板修好之前，status == 1 的排行榜行 dogTag 会退回远程加载。
    """
    avatar_box = user_info.get('avatar') if isinstance(user_info, dict) else None
    slot = avatar_box.get('avatar') if isinstance(avatar_box, dict) else None
    return _slot_status(slot) == 0


def _sniff_ext(raw: bytes) -> Optional[str]:
    """按魔数判断图片格式；不是已知图片返回 None（多半是错误页 / 防盗链 HTML）。"""
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if raw.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if raw[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return '.webp'
    if raw[:2] == b'BM':
        return '.bmp'
    return None


def _url_prefix(url: str) -> str:
    """URL 的 md5 前 10 位。

    ▍只用于**兼容改造前**的 md5 命名（查历史文件、清理遗留），新文件不再带这个前缀。
    """
    return hashlib.md5(url.encode()).hexdigest()[:10]


def _clean_basename(url: str) -> str:
    """URL 路径里的原文件名，清洗成合法文件名。

    ▍顺序：先取 basename（在**未解码**的路径上取）再 unquote。反过来先解码的话，
      文件名里若含 ``%2F`` 会凭空多出一个 ``/``、把路径带出目录。
      之后的正则会把 ``/`` 一并替换掉，所以这里不怕它。
    """
    base = os.path.basename(urlparse(url).path) or 'img'
    base = unquote(base)
    return re.sub(r'[^0-9A-Za-z._-]', '_', base)[:64] or 'img'


def named_source(url: str) -> Optional[str]:
    """具名来源 → 文件名主干（不含扩展名），如 ``qq-30436880-640``。

    不是具名来源、或 URL 里取不到 id 时返回 None（调用方走原文件名）。
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    query = dict(parse_qsl(parsed.query))
    for source, domains, id_key, extra_keys in _NAMED_SOURCES:
        if not any(host == d or host.endswith('.' + d) for d in domains):
            continue
        source_id = query.get(id_key)
        if not source_id:
            return None
        parts = [source, _UNSAFE_NAME_RE.sub('_', str(source_id))[:32]]
        for key in extra_keys:
            if query.get(key):
                parts.append(_UNSAFE_NAME_RE.sub('_', str(query[key]))[:16])
        # 注册表没声明的查询参数一律折成短哈希：宁可名字难看，也不能让两个不同 URL 撞名
        leftover = sorted((k, v) for k, v in query.items() if k != id_key and k not in extra_keys)
        if leftover:
            parts.append(hashlib.md5(repr(leftover).encode()).hexdigest()[:4])
        return '-'.join(parts)
    return None


def _name_stem(url: str) -> str:
    """文件名主干（不含扩展名）——查/清缓存用的 glob 就是 ``<主干>.*``。

    具名来源用 ``<来源>-<id>…``；否则用原文件名去掉一层图片后缀
    （``2022515210-banner.jpg.jpg`` → ``2022515210-banner.jpg``）。
    """
    stem = named_source(url)
    if stem:
        return stem
    return _URL_EXT_RE.sub('', _clean_basename(url)) or 'img'


def _file_name(url: str, ext: str) -> str:
    """URL + 实际内容扩展名 → 最终文件名。

    原文件名自带图片后缀就用它（**原样保留，不补第二个**）；没有才用响应内容推出来的 ext。
    """
    stem = named_source(url)
    if stem:
        return f'{stem}{ext}'
    base = _clean_basename(url)
    return base if _URL_EXT_RE.search(base) else f'{base}{ext}'


def _primary_pattern(url: str) -> str:
    """按**当前**命名规则查缓存用的 glob。

    ▍为什么要用「当前规则」而不是「历史规则全试一遍」：改名后若查找还兼容旧名，
      那份旧文件会被一直命中、永远不改名，缓存就成了「一半新名一半旧名」。
      旧名交给 ``_drop_siblings``（重下时清）和 ``_move_legacy_flat``（搬运时改名）收尾。
    """
    return f'{_name_stem(url)}.*'


def _all_patterns(url: str) -> Tuple[str, ...]:
    """当前 + 历史（md5）两种命名，用于**清理**同 URL 的重复/遗留文件。"""
    return (f'{_name_stem(url)}.*', f'{_url_prefix(url)}-*')


def _find_cached(dir_path: Path, url: str) -> Optional[Path]:
    """在指定目录里按 URL 找缓存文件（**不判新鲜度**）。"""
    if not dir_path.is_dir():
        return None
    return next(iter(dir_path.glob(_primary_pattern(url))), None)


def _is_fresh(path: Path, ttl_minutes: int) -> bool:
    """文件是否仍在有效期内（``ttl_minutes <= 0`` = 永不过期）。"""
    if ttl_minutes <= 0:
        return True
    try:
        age_minutes = (time.time() - path.stat().st_mtime) / 60
    except OSError:
        return False
    return age_minutes < ttl_minutes


def _move_legacy_flat(base_dir: Path, target_dir: Path, url: str) -> Optional[Path]:
    """把旧版平铺在 ``user-cache/`` 根下的文件搬进分目录，省一次重下。

    ▍分目录改造之前缓存是平铺的；用到时顺手搬走，比整目录重下文明。
    ▍搬运时按**当前命名规则**改名（旧的是 md5 命名，QQ 头像这类要变成 ``qq-…``），
      推导方式对 md5 命名是幂等的（算出来还是原名），所以只有需要换命名时才会真改名。
    """
    for old in base_dir.glob(f'{_url_prefix(url)}-*'):
        if not old.is_file():
            continue
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            new = target_dir / _file_name(url, old.suffix)
            old.replace(new)
            return new
        except OSError:
            return None
    return None


def _drop_siblings(dir_path: Path, url: str, keep: Path) -> None:
    """同一个目录里同一个 URL 只留一个文件（新旧两种命名都清）。

    ▍为什么需要：过期后重下时若源站换了图片格式（jpg → png），新文件名会和旧的不同
      （扩展名来自响应魔数），于是同前缀攒下两个文件；而 ``_find_cached`` 取的是
      glob 的第一个、顺序不保证 —— 不清掉就可能一直命中旧的那份。
      同时清 md5 命名的那份，是为了让改造前留下的 ``<md5>-headimg_dl.jpg``
      在换成 ``qq-…`` 命名后不会变成孤儿。
    """
    if not dir_path.is_dir():
        return
    for pattern in _all_patterns(url):
        for stale in dir_path.glob(pattern):
            if stale != keep:
                try:
                    stale.unlink()
                except OSError:
                    pass


def _drop_flat_duplicates(base_dir: Path, url: str) -> None:
    """清掉根目录下与分目录里**同一 URL** 的旧版平铺文件。

    ▍为什么：平铺时代留下的文件是「用到才搬走」。如果同一 URL 已经在分目录里存在
      （比如改造后又下载过一次），搬运就永远不会触发，那份平铺文件会一直留着当孤儿。
      前缀就是 URL 的 md5，所以命中前缀即同一个 URL，删掉不丢信息。
    """
    for dup in base_dir.glob(f'{_url_prefix(url)}-*'):
        if dup.is_file():
            try:
                dup.unlink()
            except OSError:
                pass


def _lookup(base_dir: Path, bucket: str, url: str, ttl_minutes: int) -> Tuple[Optional[Path], Optional[Path]]:
    """按 ``归属目录 → _shared`` 的顺序找；返回 ``(可用文件, 过期旧文件)``。

    两边都没找到时再试一次「旧版平铺文件搬迁」，命中就当作这个桶里的文件。
    """
    expired: Optional[Path] = None
    for dir_path in (base_dir / bucket, base_dir / SHARED_DIRNAME):
        hit = _find_cached(dir_path, url)
        if hit is None:
            continue
        if _is_fresh(hit, ttl_minutes):
            _drop_flat_duplicates(base_dir, url)
            return hit, None
        expired = expired or hit

    if expired is not None:
        return None, expired

    moved = _move_legacy_flat(base_dir, base_dir / bucket, url)
    if moved is None:
        return None, None
    return (moved, None) if _is_fresh(moved, ttl_minutes) else (None, moved)


async def _download_one(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                        target_dir: Path, url: str) -> Tuple[str, Optional[str]]:
    """下载一张图并返回 ``(原 URL, file:// 路径)``；失败返回 ``(原 URL, None)``。

    调用前应先用 ``_lookup`` 排除已有缓存的 URL（这里不再查缓存）。
    """
    async with sem:
        try:
            resp = await client.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            raw = resp.content
        except Exception as e:  # noqa: BLE001  单张图失败不该连累整页渲染
            logger.warning(f'用户图片下载失败: {url} ({type(e).__name__}: {e})')
            return url, None

    if not raw:
        logger.warning(f'用户图片内容为空: {url}')
        return url, None
    if len(raw) > _MAX_BYTES:
        logger.warning(f'用户图片超过 {_MAX_BYTES // 1024 // 1024}MB: {url}')
        return url, None

    ext = _sniff_ext(raw)
    if ext is None:
        # 拿回来的不是图片（错误页 / 防盗链）—— 不落盘，免得缓存里混进垃圾文件
        logger.warning(f'用户图片返回的不是图片（content-type={resp.headers.get("content-type")}）: {url}')
        return url, None

    path = target_dir / _file_name(url, ext)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except OSError as e:
        logger.warning(f'用户图片写入失败: {url} ({e})')
        return url, None
    _drop_siblings(target_dir, url, keep=path)
    logger.debug(f'用户图片已缓存: {path.parent.name}/{path.name} ({len(raw)} bytes)')
    return url, f'file:///{path.as_posix()}'


async def localize_user_images(data, *, cache_dir: Optional[Path] = None,
                               ttl_minutes: Optional[int] = None):
    """把 data 里 http(s) 的图片槽落到 ``<缓存>/user-cache/`` 并就地替换为本地路径。

    ▍落哪个目录由 **URL 路径** 决定：命中 ``/nahida-static/{avatar,root,wows-clan}/``
      的按 ``user-<accountId>`` / ``clan-<clanId>`` 分目录，其余一律进 ``_shared/``。
    ▍缓存怎么判：文件名里的 ``md5(url)[:10]`` 就是键，命中只看 URL；是否**还在有效期**
      由文件 mtime + TTL 决定：超过 TTL 就重新下载一次，**原地覆盖同名文件**
      （所以刷新不涨文件数、也不留旧副本）。``ttl_minutes <= 0`` = 永不过期。

    Args:
        data: 渲染数据（dict / list 皆可，递归处理）
        cache_dir: 自定义缓存目录，缺省 ``get_cache_file() / 'user-cache'``
        ttl_minutes: 覆盖配置里的存活时间（分钟）；缺省读
            ``hikari_config.user_image_cache_ttl_minutes``（默认 10080 = 7 天）

    Returns:
        dict: 同一个 data 对象（就地修改，方便与 find_and_modify_shipinfo 串起来）
    """
    entries = []                                  # (桶, URL, 容器, 键名)
    urls = set()
    for ancestor, container, key in iter_image_slots(data):
        url = container.get(key)
        if not _is_remote_url(url):
            continue
        if is_user_image_url(url):
            # 用户图：按归属者分目录（URL 里的 id 优先，取不到才用数据里的最近祖先）
            bucket = _bucket_name(user_owner_from_url(url) or ancestor)
        else:
            # 通用图（模板图 / 外链 / 默认海报）：集中一处，别给每个用户各存一份
            bucket = SHARED_DIRNAME
        entries.append((bucket, url, container, key))
        urls.add(url)
    if not entries:
        return data

    ttl = hikari_config.user_image_cache_ttl_minutes if ttl_minutes is None else ttl_minutes
    base_dir = cache_dir or (get_cache_file() / USER_CACHE_DIRNAME)
    base_dir.mkdir(parents=True, exist_ok=True)

    resolved: dict = {}                           # (桶, URL) -> file:// 路径
    pending: dict = {}                            # (桶, URL) -> 目标目录
    stale: dict = {}                              # (桶, URL) -> 过期旧文件
    for bucket, url, _, _ in entries:
        pair = (bucket, url)
        if pair in resolved or pair in pending:
            continue
        hit, expired = _lookup(base_dir, bucket, url, ttl)
        if hit is not None:
            resolved[pair] = f'file:///{hit.as_posix()}'
        else:
            pending[pair] = base_dir / bucket
            if expired is not None:
                stale[pair] = expired

    # 全部命中且都新鲜时不建客户端：httpx 初始化 SSL 上下文在 Windows 上要 1~2 秒，
    # 而这一层每次渲染都会走一遍，纯浪费
    if pending:
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)
        # 特意用裸客户端：这些图在第三方 CDN 上，绝不能把 yuyuko 的 Authorization 带出去
        async with httpx.AsyncClient(follow_redirects=True) as client:
            pairs = list(pending)
            fetched = await asyncio.gather(
                *(_download_one(client, sem, pending[pair], pair[1]) for pair in pairs)
            )
        for pair, (url, local) in zip(pairs, fetched):
            if local:
                resolved[pair] = local
            elif pair in stale:
                # 刷新失败（网络抖动 / 源站挂了）→ 用旧图，别退回远程地址
                logger.debug(f'用户图片刷新失败，继续用旧图: {stale[pair].parent.name}/{stale[pair].name}')
                resolved[pair] = f'file:///{stale[pair].as_posix()}'

    replaced = 0
    for bucket, url, container, key in entries:
        local = resolved.get((bucket, url))
        if local:
            container[key] = local
            replaced += 1
    unresolved = urls - {url for _, url in resolved}
    if unresolved:
        # 这几张最终只能让浏览器去远程取（多发生在源站挂了且本地又没旧图时）
        logger.debug(f'用户图片仍有 {len(unresolved)} 个未本地化，交给浏览器远程加载')
    logger.debug(f'用户图片本地化: {replaced}/{len(entries)} 个槽位，{len(urls)} 个唯一 URL，'
                 f'{len({b for b, _ in resolved})} 个目录（{base_dir}）')
    return data
