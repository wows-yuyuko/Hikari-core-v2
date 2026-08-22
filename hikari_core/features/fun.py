"""娱乐类功能：封号查询 / 圣诞箱船池 / roll船 / 扫雪。

由原 ``hikari_core/game/`` 下的 ban_search / box_check / roll / sx 四个小文件合并而来。
"""

import json
from loguru import logger

from hikari_core.core.config import hikari_config
from hikari_core.core.http_client import get_client_yuyuko
from hikari_core.core.http_error_handler import handle_yuyuko_errors
from hikari_core.core.model import Hikari_Model
from hikari_core.core.template_registry import Templates
from hikari_core.features.api import get_AccountIdByName
from hikari_core.features.bind import get_DefaultBindInfo


@handle_yuyuko_errors()
async def get_BanInfo(hikari: Hikari_Model) -> Hikari_Model:
    """查询封禁匹配记录"""
    if hikari.Status == 'init':
        if hikari.Input.Search_Type == 3:
            hikari.Input.AccountId = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
            if not isinstance(hikari.Input.AccountId, int):
                return hikari.error(f'{hikari.Input.AccountId}')
        else:
            bindResult = await get_DefaultBindInfo(hikari, hikari.Input.Platform, hikari.Input.PlatformId)
            if bindResult:
                if bindResult['serverType'] == 'cn':
                    hikari.Input.AccountId = int(bindResult['accountId'])
                else:
                    return hikari.error('目前仅支持国服查询')
            else:
                return hikari.error('未查询到该用户绑定信息，请使用wws 查询绑定 进行检查')
    else:
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/public/wows/ban/cn/user'
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.post(url, json={'accountId': hikari.Input.AccountId}, timeout=20)
    result = json.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200 and result['data']:
        hikari = Templates.WWS_BAN.apply_to(hikari)
        return hikari.success(result['data'])
    elif result['code'] == 404 and result['data']:
        hikari = Templates.WWS_UNBAN.apply_to(hikari)
        return hikari.success(result['data'])
    else:
        return hikari.failed(f"{result['message']}")


@handle_yuyuko_errors()
async def check_christmas_box(hikari: Hikari_Model) -> Hikari_Model:
    """查询圣诞箱船池"""
    if hikari.Status == 'init':
        if hikari.Input.Search_Type == 3:
            hikari.Input.AccountId = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
            if not isinstance(hikari.Input.AccountId, int):
                return hikari.error(f'{hikari.Input.AccountId}')
    else:
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/public/wows/christmas/ship/box'
    if hikari.Input.Search_Type == 3:
        params = {'server': hikari.Input.Server, 'accountId': hikari.Input.AccountId}
    else:
        params = {'server': hikari.Input.Platform, 'accountId': hikari.Input.PlatformId}
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.get(url, params=params, timeout=20)
    result = json.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200 and result['data']:
        hikari = Templates.WWS_BOX_CHRISTMAS.apply_to(hikari)
        return hikari.success(result['data'])
    else:
        return hikari.failed(f"{result['message']}")


@handle_yuyuko_errors()
async def roll_ship(hikari: Hikari_Model):
    """roll船出港"""
    if not hikari.Input.ShipInfo.country:
        hikari.Input.ShipInfo.country = ''
    if not hikari.Input.ShipInfo.level:
        hikari.Input.ShipInfo.level = ''
    if not hikari.Input.ShipInfo.shipType:
        hikari.Input.ShipInfo.shipType = ''
    params = {
        'accountId': hikari.UserInfo.PlatformId,
        'server': hikari.UserInfo.Platform,
        'county': hikari.Input.ShipInfo.country,
        'level': hikari.Input.ShipInfo.level,
        'shipName': '',
        'shipType': hikari.Input.ShipInfo.shipType,
    }
    url = f'{hikari_config.yuyuko_url}/public/wows/roll/ship/roll'
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.post(url, json=params, timeout=20)
    result = json.loads(resp.content)
    if result['code'] == 200 and result['data']:
        return hikari.success(f"本次roll到了{result['data']['shipNameCn']}")
    else:
        return hikari.failed(f"{result['message']}")


@handle_yuyuko_errors()
async def get_sx_info(hikari: Hikari_Model) -> Hikari_Model:
    """查询扫雪收益"""
    if hikari.Status == 'init':
        if hikari.Input.Search_Type == 3:
            hikari.Input.AccountId = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
            if not isinstance(hikari.Input.AccountId, int):
                return hikari.error(f'{hikari.Input.AccountId}')
    else:
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/public/wows/christmas/ship/christmas'
    if hikari.Input.Search_Type == 3:
        params = {'server': hikari.Input.Server, 'accountId': hikari.Input.AccountId}
    else:
        params = {'server': hikari.Input.Platform, 'accountId': hikari.Input.PlatformId}
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.get(url, params=params, timeout=20)
    result = json.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200 and result['data']:
        hikari = Templates.WWS_SX.apply_to(hikari)
        return hikari.success(result['data'])
    else:
        return hikari.failed(f"{result['message']}")
