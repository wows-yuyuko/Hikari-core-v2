import orjson
from loguru import logger

from ..config import hikari_config
from ..HttpClient_Pool import get_client_yuyuko
from ..http_error_handler import handle_yuyuko_errors
from ..model import Hikari_Model
from ..moudle.publicAPI import get_AccountIdByName
from ..moudle.wws_bind import get_DefaultBindInfo


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
    result = orjson.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200 and result['data']:
        hikari = hikari.set_template_info('wws-ban.html', 900, 100)
        return hikari.success(result['data'])
    elif result['code'] == 404 and result['data']:
        hikari = hikari.set_template_info('wws-unban.html', 900, 100)
        return hikari.success(result['data'])
    else:
        return hikari.failed(f"{result['message']}")
