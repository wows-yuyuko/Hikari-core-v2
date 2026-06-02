import time
import traceback
import os
import jinja2
from jinja2.exceptions import UndefinedError
from loguru import logger
from playwright.async_api import Error as playwright_Error
from pydantic import ValidationError, Field

from .cache_utils import get_cache_file
from .Html_Render import html_to_pic, html_to_pic_by_gif
from .analyze import analyze_command
from .command_select import *  # noqa: F403
from .config import hikari_config, set_hikari_config  # noqa:F401 set_hikari_config为外部程序引用
from .data_source import set_render_params, template_path
from .model import Hikari_Model, Input_Model, UserInfo_Model

env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_path), enable_async=True)
env.globals.update(
    time=time,
    abs=abs,
    enumerate=enumerate,
    int=int,
)


async def init_hikari(
        platform: str,
        PlatformId: str,
        command_text: str = Field(default='', description='输入的指令'),
        GroupId: str = None,
        Ignore_List= [],  # noqa: B006
) -> Hikari_Model:
    """Hikari初始化

    Args:
        platform (str): 平台类型
        PlatformId (str): 平台ID
        command_text (str): 传入指令，不带wws
        GroupId (str): 群号,不配置无法使用部分分群功能
        Ignore_List(List):  禁用功能列表，通过import导入
    Returns:
        Hikari_Model: 可通过Hikari.Status和Hikari.Output.Data内数据判断是否输出
    """
    try:
        hikari = Hikari_Model(UserInfo=UserInfo_Model(Platform=platform, PlatformId=PlatformId, GroupId=GroupId), Input=Input_Model(Command_Text=command_text))
        hikari = await analyze_command(hikari)
        if hikari.Status != 'init' or not hikari.Function:
            return hikari
        if hikari.Function in Ignore_List:
            return hikari.error('该功能已被禁用')
        hikari: Hikari_Model = await hikari.Function(hikari)
        return await output_hikari(hikari)
    except ValidationError:
        logger.error(traceback.format_exc())
        return Hikari_Model().error('参数校验错误，请联系开发者确认入参是否符合Model')
    except Exception:
        logger.error(traceback.format_exc())
        return Hikari_Model().error('Hikari-core顶层错误，请检查log')


async def callback_hikari(hikari: Hikari_Model) -> Hikari_Model:
    """回调wait状态的Hikari

    Args:
        hikari (Hikari_Model):前置或自行构造的Hikari_Model，可通过from hikari_core import Hikari_Model引入

    Returns:
        Hikari_Model: 可通过Hikari.Status和Hikari.Output.Data内数据判断是否输出
    """
    try:
        if not hikari.Status == 'wait':
            return hikari.error('当前请求状态错误，请确认是否为wait')
        if not hikari.Function:
            return hikari.error('缺少请求方法')
        hikari: Hikari_Model = await hikari.Function(hikari)
        return await output_hikari(hikari)

    except Exception:
        logger.error(traceback.format_exc())
        return Hikari_Model().error('Hikari-core顶层错误，请检查log')


async def output_hikari(hikari: Hikari_Model) -> Hikari_Model:
    """输出Hikari

    Args:
        hikari (Hikari_Model):前置或自行构造的Hikari_Model，可通过from hikari_core import Hikari_Model引入

    Returns:
        Hikari_Model: 可通过Hikari.Status和Hikari.Output.Data内数据判断是否输出
    """
    try:
        if (
                hikari.Status in ['success', 'wait']
                and hikari_config.auto_rendering
                and hikari.Output.Template
                and (isinstance(hikari.Output.Data, dict) or isinstance(hikari.Output.Data, list))  # noqa: PLR1701
        ):
            template = env.get_template(hikari.Output.Template)
            # 获取全部的 shipInfo节点
            if hikari.Status == 'success':
                # 对 shipInfo节点进行修改 使用本地文件来渲染
                template_data = await set_render_params(find_and_modify_shipinfo(hikari.Output.Data))
            elif hikari.Status == 'wait':
                template_data = await set_render_params(hikari.Input.Select_Data)
            else:
                template_data = {}
            content = await template.render_async(template_data)
            # 测试模式下才赋值给模板内容
            if hikari_config.local_test:
                hikari.template_content = content
            hikari.Output.Data = content
            hikari.Output.Data_Type = type(hikari.Output.Data)

            if hikari_config.auto_image:
                hikari.Output.Data = await html_to_pic(
                    content,
                    wait=0,
                    viewport={'width': hikari.Output.Width, 'height': hikari.Output.Height},
                    use_browser=hikari_config.use_broswer,
                )
                hikari.Output.Data_Type = type(hikari.Output.Data)
        return hikari
    except UndefinedError as e:
        logger.error(traceback.format_exc())
        return Hikari_Model().error(f'模板渲染错误，请将错误日志提交给开发者\n{e}')
    except playwright_Error as e:
        logger.error(traceback.format_exc())
        return Hikari_Model().error(f'playwright错误，请检查浏览器内核是否异常结束，可能是由于服务器版本过低，请升级至winserver2016+或改为firefox启动。\n{e}')
    except Exception as e:
        logger.error(traceback.format_exc())
        return Hikari_Model().error(f'Hikari-core顶层错误，请检查log\n{e}')


# shipInfo 中需要替换为本地缓存路径的图片字段
_SHIP_IMAGE_KEYS = ("shipTypeImage", "imgSmall", "countryImage")


def find_and_modify_shipinfo(data, target_key="shipInfo"):
    """深度搜索 shipInfo 节点，将远程图片 URL 替换为本地缓存路径。

    Args:
        data: 嵌套数据结构
        target_key: 要搜索的键名，默认 "shipInfo"
    """
    wows_temp = get_cache_file() / "ship_cache"

    def _replace_images(ship_info):
        """将 shipInfo 中的图片 URL 替换为本地 file:// 路径（若缓存文件存在）。"""
        for key in _SHIP_IMAGE_KEYS:
            if key in ship_info:
                local = wows_temp / str(os.path.basename(ship_info[key]))
                if local.exists():
                    ship_info[key] = f"file:///{local.as_posix()}"

    def _recurse(obj):
        if isinstance(obj, dict):
            if target_key in obj and isinstance(obj[target_key], dict):
                _replace_images(obj[target_key])
            for value in obj.values():
                _recurse(value)
        elif isinstance(obj, list):
            for item in obj:
                _recurse(item)

    _recurse(data)
    return data
