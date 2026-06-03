import orjson
from loguru import logger

from ..config import hikari_config
from ..HttpClient_Pool import get_client_yuyuko
from ..http_error_handler import handle_yuyuko_errors
from ..model import Hikari_Model


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
    result = orjson.loads(resp.content)
    if result['code'] == 200 and result['data']:
        return hikari.success(f"本次roll到了{result['data']['shipNameCn']}")
    else:
        return hikari.failed(f"{result['message']}")
