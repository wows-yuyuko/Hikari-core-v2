import asyncio
import gzip
import traceback
from asyncio.exceptions import TimeoutError
from base64 import b64encode
from pathlib import Path
from typing import List

import httpx
import orjson
from bs4 import BeautifulSoup
from httpx import ConnectTimeout, PoolTimeout
from loguru import logger

from ..config import hikari_config
from ..data_source import number_url_homes
from ..HttpClient_Pool import (
    get_client_default,
    get_client_wg,
    get_client_yuyuko,
    recreate_client_default,
    recreate_client_wg,
    recreate_client_yuyuko,
)
from ..model import Hikari_Model, ShipInfo


async def get_nation_list(hikari: Hikari_Model):
    try:
        msg = ''
        url = f'{hikari_config.yuyuko_url}/public/wows/encyclopedia/nation/list'
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.get(url, timeout=20)
        result = orjson.loads(resp.content)
        for nation in result['data']:
            msg: str = msg + f"{nation['cn']}：{nation['nation']}\n"
        return msg
    except PoolTimeout:
        await recreate_client_yuyuko()
        return
    except Exception:
        logger.error(traceback.format_exc())


async def get_ship_name(hikari: Hikari_Model):
    """根据国家等级类型查船名"""
    msg = ''
    try:
        params = {
            'country': hikari.Input.ShipInfo.country,
            'level': hikari.Input.ShipInfo.level,
            'shipName': '',
            'shipType': hikari.Input.ShipInfo.shipType,
            'groupType': 'default',
        }
        url = f'{hikari_config.yuyuko_url}/public/wows/encyclopedia/ship/search'
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.get(url, params=params, timeout=20)
        result = orjson.loads(resp.content)
        if result['data']:
            for ship in result['data']:
                msg += f"{ship['nameCn']}：{ship['nameEnglish']}\n"
            return hikari.success(msg)
        else:
            return hikari.failed('没有符合的船只')
    except (TimeoutError, ConnectTimeout):
        logger.warning(traceback.format_exc())
        return hikari.error('请求超时了，请过会儿再尝试哦~')
    except PoolTimeout:
        await recreate_client_yuyuko()
        return hikari.error('连接池异常，请尝试重新查询~')
    except Exception as e:
        logger.error(traceback.format_exc())
        return hikari.error(f'wuwuwu出了点问题，请联系麻麻解决\n{e}')

async def get_ship_byName(hikari: Hikari_Model) -> List:
    try:
        ship_name = hikari.Input.ShipInfo.nameCn
        ship_name_select_index = None
        result = ship_name.split('.')
        if len(result) == 2 and result[1].isdigit():
            ship_name = result[0]
            ship_name_select_index = int(result[1])
        url = f'{hikari_config.yuyuko_url}/public/wows/encyclopedia/ship/search'
        params = {'country': '', 'level': '', 'shipName': ship_name, 'shipType': '', 'groupType': 'default'}
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.get(url, params=params, timeout=20)
        result = orjson.loads(resp.content)
        if result.get('code') == 200 and result.get('data'):
            code_data = result['data']
            # 转换为 ShipInfo 对象列表
            ship_list = []
            for ship_dict in code_data:
                ship_list.append(ShipInfo(ship_dict))
            # 如果指定了序号选择
            if ship_name_select_index and ship_name_select_index <= len(ship_list):
                return [ship_list[ship_name_select_index - 1]]

            return ship_list
        else:
            return []
    except PoolTimeout:
        await recreate_client_yuyuko()
        return []
    except Exception:
        return []



async def get_all_shipList(hikari: Hikari_Model):
    try:
        url = f'{hikari_config.yuyuko_url}/public/wows/encyclopedia/ship/search'
        params = {'country': '', 'level': '', 'shipName': '', 'shipType': '', 'groupType': 'default'}
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.get(url, params=params, timeout=20)
        result = orjson.loads(resp.content)
        if result['code'] == 200 and result['data']:
            return result['data']
        else:
            return None
    except PoolTimeout:
        await recreate_client_yuyuko()
        return
    except Exception:
        return None


async def get_AccountIdByName(hikari: Hikari_Model, server: str, name: str) -> str:
    try:
        url = f'{hikari_config.yuyuko_url}/public/wows/account/search/{server}/user'
        params = {'userName': name, 'one': True}
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.post(url, json=params, timeout=20)
        result = orjson.loads(resp.content)
        if result['code'] == 200 and result['data']:
            return int(result['data'][0]['accountId'])
        else:
            return result['message']
    except (TimeoutError, ConnectTimeout):
        logger.warning(traceback.format_exc())
        return '请求超时了，请过一会儿重试哦~'
    except PoolTimeout:
        await recreate_client_yuyuko()
        return
    except Exception as e:
        logger.error(traceback.format_exc())
        return f'好像出了点问题呢，可能是网络问题，如果重试几次还不行的话，请联系麻麻解决\n{e}'


async def get_ClanIdByName(hikari: Hikari_Model, server: str, tag: str):
    try:
        url = f'{hikari_config.yuyuko_url}/public/wows/clan/search/{server}'
        params = {
            'tag': tag,
        }
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.get(url, params=params, timeout=20)
        result = orjson.loads(resp.content)
        if result['code'] == 200 and result['data']:
            return result['data']
        else:
            return None
    except (TimeoutError, ConnectTimeout):
        logger.warning(traceback.format_exc())
        return None
    except PoolTimeout:
        await recreate_client_yuyuko()
        return
    except Exception:
        logger.error(traceback.format_exc())
        return None


async def check_yuyuko_cache(hikari: Hikari_Model, server, id):
    try:
        yuyuko_cache_url = f'{hikari_config.yuyuko_url}/api/wows/cache/check'
        params = {'accountId': id, 'server': server}
        client_yuyuko = await get_client_yuyuko(hikari.UserInfo)
        resp = await client_yuyuko.post(yuyuko_cache_url, json=params, timeout=5)
        result = orjson.loads(resp.content)
        cache_data = {}
        if result['code'] == 201:
            if 'DEV' in result['data']:
                await get_wg_info(cache_data, 'DEV', result['data']['DEV'])
            elif 'PVP' in result['data']:
                tasks = []
                for key in result['data']:
                    tasks.append(asyncio.ensure_future(get_wg_info(cache_data, key, result['data'][key])))
                await asyncio.gather(*tasks)
            if not cache_data:
                return False
            data_base64 = b64encode(gzip.compress(orjson.dumps(cache_data))).decode()
            params['data'] = data_base64
            resp = await client_yuyuko.post(yuyuko_cache_url, json=params, timeout=5)
            result = orjson.loads(resp.content)
            logger.success(result)
            if result['code'] == 200:
                return True
            else:
                return False
        return False
    except PoolTimeout:
        await recreate_client_yuyuko()
        return False
    except Exception:
        logger.error('缓存上报失败')
        return False


async def get_wg_info(params, key, url):
    try:
        client_wg = await get_client_wg()
        resp = await client_wg.get(url, timeout=5, follow_redirects=True)
        wg_result = orjson.loads(resp.content)
        if resp.status_code == 200 and wg_result['status'] == 'ok':
            params[key] = resp.text
    except PoolTimeout:
        await recreate_client_wg()
        return
    except Exception:
        logger.error(f'wg请求异常,请配置代理后尝试,上报url：{url}')
        return