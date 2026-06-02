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
    # await command('asia wose_sinus', False)
    # await command('cn 用户＿11451414514 recent 90', False)
    # await command('me ship 大', False)
    # await command('战舰排行榜 cn 大和', False)
    await command('asia nahida_official ship 大', False)
    # await command("公会战记录 cn 团子大家族 25", False)
    # await command("wws查询绑定 me", True)
    # await command("me sx", False)
    # await command("me sd", False)
    # await command('me clan', False)
    # await command("战舰排行榜 cn 大和", False)
    # await command("封号记录 国服 西行寺雨季", False)
    # await command("me ship 无比 recent 2024-05-30", False)
    # await command("公会战排行榜 20", False)


async def command(command_text: str, is_err: bool):
    hikari_data = await init_hikari(platform=platform,PlatformId= platform_id, command_text=str(command_text), GroupId=group_id)
    if hikari_data.Status == 'success':
        await output_with_check_type(hikari_data, command_text)
    elif hikari_data.Status == 'wait':
        await output_with_check_type(hikari_data, command_text + 'select')
        hikari_data.Input.Select_Index = 1
        hikari_data = await callback_hikari(hikari_data)
        await output_with_check_type(hikari_data, command_text)
    elif hikari_data.Status in ['error', 'failed']:
        if is_err:
            raise IOError(hikari_data.Output.Data)
        else:
            print('\033[31m' + hikari_data.Output.Data + '\033[0m')


async def output_with_check_type(hikari_data: Hikari_Model, command: str):
    print(hikari_data.Output.Data_Type)
    if isinstance(hikari_data.Output.Data, bytes):
        with open(command.replace(' ', '-') + '.html', 'w',encoding='utf-8') as f:
            f.write(hikari_data.template_content)
        with open(command.replace(' ', '-') + '.jpg', 'wb') as f:
            f.write(hikari_data.Output.Data)
            print(f'渲染完成,用时{time.time() - start_time}')
    elif isinstance(hikari_data.Output.Data, str):
        print(hikari_data.Output.Data)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start())
