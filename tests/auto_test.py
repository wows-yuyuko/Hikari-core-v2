import asyncio

from hikari_core.config import set_hikari_config
from tests.test import command

platform = 'QQ'
platform_id = '2622749113'
group_id = '967546463'


async def start():
    set_hikari_config(use_broswer='chromium', http2=True,
                      # proxy='http://localhost:7890',
                      proxy=None,
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


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start())
