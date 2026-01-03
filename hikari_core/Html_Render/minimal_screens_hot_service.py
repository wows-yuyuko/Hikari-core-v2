#!/usr/bin/env python3
"""
极简高性能HTML截图服务
特点：快速启动、低内存占用、支持HTML内嵌图片和JS
"""

import asyncio
import hashlib
import tempfile
import time
from pathlib import Path
from PIL import Image
from typing import Optional, List, Dict
import logging
import gc
import io

from playwright.async_api import async_playwright, Browser, Page

from hikari_core.cache_utils import get_cache_file

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class minimal_screens_hot_service:
    """极简截图服务 - 专注启动速度和内存优化"""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def get_instance(cls):
        """获取单例实例（推荐使用这个方法）"""
        if cls._instance is None:
            cls._instance = minimal_screens_hot_service()
            await cls._instance.start()
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.browser: Optional[Browser] = None
        self.context_pages: Dict[str, Page] = {}  # 会话页面缓存
        self.temp_dir = get_cache_file() / "browser_temp"
        self.temp_dir.mkdir(exist_ok=True)
        self.gc_count = 100
        # 内存监控
        self.last_gc = time.time()
        self.request_count = 0

    async def start(self):
        """极速启动浏览器 - 优化启动参数"""
        start_time = time.time()
        self.playwright = await async_playwright().start()
        try:
            # 使用最小的启动参数
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',  # 截图不需要GPU加速
                    '--disable-software-rasterizer',
                    # 允许加载本地资源和跨域
                    '--disable-web-security',
                    '--allow-file-access-from-files',
                    '--allow-running-insecure-content',
                    # 内存优化
                    # '--single-process',
                    # '--max_old_space_size=128',
                    # 性能优化
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                ],
                # 关键：关闭信号处理，加速启动
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
                # 超时设置
                timeout=30000
            )

            elapsed = time.time() - start_time
            logger.info(f"浏览器启动完成，耗时: {elapsed:.2f}秒")
            return True

        except Exception as e:
            logger.error(f"浏览器启动失败: {e}")
            # 尝试回退方案
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage'],
                    timeout=30000
                )
                logger.info("使用最小参数启动成功")
                return True
            except Exception as e2:
                logger.error(f"回退启动也失败: {e2}")
                return False

    async def create_page(self, session_id: str = None) -> Page:
        """创建优化页面 - 快速轻量"""

        # 如果有会话缓存且页面有效，复用
        if session_id and session_id in self.context_pages:
            page = self.context_pages[session_id]
            try:
                if not page.is_closed():
                    # 快速重置页面
                    await page.evaluate("document.body.innerHTML = ''")
                    return page
            except:
                del self.context_pages[session_id]

        # 创建新页面
        context = await self.browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
            # 最小化上下文开销
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            # 关键：禁用不必要的功能
            locale='zh-CN',
            timezone_id='UTC',
        )

        page = await context.new_page()

        # 关键：设置极简资源拦截
        await page.route("**/*", self._ultra_light_route_handler)

        # 注入优化脚本
        await page.add_init_script("""
            // 性能优化脚本 - 极简版
            (function() {
                // 1. 限制JS执行时间
                const originalSetTimeout = window.setTimeout;
                const originalSetInterval = window.setInterval;
                
                window.setTimeout = function(fn, delay) {
                    delay = Math.max(delay, 10);  // 最小10ms
                    return originalSetTimeout(fn, delay);
                };
                
                window.setInterval = function(fn, delay) {
                    delay = Math.max(delay, 100);  // 最小100ms
                    return originalSetInterval(fn, delay);
                };
                
                // 2. 监听页面加载完成
                window.__screenshot_ready = false;
                window.addEventListener('load', () => {
                    window.__screenshot_ready = true;
                }, {once: true});
                
                // 3. 图片加载优化
                document.addEventListener('DOMContentLoaded', () => {
                    const images = document.images;
                    let loaded = 0;
                    const total = images.length;
                    
                    for (let img of images) {
                        if (img.complete) {
                            loaded++;
                        } else {
                            img.onload = img.onerror = () => {
                                loaded++;
                            };
                        }
                    }
                    
                    window.__images_loaded = loaded;
                    window.__images_total = total;
                });
            })();
        """)

        if session_id:
            self.context_pages[session_id] = page

        return page

    async def _ultra_light_route_handler(self, route):
        """极简资源处理 - 允许所有必要资源"""
        request = route.request
        resource_type = request.resource_type

        try:
            await route.continue_()
        except:
            # 任何错误都直接继续，不阻塞
            try:
                await route.continue_()
            except:
                await route.fulfill(status=404)

    async def screenshot(self, html_content: str, session_id: str = None, **kwargs) -> bytes:
        """核心截图方法 - 优化执行流程"""
        self.request_count += 1

        page = None
        temp_file = None

        try:
            # 1. 获取页面（复用或创建）
            page = await self.create_page(session_id)

            # 2. 快速写入临时文件（比data URL稳定）
            html_hash = hashlib.md5(html_content.encode()).hexdigest()[:8]
            temp_file = self.temp_dir / f"temp_{html_hash}.html"

            # 使用同步写入，更快
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 3. 极速加载策略
            load_start = time.time()

            # 关键：使用最快加载模式
            await page.goto(
                f"file://{temp_file}",
                wait_until='domcontentloaded',  # 最快：DOM加载完成即可
                timeout=10000,  # 10秒超时
            )

            load_time = time.time() - load_start
            logger.debug(f"页面加载: {load_time:.2f}s")

            # 4. 智能等待渲染
            await self._smart_wait(page)
            # 根据元素尺寸调整视口
            view = kwargs["viewport"]
            await page.set_viewport_size(view)

            # 5. 快速截图
            screenshot_start = time.time()
            image_data = await page.screenshot(
                type='jpeg',  # JPEG最快
                quality=85,
                full_page=True,  # 只截取可视区域
                omit_background=True,
            )

            screenshot_time = time.time() - screenshot_start
            logger.debug(f"截图耗时: {screenshot_time:.2f}s")

            total_time = time.time() - load_start
            logger.info(f"请求{self.request_count} - 总耗时: {total_time:.2f}s")

            # 6. 内存清理（定期触发）
            await self._auto_cleanup()

            return image_data

        except Exception as e:
            logger.error(f"截图失败: {e}")
            raise

        finally:
            # 7. 快速清理
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass

            # 8. 非会话页面立即关闭（避免内存累积）
            if page and not session_id:
                try:
                    await page.context.close()
                except:
                    pass

    async def screenshot_gif_img(self, html_content: str, session_id: str = None,
                                 fps: int = 10,
                                 duration: int = 3) -> bytes:
        """核心截图方法 - 优化执行流程"""
        self.request_count += 1

        page = None
        temp_file = None

        try:
            # 1. 获取页面（复用或创建）
            page = await self.create_page(session_id)

            # 2. 快速写入临时文件（比data URL稳定）
            html_hash = hashlib.md5(html_content.encode()).hexdigest()[:8]
            temp_file = self.temp_dir / f"temp_{html_hash}.html"

            # 使用同步写入，更快
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 3. 极速加载策略
            load_start = time.time()

            # 关键：使用最快加载模式
            await page.goto(
                f"file://{temp_file}",
                wait_until='domcontentloaded',  # 最快：DOM加载完成即可
                timeout=10000,  # 10秒超时
            )

            load_time = time.time() - load_start
            logger.debug(f"页面加载: {load_time:.2f}s")

            # 4. 智能等待渲染
            await self._smart_wait(page)

            # 5. 快速截图
            screenshot_start = time.time()
            # 创建临时目录存放截图
            with tempfile.TemporaryDirectory() as temp_dir:
                screenshot_files = []
                # 计算截图次数
                interval = 1.0 / fps  # 每帧间隔(秒)
                total_frames = int(duration * fps)
                # 开始截图
                for i in range(total_frames):
                    timestamp = int(time.time() * 1000)
                    filename = Path(temp_dir) / f"frame_{i:03d}_{timestamp}.png"

                    # 截图
                    await page.screenshot(
                        path=str(filename),
                        type='png',
                        full_page=True,  # 只截取可视区域
                        omit_background=True,
                    )
                    screenshot_files.append(str(filename))

                    # 如果需要，可以在每次截图之间执行一些操作
                    # 例如：滚动、点击等

                    # 等待下一帧
                    if i < total_frames - 1:  # 最后一帧后不需要等待
                        await page.wait_for_timeout(int(interval * 1000))

                # 将截图转换为GIF
                image_data = await self._images_to_gif(screenshot_files, fps)

            screenshot_time = time.time() - screenshot_start
            logger.debug(f"截图耗时: {screenshot_time:.2f}s")

            total_time = time.time() - load_start
            logger.info(f"请求{self.request_count} - 总耗时: {total_time:.2f}s")

            # 6. 内存清理（定期触发）
            await self._auto_cleanup()
            return image_data

        except Exception as e:
            logger.error(f"截图失败: {e}")
            raise

        finally:
            # 7. 快速清理
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass

            # 8. 非会话页面立即关闭（避免内存累积）
            if page and not session_id:
                try:
                    await page.context.close()
                except:
                    pass

    async def _smart_wait(self, page: Page):
        """智能等待页面渲染完成"""
        try:
            # 1. 等待基本加载
            await page.wait_for_load_state('load', timeout=5000)

            # 2. 检查自定义就绪标志
            await page.wait_for_function(
                "window.__screenshot_ready === true",
                timeout=3000
            )

            # 3. 等待图片加载（如果有）
            await page.wait_for_function(
                """
                () => {
                    if (!window.__images_total) return true;
                    return window.__images_loaded >= window.__images_total;
                }
                """,
                timeout=5000
            )

            # 4. 微等待确保渲染稳定
            await asyncio.sleep(0.1)

            # 5. 执行用户JS（如果有异步操作）
            await page.evaluate("""
                                // 触发可能的异步渲染
                                if (window.__renderComplete) {
                                    return window.__renderComplete();
                                }
                                return Promise.resolve();
                                """)

            # 6. 最终微等待
            await asyncio.sleep(0.05)

        except Exception as e:
            logger.debug(f"智能等待超时/中断: {e}")
            # 即使等待失败也继续，可能页面已经可用

    async def _auto_cleanup(self):
        """自动内存清理"""
        now = time.time()

        # 每50个请求强制GC一次
        if self.request_count % self.gc_count == 0:
            gc.collect()
            self.last_gc = now
            logger.debug("强制垃圾回收完成")

        # 每10分钟清理过期会话
        if now - self.last_gc > 600:
            expired = []
            for sid, page in list(self.context_pages.items()):
                try:
                    if page.is_closed():
                        expired.append(sid)
                except:
                    expired.append(sid)

            for sid in expired:
                del self.context_pages[sid]

            gc.collect()
            self.last_gc = now
            logger.info(f"清理了 {len(expired)} 个过期会话")

    async def close(self):
        """关闭服务"""
        logger.info("关闭截图服务...")

        # 清理页面
        for page in list(self.context_pages.values()):
            try:
                context = page.context
                await page.close()
                await context.close()
            except:
                pass
        self.context_pages.clear()

        # 关闭浏览器
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None
        if hasattr(self, 'playwright') and self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
            self.playwright = None
        # 清理临时目录
        try:
            for f in self.temp_dir.glob("temp_*.html"):
                f.unlink()
        except:
            pass
        logger.info("服务已关闭")

    async def _images_to_gif(self, image_files: List[str], fps: int) -> bytes:

        """将图片列表转换为GIF"""
        if not image_files:
            raise Exception("没有图片可以转换为GIF")

        images = []
        for img_file in image_files:
            try:
                img = Image.open(img_file)
                images.append(img)
            except Exception as e:
                logger.error(f"加载图片失败 {img_file}: {e}")
                continue
        if not images:
            raise Exception("所有图片加载失败")

        # 将PIL图像转换为字节流
        output = io.BytesIO()

        # 计算每帧持续时间(毫秒)
        frame_duration = 1000 // fps

        # 保存为GIF
        images[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=images[1:],
            duration=frame_duration,
            loop=0,  # 无限循环
            optimize=True
        )
        return output.getvalue()
