import orjson
from loguru import logger

from ..config import hikari_config
from ..HttpClient_Pool import get_client_yuyuko
from ..http_error_handler import handle_yuyuko_errors
from ..model import Hikari_Model
from ..template_registry import Templates
from .publicAPI import get_AccountIdByName

# from nonebot_plugin_htmlrender import html_to_pic


@handle_yuyuko_errors()
async def get_RecentsInfo(hikari: Hikari_Model) -> Hikari_Model:
    """查询Recents"""
    if hikari.Status == 'init':
        if hikari.Input.Search_Type == 3:
            hikari.Input.AccountId = await get_AccountIdByName(hikari, hikari.Input.Server, hikari.Input.AccountName)
            if not isinstance(hikari.Input.AccountId, int):
                return hikari.error(f'{hikari.Input.AccountId}')
    else:
        return hikari.error('当前请求状态错误')
    url = f'{hikari_config.yuyuko_url}/api/wows/recents/day/info'
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
        hikari = Templates.WWS_INFO_RECENTS.apply_to(hikari)
        return hikari.success(result['data'])
    else:
        return hikari.failed(f"{result['message']}")
