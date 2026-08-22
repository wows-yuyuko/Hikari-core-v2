import asyncio
import time

from loguru import logger

from hikari_core import Hikari_Model, callback_hikari, init_hikari, get_cache_file  # noqa: E402
from hikari_core.core.config import set_hikari_config

platform = 'QQ'
platform_id = '2622749113'
group_id = '967546463'
is_out_image = False


async def start():
    global start_time
    start_time = time.time()
    set_hikari_config(use_broswer='chromium', http2=False,
                      # proxy='http://localhost:7890',
                      proxy=None,
                      local_test=True,
                      token='2622749113:TAN9iMARSDJbzLVOUK1a9cTSiKtb32GIbpr', yuyuko_type='QQ_CHANNEL',
                      game_path='')
    global is_out_image
    is_out_image = True
    await command("me ship 哥伦布")
    # await command("ban cn 西行寺雨季")
    await command("me")
    # await command("me sx")
    # await command("me sd")
    # await command("me recent 30")
    # await command("me ship 大和 recent 90")
    # await command("me clan")
    # await command("clan asia YU")
    # await command("战舰排行榜 国服 大和")
    # await command("me ship 无比 recent 2024-05-30")
    # await command("公会战排行榜 20")
    # await command('asia nahida_official ship 大')


async def command(command_text: str):
    logger.info("============START===========================================================================")
    logger.info(f'command ==>> {command_text}')
    hikari_data = await init_hikari(platform=platform, PlatformId=platform_id, command_text=str(command_text), GroupId=group_id)
    if hikari_data.Status == 'success':
        output_with_check_type(hikari_data, command_text)
    elif hikari_data.Status == 'wait':
        output_with_check_type(hikari_data, command_text + 'select')
        hikari_data.Input.Select_Index = 1
        hikari_data = await callback_hikari(hikari_data)
        output_with_check_type(hikari_data, command_text)
    elif hikari_data.Status == 'failed':
        logger.error(hikari_data.Output.Data)
    elif hikari_data.Status in ['error', 'failed']:
        raise IOError(hikari_data.Output.Data)
    logger.info("============END============================================================================")


def output_with_check_type(hikari_data: Hikari_Model, command: str):
    logger.info(hikari_data.Output.Data_Type)
    global is_out_image
    if not is_out_image:
        logger.info(command.replace(' ', '-') + '.html')
        return
    if isinstance(hikari_data.Output.Data, bytes):
        file = get_cache_file() / 'temp_image' / (command.replace(' ', '-') + '.html')
        with open(file, 'w', encoding='utf-8') as f:
            f.write(hikari_data.template_content)
        img = get_cache_file() / 'temp_image' / (command.replace(' ', '-') + '.jpg')
        with open(img, 'wb') as f:
            f.write(hikari_data.Output.Data)
    elif isinstance(hikari_data.Output.Data, str):
        logger.info(hikari_data.Output.Data)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start())
