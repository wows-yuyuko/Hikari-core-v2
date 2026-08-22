import asyncio
import json
import os
import subprocess
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from hikari_core import __version__
from hikari_core.core.cache_utils import get_cache_file, get_cache_file_str
from hikari_core.core.config import hikari_config
from hikari_core.core.constants import template_path
from hikari_core.core.http_client import get_client_default
from hikari_core.core.http_error_handler import handle_yuyuko_errors
from hikari_core.core.model import Hikari_Model
from hikari_core.core.template_registry import Templates

executor = ThreadPoolExecutor()


@handle_yuyuko_errors(recreate_func="default")
async def get_help(hikari: Hikari_Model):
    """获取帮助列表（按 command_language 输出中文/英文 H5 帮助页）"""
    template = Templates.HELP_EN if hikari_config.command_language == 'en' else Templates.HELP_ZH
    template.apply_to(hikari)
    return hikari.success({})


def _find_repo_root() -> Optional[Path]:
    """向上查找包含 .git 的仓库根目录（供 check_version 同步用）"""
    start = Path(__file__).resolve().parent.parent.parent  # hikari_core 的上级
    for d in (start, *start.parents):
        if (d / '.git').exists():
            return d
    return None


def _git_pull_main(repo_root: Path):
    """同步仓库 main 分支，返回 (returncode, stdout, stderr)"""
    try:
        proc = subprocess.run(
            ['git', '-C', str(repo_root), 'pull', 'origin', 'main'],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return -1, '', str(e)


@handle_yuyuko_errors(recreate_func="default")
async def check_version(hikari: Hikari_Model):
    """检查版本信息；检测到新版本时自动同步仓库 main 分支"""
    url = 'https://benx1n.oss-cn-beijing.aliyuncs.com/version.json'
    client_default = await get_client_default()
    resp = await client_default.get(url, timeout=20)
    result = json.loads(resp.content)
    match, msg = False, '发现新版本'
    for each in result['data']:
        if each['version'] > __version__:
            match = True
            msg += f"\n{each['date']} v{each['version']}\n"
            for i in each['description']:
                msg += f'{i}\n'
    if not match:
        return hikari.success('Hikari:当前已经是最新版本了')
    msg += '\n检测到新版本，正在同步仓库 main 分支...'
    repo_root = _find_repo_root()
    if repo_root is None:
        msg += '\n未找到仓库目录（.git），请手动执行 git pull origin main'
        return hikari.error(msg)
    code, out, err = await asyncio.to_thread(_git_pull_main, repo_root)
    if code == 0:
        msg += f'\n同步完成：{repo_root}\n请重启 Bot 后生效'
        return hikari.success(msg)
    msg += f'\n同步失败（exit {code}）:\n{(err or out)[-500:]}'
    return hikari.error(msg)


async def async_update_template(hikari: Hikari_Model = Hikari_Model()):
    try:
        # 在线程池中执行阻塞操作
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(executor, update_template)
        if result:
            return hikari.success('更新模板成功')
        return hikari.error('更新模板失败')
    except Exception as e:
        return hikari.error(f'更新模板失败: {str(e)}')


async def async_update_ship_cache(hikari: Hikari_Model = Hikari_Model()):
    try:
        # 在线程池中执行阻塞操作
        loop = asyncio.get_event_loop()
        # 定时任务这边直接下载
        result = await loop.run_in_executor(executor, update_ship_cache)
        if result:
            return hikari.success('更新战舰资源成功')
        return hikari.error('更新战舰资源失败')
    except Exception as e:
        return hikari.error(f'更新战舰资源失败: {str(e)}')


def update_template():
    """更新模板"""
    try:
        # tasks = []
        url = 'https://hikari-resource.oss-cn-shanghai.aliyuncs.com/hikari_core_template/template-v2.json'
        with httpx.Client() as client:
            resp = client.get(url, timeout=20)
            result = json.loads(resp.content)
            for each in result:
                for name, url in each.items():
                    resp = client.get(url, timeout=5)
                    with open(template_path / name, 'wb+') as file:
                        file.write(resp.content)
            logger.info('更新模板成功')
        return True
    except Exception:
        logger.error(traceback.format_exc())
        return False

def update_ship_cache_cron():
    base_path = get_cache_file() / "ship_cache"
    base_path.mkdir(exist_ok=True, parents=True)
    zip_path = get_cache_file() / "ship_cache.zip"
    load_ship_cache_zip(get_cache_file(), zip_path)

def update_ship_cache():
    logger.info('开始更新战舰资源')
    base_path = get_cache_file() / "ship_cache"
    base_path.mkdir(exist_ok=True, parents=True)
    zip_path = get_cache_file() / "ship_cache.zip"
    if not zip_path.exists():
        load_ship_cache_zip(get_cache_file(), zip_path)
        get_all_ship_cache_hash_json(get_cache_file_str())
    # 加载本地json
    with open(get_cache_file() / "ship_cache_hash.json", "rb") as f:
        ship_hash_local_json = json.loads(f.read())
    ship_hash_new_json = get_all_ship_cache_hash_json(get_cache_file_str())
    local_dict = {item["key"]: item["value"] for item in ship_hash_local_json}
    remote_dict = {item["key"]: item["value"] for item in ship_hash_new_json}
    files_to_download = []
    for filename, remote_hash in remote_dict.items():
        if filename not in local_dict or local_dict[filename] != remote_hash:
            files_to_download.append(filename)
    for filename in files_to_download:
        write_ship_cache(base_path,f"https://v3-api.wows.shinoaki.com/nahida-static/ship_cache/{filename}")
    logger.info("更新战舰资源完成")

def get_all_ship_cache_hash_json(dir: str):
    try:
        file_json = Path(dir) / 'ship_cache_hash.json'
        url = f'https://v3-api.wows.shinoaki.com/nahida-static/ship_cache/ship_cache_hash.json'
        with httpx.Client() as client:
            resp = client.get(url, timeout=20)
            with open(file_json, 'wb') as f:
                f.write(resp.content)
            return json.loads(resp.content)
    except Exception:
        return None

def load_ship_cache_zip(wows_temp : Path,zip_path: Path):
    logger.info('开始下载战舰图片资源压缩包，等待时间较长！')
    _download_file("https://v3-api.wows.shinoaki.com/nahida-static/ship_cache.zip", zip_path)
    extract_zip(zip_path, wows_temp)
    logger.info("更新战舰zip包资源完成")

def write_ship_cache(file_dir: Path, ship_url: str):
    """
    异步下载 ship_url 文件到 file_dir 文件夹

    Args:
        file_dir: 目标文件夹路径
        ship_url: 要下载的URL地址
        is_check_time: 是否检查文件更新时间，True则检查7天内是否需要更新

    """
    try:
        # 确保目录存在
        os.makedirs(file_dir, exist_ok=True)

        # 从URL中提取文件名
        url_path = urlparse(ship_url).path
        file_name = os.path.basename(url_path)
        file_path = file_dir / file_name

        # 检查文件是否存在
        # if os.path.exists(file_path):
        #     return True
        logger.info(f"开始下载: {file_name}")
        success = _download_file(ship_url, file_path)
        return success

    except Exception as e:
        logger.error(f"处理失败: {e}")
        return False


def _download_file(url: str, file_path: Path) -> bool:
    """
    异步下载文件到指定路径的内部函数

    Args:
        url: 下载URL
        file_path: 保存路径

    """
    try:
        # 使用httpx异步下载
        with httpx.Client() as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()  # 检查HTTP状态码

                # 确保目录存在（再次检查）
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # 写入文件（使用Path对象打开文件）
                with file_path.open('wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)

        # 验证文件是否成功下载
        if file_path.exists() and file_path.stat().st_size > 0:
            # 更新文件时间戳为当前时间
            current_time = time.time()
            os.utime(str(file_path), (current_time, current_time))

            file_size = file_path.stat().st_size
            logger.info(f"文件下载成功: {file_path} ({file_size} bytes)")
            return True
        else:
            logger.error(f"文件下载失败或文件为空: {file_path}")
            return False

    except httpx.TimeoutException:
        logger.error(f"下载超时: {url}")
        return False
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP错误 ({e.response.status_code}): {e}")
        return False
    except httpx.RequestError as e:
        logger.error(f"请求错误: {e}")
        return False
    except Exception as e:
        logger.error(f"下载失败: {e}")
        return False


def extract_zip(zip_path: Path, base_path: Path) -> bool:
    """
    解压ZIP文件

    Args:
        overwrite: 是否覆盖已存在的文件

    Returns:
        bool: 解压是否成功
    """
    try:
        if not zip_path.exists():
            logger.error(f"ZIP文件不存在: {zip_path}")
            return False
        logger.info(f"开始解压: {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 获取文件列表
            file_list = zip_ref.namelist()
            logger.info(f"开始解压 {len(file_list)} 个文件")

            # 解压所有文件
            zip_ref.extractall(base_path)

            # 验证解压结果
            extracted_files = []
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    extracted_files.append(os.path.join(root, file))

            logger.info(f"解压完成，共 {len(extracted_files)} 个文件")

            # 检查是否有文件
            if len(extracted_files) == 0:
                logger.warning("解压后没有文件")
                return False

            # 打印前10个文件
            for i, file in enumerate(extracted_files[:10]):
                file_size = os.path.getsize(file)
                logger.debug(f"  {i + 1}. {os.path.basename(file)} ({file_size} bytes)")

            if len(extracted_files) > 10:
                logger.debug(f"  ... 还有 {len(extracted_files) - 10} 个文件")

            return True

    except zipfile.BadZipFile:
        logger.error("ZIP文件损坏")
        return False
    except Exception as e:
        logger.error(f"解压失败: {e}")
        return False
