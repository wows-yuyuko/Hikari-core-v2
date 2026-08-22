import httpx
from httpx import AsyncClient, Request, Response
from loguru import logger

from .config import hikari_config
from .. import __version__


async def before_request(request: Request):
    logger.info(f'{request.method} {request.url}')


async def after_response(response: Response):
    logger.info(f'本次响应的状态码:{response.status_code} {response.http_version} {response.request}')


_client_yuyuko: AsyncClient = None
_client_wg: AsyncClient = None
_client_default: AsyncClient = None


async def create_client_yuyuko() -> AsyncClient:
    global _client_yuyuko
    # base数据支持 添加 Base64UserInfoImg
    _client_yuyuko = httpx.AsyncClient(
        headers={
            'Authorization': hikari_config.token,
            'accept': 'application/json',
            'Content-Type': 'application/json',
            'Yuyuko-Client-Type': f'{hikari_config.yuyuko_type};{__version__};Base64UserInfoImg',
        },
        event_hooks={
            'request': [
                before_request,
            ],
            'response': [
                after_response,
            ],
        },
        http2=hikari_config.http2,
    )
    logger.info('创建client_yuyuko')
    return _client_yuyuko


async def create_client_wg() -> AsyncClient:
    if hikari_config.proxy:
        proxy = {'https://': hikari_config.proxy}
    else:
        proxy = {}
    global _client_wg
    _client_wg = httpx.AsyncClient(proxies=proxy)
    logger.info('创建client_wg')
    return _client_wg


async def create_client_default() -> AsyncClient:
    global _client_default
    _client_default = httpx.AsyncClient()
    logger.info('创建client_default')
    return _client_default


async def get_client_yuyuko(UserModel) -> AsyncClient:
    user_info_json = UserModel.json()
    global _client_yuyuko
    if _client_yuyuko:
        _client_yuyuko.headers.update({'YUYUKO-INFO': user_info_json})
    else:
        _client_yuyuko = await create_client_yuyuko()
        _client_yuyuko.headers.update({'YUYUKO-INFO': user_info_json})
    return _client_yuyuko


async def get_client_wg() -> AsyncClient:
    return _client_wg if _client_wg else await create_client_wg()


async def get_client_default() -> AsyncClient:
    return _client_default if _client_default else await create_client_default()


async def recreate_client_yuyuko():
    global _client_yuyuko  # 声明使用全局变量
    # 关闭旧连接
    if _client_yuyuko is not None:
        logger.info('关闭旧的yuyuko连接池')
        await _client_yuyuko.aclose()
    # 创建新连接
    logger.info('重新创建yuyuko连接池')
    _client_yuyuko = await create_client_yuyuko()


async def recreate_client_wg():
    global _client_wg
    if _client_wg is not None:
        logger.info('重新创建wg连接池')
        await _client_wg.aclose()
    _client_wg = await create_client_wg()

async def recreate_client_default():
    global _client_default
    if _client_default is not None:
        logger.info('重新创建default连接池')
        await _client_default.aclose()
    _client_default = await create_client_default()
