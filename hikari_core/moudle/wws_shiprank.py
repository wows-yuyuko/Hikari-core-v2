import traceback
from asyncio.exceptions import TimeoutError

import orjson
from bs4 import BeautifulSoup
from httpx import ConnectTimeout, PoolTimeout
from loguru import logger

from ..config import hikari_config
from ..data_source import number_url_homes, set_ShipRank_Numbers
from ..HttpClient_Pool import get_client_default, get_client_yuyuko, recreate_client_default, recreate_client_yuyuko
from ..model import Hikari_Model
from .publicAPI import get_ship_byName


async def get_ShipRank(hikari: Hikari_Model):
    """查询单船排行榜"""
    try:
        if hikari.Status == 'init':
            shipList = await get_ship_byName(hikari)
            if shipList:
                if len(shipList) < 2:
                    hikari.Input.ShipInfo = shipList[0]
                else:
                    hikari.Input.Select_Data = shipList
                    hikari.set_template_info('select-ship-v3.html', 680, 100)
                    return hikari.wait(shipList)
            else:
                return hikari.failed('找不到船，请确认船名是否正确，可以使用【wws 查船名】查询船只中英文')
        elif hikari.Status == 'wait':
            if hikari.Input.Select_Data and hikari.Input.Select_Index and hikari.Input.Select_Index <= len(hikari.Input.Select_Data):
                hikari.Input.ShipInfo = hikari.Input.Select_Data[hikari.Input.Select_Index - 1]
            else:
                return hikari.error('请选择有效的序号')
        else:
            return hikari.error('当前请求状态错误')

        return await search_rank(hikari)
    except (TimeoutError, ConnectTimeout):
        logger.warning(traceback.format_exc())
        return hikari.error('请求超时了，请过会儿再尝试哦~')
    except PoolTimeout:
        await recreate_client_yuyuko()
        return hikari.error('连接池异常，请尝试重新查询~')
    except Exception:
        logger.error(traceback.format_exc())
        return hikari.error('wuwuwu出了点问题，请联系麻麻解决')



async def search_rank(hikari: Hikari_Model):
    try:
        url = f'{hikari_config.yuyuko_url}/public/rank/yuyuko_ship/{hikari.Input.Server}?shipId={hikari.Input.ShipInfo.shipId}&page=1'
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.get(url, timeout=20)
        result = orjson.loads(resp.content)
        if result['code'] == 200 and result['data']:
            hikari.set_template_info('ship-rank-v2.html', 1300, 100)
            result_data = {'data': result['data'], 'shipInfo': hikari.Input.ShipInfo.dict()}
            return hikari.success(result_data)
        else:
            return hikari.failed(f"{result['message']}")
    except (TimeoutError, ConnectTimeout):
        logger.warning(traceback.format_exc())
        return hikari.error('请求超时了，请过会儿再尝试哦~')
    except PoolTimeout:
        await recreate_client_yuyuko()
        return hikari.error('连接池异常，请尝试重新查询~')
    except Exception:
        logger.error(traceback.format_exc())
        return hikari.error('wuwuwu出了点问题，请联系麻麻解决')
