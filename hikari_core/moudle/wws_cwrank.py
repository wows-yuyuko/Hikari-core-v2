import orjson
from loguru import logger

from ..config import hikari_config
from ..HttpClient_Pool import get_client_yuyuko
from ..http_error_handler import handle_yuyuko_errors
from ..model import Hikari_Model
from ..template_registry import Templates


@handle_yuyuko_errors()
async def get_CwRank(hikari: Hikari_Model) -> Hikari_Model:
    """查询军团战排行榜"""
    if hikari.Status == 'init':
        if not hikari.Input.Server:
            hikari.Input.Server = 'global'
    else:
        return hikari.error('当前请求状态错误')

    url = f'{hikari_config.yuyuko_url}/public/wows/clan/rank/cw'
    params = {
        'season': hikari.Input.CwSeasonId,
        'server': hikari.Input.Server,
        'page': 1,
        'size': 100,
    }
    client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
    resp = await client_yuyuko.get(url, params=params, timeout=20)
    result = orjson.loads(resp.content)
    hikari.Output.Yuyuko_Code = result['code']
    if result['code'] == 200 and result['data']:
        Templates.CW_RANK.apply_to(hikari)
        result_data = {'data': result['data'], 'server': hikari.Input.Server, 'season': hikari.Input.CwSeasonId}
        return hikari.success(result_data)
    else:
        return hikari.failed(f"{result['message']}")
