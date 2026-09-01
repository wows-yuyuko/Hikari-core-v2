"""管理员校验与添加。

流程（SDK 接入端提示：建议走私信，详细说明见 docs/admin-guide.md）：
1. 机器人启动成功后，控制台输出 32 位随机校验串
   （由 ``generate_check_admin`` 生成，写入 get_cache_file()/checkAdmin.txt）；
2. 用户把校验串私信发送给机器人，接入端需保证私信消息也进入 init_hikari 指令流程；
3. 用户发送 ``wws add_admin <校验串>``，校验（``verify_check_admin``）通过后
   把发送者平台ID写入 get_cache_file()/admin.txt，并删除 checkAdmin.txt；
4. 再次启动时检测到 admin.txt 存在，则不再生成校验串。
"""

import secrets
import traceback
from pathlib import Path

from loguru import logger

from hikari_core.core.cache_utils import get_cache_file
from hikari_core.core.model import Hikari_Model

ADMIN_FILE = 'admin.txt'
CHECK_FILE = 'checkAdmin.txt'
TOKEN_LENGTH = 32  # 校验串字符数（十六进制）


def _admin_file() -> Path:
    return get_cache_file() / ADMIN_FILE


def _check_file() -> Path:
    return get_cache_file() / CHECK_FILE


def is_admin(platform_id) -> bool:
    """判断平台用户是否为管理员（admin.txt 中逐行保存的用户ID）。"""
    try:
        path = _admin_file()
        if not path.exists():
            return False
        target = str(platform_id).strip()
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() == target:
                return True
    except Exception:
        logger.error(traceback.format_exc())
    return False


def generate_check_admin() -> str:
    """生成 32 位随机校验串并写入 checkAdmin.txt（独立生成器）。

    仅当不存在 admin.txt 时生成；返回校验串，未生成时返回空串。
    """
    if _admin_file().exists():
        return ''
    token = secrets.token_hex(TOKEN_LENGTH // 2)  # 32 位十六进制随机串
    try:
        _check_file().write_text(token, encoding='utf-8')
    except Exception:
        logger.error(traceback.format_exc())
        return ''
    return token


def verify_check_admin(token) -> bool:
    """校验用户发送的校验串是否与 checkAdmin.txt 一致（独立校验函数，无副作用）。"""
    path = _check_file()
    if not path.exists():
        return False
    try:
        stored = path.read_text(encoding='utf-8').strip()
    except Exception:
        return False
    return bool(stored) and str(token).strip() == stored


def remove_check_admin() -> None:
    """验证成功后删除 checkAdmin.txt。"""
    try:
        _check_file().unlink(missing_ok=True)
    except Exception:
        logger.error(traceback.format_exc())


def add_admin_id(platform_id) -> bool:
    """将平台用户ID写入 admin.txt（追加去重）。"""
    try:
        path = _admin_file()
        ids = []
        if path.exists():
            ids = [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        target = str(platform_id).strip()
        if not target:
            return False
        if target not in ids:
            ids.append(target)
        path.write_text('\n'.join(ids) + '\n', encoding='utf-8')
        return True
    except Exception:
        logger.error(traceback.format_exc())
        return False


async def add_admin(hikari: Hikari_Model) -> Hikari_Model:
    """wws add_admin <32位校验串> —— 校验通过后把发送者添加为管理员（建议私信发送）。"""
    if hikari.Status != 'init':
        return hikari.error('当前请求状态错误')
    if not hikari.Input.Command_List:
        return hikari.error('请发送 wws add_admin <32位校验串>（建议通过私信发送给机器人）')
    token = str(hikari.Input.Command_List[0])
    if not verify_check_admin(token):
        return hikari.failed('校验串无效或已过期，请以机器人启动时控制台输出的最新校验串重试')
    if not add_admin_id(hikari.UserInfo.PlatformId):
        return hikari.error('管理员添加失败，请检查缓存目录写入权限')
    remove_check_admin()
    return hikari.success('管理员添加成功，现在可以使用 check_version / update_style / update_ship')
