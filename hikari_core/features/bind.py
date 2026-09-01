import json
import traceback
from asyncio.exceptions import TimeoutError

from httpx import ConnectTimeout
from loguru import logger

from hikari_core.core.config import hikari_config
from hikari_core.core.http_client import get_client_yuyuko
from hikari_core.core.http_error_handler import handle_yuyuko_errors
from hikari_core.core.model import Hikari_Model
from hikari_core.core.template_registry import Templates
from hikari_core.features.api import get_AccountIdByName


@handle_yuyuko_errors()
async def get_BindInfo(hikari: Hikari_Model) -> Hikari_Model:
    """获取用户绑定信息"""
    if hikari.Status != 'init':
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/api/user/platform/bind/list'
    params = {'platformType': hikari.Input.Platform, 'platformId': hikari.Input.PlatformId}
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.get(url, params=params, timeout=20)
    result = json.loads(resp.content)
    if result['code'] == 200 and result['message'] == 'success':
        if result['data']:
            hikari = Templates.BIND_LIST.apply_to(hikari)
            return hikari.success(result['data'])
        else:
            return hikari.failed('该用户似乎还没绑定窝窝屎账号')
    else:
        return hikari.failed(f"{result['message']}")


@handle_yuyuko_errors()
async def set_BindInfo(hikari: Hikari_Model) -> Hikari_Model:
    """通过昵称绑定账号"""
    if hikari.Status == 'init':
        if hikari.Input.Search_Type == 3 and not hikari.Input.AccountId:
            hikari.Input.AccountId = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
            if not isinstance(hikari.Input.AccountId, int):
                return hikari.error(f'{hikari.Input.AccountId}')
    else:
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/api/user/platform/switch/bind'
    params = {'platformType': hikari.Input.Platform, 'platformId': hikari.Input.PlatformId, 'accountId': hikari.Input.AccountId}
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.post(url, json=params, timeout=20)
    result = json.loads(resp.content)
    if result['code'] == 200 and result['message'] == 'success':
        return hikari.success('绑定成功')
    else:
        return hikari.failed(f"{result['message']}")


# 防止混淆纯数字名与AID，单独添加特殊绑定指令
@handle_yuyuko_errors()
async def set_special_BindInfo(hikari: Hikari_Model) -> Hikari_Model:
    """通过AID绑定账号"""
    if hikari.Status != 'init':
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/api/user/platform/switch/bind'
    params = {'platformType': hikari.Input.Platform, 'platformId': hikari.Input.PlatformId, 'accountId': hikari.Input.AccountId}
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.post(url, json=params, timeout=20)
    result = json.loads(resp.content)
    if result['code'] == 200 and result['message'] == 'success':
        return hikari.success('绑定成功')
    else:
        return hikari.failed(f"{result['message']}")


@handle_yuyuko_errors()
async def change_BindInfo(hikari: Hikari_Model) -> Hikari_Model:
    """切换绑定"""

    if hikari.Status not in ['init', 'wait']:
        return hikari.error('当前请求状态错误')
    # 初次调用时无参数，返回输出选择列表
    if hikari.Status == 'init' and not hikari.Input.Select_Index:
        hikari = await get_BindInfo(hikari)
        # 成功获取绑定列表时置为wait，否则按原状态返回
        if hikari.Status == 'success':
            hikari.Status = 'wait'
            hikari.Input.Select_Data = hikari.Output.Data
        return hikari
    # 初次调用时或回调时有参数
    elif hikari.Input.Select_Index:
        # 初次调用时有选择序号，查询一次绑定列表
        if not hikari.Input.Select_Data:
            hikari.Status = 'init'
            hikari = await get_BindInfo(hikari)
            if not hikari.Status == 'success':
                return hikari
            hikari.Input.Select_Data = hikari.Output.Data
        if hikari.Input.Select_Index > len(hikari.Input.Select_Data):
            return hikari.error('请选择正确的序号')
        hikari.Input.AccountId = hikari.Input.Select_Data[hikari.Input.Select_Index - 1]['accountId']
        hikari.Status = 'init'
        # 切换绑定
        hikari = await set_BindInfo(hikari)
        if hikari.Status == 'success':
            return hikari.success(
                f"切换绑定成功,当前绑定账号{hikari.Input.Select_Data[hikari.Input.Select_Index - 1]['server']}：{hikari.Input.Select_Data[hikari.Input.Select_Index - 1]['userName']}"
            )


@handle_yuyuko_errors()
async def delete_BindInfo(hikari: Hikari_Model) -> Hikari_Model:
    """删除绑定"""
    if hikari.Status not in ['init', 'wait']:
        return hikari.error('当前请求状态错误')
    # 初次调用时无参数，返回输出选择列表
    if hikari.Status == 'init' and not hikari.Input.Select_Index:
        hikari = await get_BindInfo(hikari)
        # 成功获取绑定列表时置为wait，否则按原状态返回
        if hikari.Status == 'success':
            hikari.Status = 'wait'
            hikari.Input.Select_Data = hikari.Output.Data
        return hikari
    # 初次调用时或回调时有参数
    elif hikari.Input.Select_Index:
        # 初次调用时有选择序号，查询一次绑定列表
        if not hikari.Input.Select_Data:
            hikari.Status = 'init'
            hikari = await get_BindInfo(hikari)
            if not hikari.Status == 'success':
                return hikari
            hikari.Input.Select_Data = hikari.Output.Data
        if hikari.Input.Select_Index > len(hikari.Input.Select_Data):
            return hikari.error('请选择正确的序号')
        hikari.Input.AccountId = hikari.Input.Select_Data[hikari.Input.Select_Index - 1]['accountId']
        url = f'{hikari_config.yuyuko_url}/api/user/platform/remove/bind'
        params = {'platformType': hikari.Input.Platform, 'platformId': hikari.Input.PlatformId, 'accountId': hikari.Input.AccountId}
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.request('DELETE', url=url, json=params, timeout=20)
        result = json.loads(resp.content)
        if result['code'] == 200 and result['message'] == 'success':
            return hikari.success(
                f"删除绑定成功，删除的账号为{hikari.Input.Select_Data[hikari.Input.Select_Index - 1]['server']}：{hikari.Input.Select_Data[hikari.Input.Select_Index - 1]['userName']}"
            )
        else:
            return hikari.failed(f"{result['message']}")


@handle_yuyuko_errors()
async def get_DefaultBindInfo(hikari: Hikari_Model, platformType, platformId):
    """获取默认绑定账号
     Args:
        platformType (str):平台类型
        platformId (str):平台ID
    Returns:
        Dict:绑定用户信息
    """

    url = f'{hikari_config.yuyuko_url}/api/user/platform/bind/list'
    params = {
        'platformType': platformType,
        'platformId': platformId,
    }
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.get(url, params=params, timeout=20)
    result = json.loads(resp.content)
    if result['code'] == 200 and result['message'] == 'success':
        if result['data']:
            for each in result['data']:
                if each['defaultId']:
                    return each
        else:
            return None


@handle_yuyuko_errors()
async def update_user_cache(hikari: Hikari_Model) -> Hikari_Model:
    """更新用户缓存（wws me update 或 wws 服务器 游戏昵称 update）。

    提交格式参考 platform/bind/list：以 platformType + platformId 标识平台用户，
    并携带目标账号 server + accountId。
    me 模式更新默认绑定账号；服务器+昵称模式按昵称解析后更新指定账号。
    """
    if hikari.Status != 'init':
        return hikari.error('当前请求状态错误')

    # 目标账号：me → 默认绑定账号；服务器+昵称 → 按昵称解析 accountId
    if hikari.Input.Search_Type == 1:
        default_bind = await get_DefaultBindInfo(hikari, hikari.Input.Platform, hikari.Input.PlatformId)
        if not default_bind:
            return hikari.error('未找到默认绑定账号，请先使用 wws bind 服务器 游戏昵称 绑定，或 wws change_bind 切换')
        server = default_bind['server']
        account_id = default_bind['accountId']
        account_name = default_bind.get('userName', account_id)
    else:
        if not hikari.Input.Server or not hikari.Input.AccountName:
            return hikari.error('请使用 wws me update 或 wws 服务器 游戏昵称 update')
        account_id = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
        if not isinstance(account_id, int):
            return hikari.error(f'{account_id}')
        server = hikari.Input.Server
        account_name = hikari.Input.AccountName

    url = f'{hikari_config.yuyuko_url}/api/user/platform/cache/update'
    params = {
        'platformType': hikari.Input.Platform,
        'platformId': hikari.Input.PlatformId,
        'server': server,
        'accountId': account_id,
    }
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.post(url, json=params, timeout=20)
    result = json.loads(resp.content)
    if result['code'] == 200 and result['message'] == 'success':
        return hikari.success(f'已更新 {server}：{account_name} 的用户缓存')
    else:
        return hikari.failed(f"{result['message']}")
