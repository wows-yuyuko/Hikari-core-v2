from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
from pydantic import BaseModel

_scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
# 启动时只执行一次
_initial_scheduler = True


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
    save_template_html: bool = False  # 渲染图片时额外保存一份 HTML，便于查看与调试
    # 指令输错时的智能提示配置
    command_suggest_max: int = 3  # 最大提示条数，设为 0 则关闭智能提示
    command_suggest_dedupe: bool = True  # 同一效果(相同功能)的多个别名只提示一条
    command_language: str = 'zh'  # 指令提示语言: zh=中文, en=英文（英文模式下提示英文指令）


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
    save_template_html: bool = False,
    command_suggest_max: int = 3,
    command_suggest_dedupe: bool = True,
    command_language: str = 'zh',
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
        command_suggest_max (int): 指令输错时最大提示条数，默认3，设为0则关闭智能提示
        command_suggest_dedupe (bool): 相同功能的多别名只提示一条，默认开启
        command_language (str): 指令提示语言，zh=中文(默认)，en=英文（提示英文指令与英文参数用法）
        save_template_html (bool): 渲染图片时额外保存一份 HTML 到缓存目录 template_html/，默认关闭
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
    hikari_config.save_template_html = save_template_html
    hikari_config.command_suggest_max = command_suggest_max
    hikari_config.command_suggest_dedupe = command_suggest_dedupe
    hikari_config.command_language = 'en' if str(command_language).lower().startswith('en') else 'zh'
    # 为空则使用默认路径
    from hikari_core.core.cache_utils import get_cache_file, initial_cache_file

    try:
        if game_path == '':
            cache_dir = get_cache_file()
            initial_cache_file(cache_dir)
            logger.info(f'数据目录{cache_dir!s}')
        else:
            initial_cache_file(Path(game_path))
    except Exception as e:
        logger.error(f'初始化数据目录失败: {e}')
    logger.info(f'当前hikari-core配置\n{hikari_config}')
    global _initial_scheduler
    if _initial_scheduler and local_test is not True:
        logger.info('初始化任务....')
        from hikari_core.features.system import update_ship_cache, update_ship_cache_cron, update_template

        logger.info('执行初始模板更新...')
        # update_template()
        logger.info('执行初始缓存更新...')
        update_ship_cache()
        logger.info('启动定时任务')
        _scheduler.add_job(update_template, 'cron', hour='4,12')
        _scheduler.add_job(update_ship_cache_cron, 'cron', day_of_week='thu', hour=8, minute=0)
        _scheduler.start()
        logger.info('初始化任务结束....')
        _initial_scheduler = False
