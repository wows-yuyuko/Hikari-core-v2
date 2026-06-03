import asyncio
import time

from hikari_core import Hikari_Model, callback_hikari, init_hikari  # noqa: E402
from hikari_core.config import set_hikari_config

platform = 'QQ'
platform_id = '2622749113'
group_id = '967546463'


async def start():
    global start_time
    start_time = time.time()
    set_hikari_config(use_broswer='chromium', http2=False, proxy='http://localhost:7890',
                      local_test=True,
                      token='2622749113:TAN9iMARSDJbzLVOUK1a9cTSiKtb32GIbpr', yuyuko_type='QQ_CHANNEL',
                      game_path='')
    # await command('测试监控', False)
    await command('asia nahida_official')
    await command('me recent 180')
    await command('me ship 大')
    await command('战舰排行榜 cn 大和')
    await command('asia nahida_official ship 大')
    await command("公会战记录 cn 团子大家族 25")
    await command("wws查询绑定 me")
    await command("me sx")
    await command("me sd")
    await command('me clan')
    await command("封号记录 国服 西行寺雨季")
    await command("me ship 无比 recent 2024-05-30")
    await command("公会战排行榜 20")


async def command(command_text: str):
    hikari_data = await init_hikari(platform=platform, PlatformId=platform_id, command_text=str(command_text), GroupId=group_id)
    if hikari_data.Status == 'success':
        output_with_check_type(hikari_data, command_text)
    elif hikari_data.Status == 'wait':
        output_with_check_type(hikari_data, command_text + 'select')
        hikari_data.Input.Select_Index = 1
        hikari_data = await callback_hikari(hikari_data)
        output_with_check_type(hikari_data, command_text)
    elif hikari_data.Status in ['error', 'failed']:
        raise IOError(hikari_data.Output.Data)


def output_with_check_type(hikari_data: Hikari_Model, command: str):
    print(hikari_data.Output.Data_Type)
    if isinstance(hikari_data.Output.Data, bytes):
        with open(command.replace(' ', '-') + '.html', 'w', encoding='utf-8') as f:
            f.write(hikari_data.template_content)
        with open(command.replace(' ', '-') + '.jpg', 'wb') as f:
            f.write(hikari_data.Output.Data)
            print(f'渲染完成,用时{time.time() - start_time}')
    elif isinstance(hikari_data.Output.Data, str):
        print(hikari_data.Output.Data)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start())
