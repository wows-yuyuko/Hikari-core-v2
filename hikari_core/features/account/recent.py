import orjson
from loguru import logger

from hikari_core.core.config import hikari_config
from hikari_core.core.http_client import get_client_yuyuko
from hikari_core.core.http_error_handler import handle_yuyuko_errors
from hikari_core.core.model import Hikari_Model
from hikari_core.core.template_registry import Templates
from hikari_core.features.api import check_yuyuko_cache, get_AccountIdByName

# from nonebot_plugin_htmlrender import html_to_pic


@handle_yuyuko_errors()
async def get_RecentInfo(hikari: Hikari_Model) -> Hikari_Model:
    """查询Recent"""
    if hikari.Status == 'init':
        if hikari.Input.Search_Type == 3:
            hikari.Input.AccountId = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
            if not isinstance(hikari.Input.AccountId, int):
                return hikari.error(f'{hikari.Input.AccountId}')
    else:
        return hikari.error('当前请求状态错误')
    if hikari.Input.Search_Type == 3:
        is_cache = await check_yuyuko_cache(hikari, hikari.Input.Server, hikari.Input.AccountId)
    else:
        is_cache = await check_yuyuko_cache(hikari, hikari.Input.Platform, hikari.Input.PlatformId)
    if is_cache:
        logger.success('上报数据成功')
    else:
        logger.success('跳过上报数据，直接请求')
    url = f'{hikari_config.yuyuko_url}/api/wows/recent/day/info'
    if hikari.Input.Search_Type == 3:
        params = {
            'server': hikari.Input.Server,
            'accountId': hikari.Input.AccountId,
            'dateTime': hikari.Input.Recent_Date,
            'day': hikari.Input.Recent_Day,
            'shipId': 0,
        }
    else:
        params = {
            'server': hikari.Input.Platform,
            'accountId': hikari.Input.PlatformId,
            'dateTime': hikari.Input.Recent_Date,
            'day': hikari.Input.Recent_Day,
            'shipId': 0,
        }
    print(params)
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.get(url, params=params, timeout=20)
    result = orjson.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200:
        if result['data']['battleTypeInfo']['PVP']['battle'] or result['data']['battleTypeInfo']['RANK_SOLO']['battle']:
            hikari = Templates.WWS_INFO_RECENT.apply_to(hikari)
            return hikari.success(result['data'])
        else:
            return hikari.failed('该日期数据记录不存在')
    else:
        return hikari.failed(f"{result['message']}")
