import orjson
from loguru import logger

from ..config import hikari_config
from ..HttpClient_Pool import get_client_yuyuko
from ..http_error_handler import handle_yuyuko_errors
from ..model import Hikari_Model
from ..moudle.publicAPI import get_AccountIdByName


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
    result = orjson.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200 and result['data']:
        hikari = hikari.set_template_info('wws-box-christmas.html', 920, 1000)
        return hikari.success(result['data'])
    else:
        return hikari.failed(f"{result['message']}")
