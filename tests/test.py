import asyncio
import time

from hikari_core.config import set_hikari_config
from tests.auto_test import command

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
    await command('asia nahida_official ship 大')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start())
