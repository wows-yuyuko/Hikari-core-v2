import time
import traceback
import os
import jinja2
from jinja2.exceptions import UndefinedError
from loguru import logger
from playwright.async_api import Error as playwright_Error
from pydantic import ValidationError

from .Html_Render import html_to_pic, html_to_pic_by_gif
from .analyze import analyze_command
from .command_select import *  # noqa: F403
from .config import hikari_config  # noqa:F401
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
        command_text: str = None,
        GroupId: str = None,
        Ignore_List=[],  # noqa: B006
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
        userinfo = UserInfo_Model(Platform=platform, PlatformId=PlatformId, GroupId=GroupId)
        input = Input_Model(Command_Text=command_text)
        hikari = Hikari_Model(UserInfo=userinfo, Input=input)
        hikari = await analyze_command(hikari)
        if not hikari.Status == 'init' or not hikari.Function:
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


def find_and_modify_shipinfo(data, target_key="shipInfo"):
    """
    深度搜索并修改 shipInfo 节点

    Args:
        data: 嵌套数据结构
        target_key: 要搜索的键名，默认 "shipInfo"
    """

    def recursive_modify(obj, path=""):
        from hikari_core.cache_utils import get_cache_file
        wows_temp = get_cache_file() / "ship_cache"
        if isinstance(obj, dict):
            # 如果找到目标键
            if target_key in obj:
                ship_info = obj[target_key]
                if isinstance(ship_info, dict):
                    # 处理字典形式：{ship_id: ship_data, ...}
                    if "shipTypeImage" in ship_info and "imgSmall" in ship_info and "countryImage" in ship_info:
                        # 获取 shipTypeImage 和 imgSmall 的文件名
                        ship_type_image_filename = wows_temp / os.path.basename(ship_info["shipTypeImage"])
                        img_small_filename = wows_temp / os.path.basename(ship_info["imgSmall"])
                        country_image_filename = wows_temp / os.path.basename(ship_info["countryImage"])
                        if ship_type_image_filename.exists():
                            ship_info["shipTypeImage"] = f"file:///{ship_type_image_filename.as_posix()}"

                        if img_small_filename.exists():
                            ship_info["imgSmall"] = f"file:///{img_small_filename.as_posix()}"

                        if country_image_filename.exists():
                            ship_info["countryImage"] = f"file:///{country_image_filename.as_posix()}"

            # 递归搜索所有键值对
            for key, value in list(obj.items()):
                recursive_modify(value, f"{path}.{key}" if path else key)

        elif isinstance(obj, list):
            # 递归搜索列表元素
            for i, item in enumerate(obj):
                recursive_modify(item, f"{path}[{i}]")

    recursive_modify(data)
    return data

# logger.add(
#    'hikari-core-logs/error.log',
#    rotation='00:00',
#    retention='1 week',
#    diagnose=False,
#    level='ERROR',
#    encoding='utf-8',
# )
# logger.add(
#    'hikari-core-logs/info.log',
#    rotation='00:00',
#    retention='1 week',
#    diagnose=False,
#    level='INFO',
#    encoding='utf-8',
# )
# logger.add(
#    'hikari-core-logs/warning.log',
#    rotation='00:00',
#    retention='1 week',
#    diagnose=False,
#    level='WARNING',
#    encoding='utf-8',
# )
