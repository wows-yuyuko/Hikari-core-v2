from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = BackgroundScheduler(timezone='Asia/Shanghai')

class Config_Model(BaseModel):
    proxy: Optional[str] = None
    http2: bool = True
    token: Optional[str] = '123456:111111111111'
    auto_rendering: bool = True
    auto_image: bool = True
    use_broswer: Optional[str] = 'chromium'
    yuyuko_url: Optional[str] = 'https://v3-api.wows.shinoaki.com'
    yuyuko_type: Optional[str] = 'BOT'
    local_test: bool = False


hikari_config = Config_Model()


def set_hikari_config(  # noqa: PLR0913
        proxy: Optional[str] = None,
        http2: bool = True,
        token: Optional[str] = '123456:111111111111',
        auto_rendering: bool = True,
        auto_image: bool = True,
        use_broswer: Optional[str] = 'chromium',
        game_path: Optional[str] = '',
        yuyuko_url: Optional[str] = 'https://v3-api.wows.shinoaki.com',
        yuyuko_type: Optional[str] = 'BOT',
        local_test: bool = False,
):
    """配置Hikari-core

    Args:
        proxy (str): 访问WG使用的代理，格式http://localhost:7890
        http2 (bool): 是否开启http2，默认启用
        token (str): #请加群联系雨季获取api_key和token Q群:967546463
        auto_rendering (bool): 自动填充模板，默认启用
        auto_image (bool): 是否自动渲染，默认启用，若auto_rending未启用则该项配置无效
        use_broswer (str): chromium/firefox，默认chromium，性能大约为firefox三倍
        game_path (str):缓存文件夹路径，推荐设置在bot目录下，不配置默认为当前项目的data/wows-yuyuko目录下
        yuyuko_url (str):yuyuko请求地址
    """
    global hikari_config  # noqa: PLW0602
    hikari_config.proxy = proxy
    hikari_config.http2 = http2
    hikari_config.token = token
    hikari_config.auto_rendering = auto_rendering
    hikari_config.auto_image = auto_image
    hikari_config.use_broswer = use_broswer
    hikari_config.yuyuko_url = yuyuko_url
    hikari_config.yuyuko_type = yuyuko_type
    hikari_config.local_test = local_test
    # 为空则使用默认路径
    from hikari_core.cache_utils import get_cache_file,initial_cache_file
    if game_path == '':
        initial_cache_file(get_cache_file())
    else:
        initial_cache_file(Path(game_path))
    logger.info(f'当前hikari-core配置\n{hikari_config}')
    from hikari_core.game.help import update_template, update_ship_cache,update_ship_cache_cron
    update_template()
    update_ship_cache()
    logger.info(f"启动定时任务")
    _scheduler.add_job(update_template, 'cron', hour='4,12')
    _scheduler.add_job(update_ship_cache_cron, 'cron', day_of_week='thu', hour=8, minute=0)
    _scheduler.start()

