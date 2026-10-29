import asyncio
import gc
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict

from PIL import Image
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page

from hikari_core.core.cache_utils import get_cache_file
from hikari_core.core.config import hikari_config


class BrowserRenderError(RuntimeError):
    """浏览器端模板渲染没成功（模板报错 / 渲染器资源缺失 / 等不到完成标记）。

    ▍为什么单独一个类型：默认这条路只打日志、照常截图（用户拿到一张写着报错的图），
      但接入端可能更想要"回一条文本错误"。配上 `hikari_config.render_error_fallback=True`
      这个异常会被抛到 `output_hikari`，由它转成 `hikari.error(...)`。
      注意：只有在页面里含 `hikari-render.js`（即模板渲染那条路）时才会抛，
      markdown / 纯文本渲染不受影响。
    """


class RenderBusyError(RuntimeError):
    """渲染并发已满：排队数量超限或排队等待超时。

    属于**可恢复的过载保护**，上层应回一句「稍后再试」，而不是当作渲染 bug。
    """


class RenderTimeoutError(RuntimeError):
    """单个渲染请求超过 `render_timeout` 的硬超时，槽位已被强制释放。"""


class minimal_screens_hot_service:
    _instance = None
    _initialized = False
    # 冷启动并发：多个请求同时进来时，只让一个去启动浏览器，其余等待
    _start_lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def get_instance(cls):
        async with cls._start_lock:
            instance = cls._instance
            if instance is not None and instance.browser is not None and instance.browser.is_connected():
                return instance
            if instance is None:
                instance = cls._instance = minimal_screens_hot_service()
            try:
                await instance.start()
            except Exception:
                # 重置单例，免得后续查询拿到 browser=None 的半成品
                cls._instance = None
                raise
            return instance

    def __init__(self):
        self.playwright = None
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.browser: Optional[Browser] = None
        self.user_browser =  None
        self.context_pages: Dict[str, Page] = OrderedDict()  # 会话页面缓存（LRU）
        self._page_ts: Dict[str, float] = {}  # 会话页面最近使用时间
        self.temp_dir = get_cache_file() / "browser_temp"
        self.temp_dir.mkdir(exist_ok=True)
        self.gc_count = 50
        # 内存监控
        self.last_gc = time.time()
        self.request_count = 0
        # 过载保护：并发槽位 + 有界排队
        self._capacity = max(1, int(hikari_config.render_concurrency))
        self._sem = asyncio.Semaphore(self._capacity)
        self._active = 0
        self._waiting = 0
        self._last_recycle = 0
        self._recycle_lock = asyncio.Lock()

    async def start(self):
        """启动 Playwright 与浏览器内核；失败直接抛错，不留 browser=None 的半成品。"""
        from hikari_core.core.config import hikari_config
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None
        await self._stop_playwright()
        self.user_browser = hikari_config.use_broswer
        # 浏览器临时 profile 落缓存目录（必须在 start() 之前，理由见 use_cache_as_browser_temp）
        self.temp_dir = self.use_cache_as_browser_temp()
        self.playwright = await async_playwright().start()
        try:
            if hikari_config.use_broswer == 'chromium':
                ok = await self.chromium()
            else:
                ok = await self.firefox()
        except Exception:
            await self._stop_playwright()
            raise
        if not ok or self.browser is None:
            await self._stop_playwright()
            raise RuntimeError(
                f"浏览器（{hikari_config.use_broswer}）启动失败，请检查 Playwright 浏览器内核"
            )

    async def _stop_playwright(self):
        """停掉 Playwright，忽略关闭过程中的异常。"""
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

    @staticmethod
    def use_cache_as_browser_temp() -> Path:
        """把浏览器（Playwright）的临时目录指到缓存目录下，返回该目录。

        ▍要解决什么：Playwright 把浏览器的临时 profile 建在 os.tmpdir()（Windows 是 %TEMP%），
          实测某些机器上**非安装版内核**在那儿建不出单例锁文件 ——
              Lock file can not be created: 拒绝访问。 (0x5)
              Failed to create a ProcessSingleton for your profile directory ... Aborting
          Chrome 为防 profile 损坏直接退出（exitCode=21），Playwright 只报一句
          「profile is already in use」，页面根本没渲染（系统装的 Chrome 在同一条路径下却没事）。
          同一份内核把 profile 放到缓存目录就能正常启动，所以这里统一挪过去。

        ▍为什么必须在 async_playwright().start() **之前**调用：profile 路径是 Playwright 的
          node driver 进程按**它自己的**环境变量算出来的（node 的 os.tmpdir()）。
          start() 之后才改 os.environ、或者给 launch(env=...) 传变量，都影响不到它。

        ▍三个变量一起写：Windows 读 TEMP / TMP，POSIX 读 TMPDIR；多写一个不影响什么，
          少写一个就在那个平台静默失效（又退回 %TEMP%）。
        """
        temp_dir = get_cache_file() / "browser_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        for key in ('TEMP', 'TMP', 'TMPDIR'):
            os.environ[key] = str(temp_dir)
        return temp_dir

    async def chromium(self):
        browser_path = minimal_screens_hot_service.setup_playwright(browser="chromium")
        if not browser_path:
            logger.error("未找到可用的 chromium 内核（Playwright 安装失败），跳过启动")
            return False
        logger.info(f"使用浏览器: {browser_path}")
        try:
            start_time = time.time()
            # 使用最小的启动参数
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',  # 截图不需要GPU加速
                    # 渲染兼容性：不再禁用软件光栅化（去掉 --disable-software-rasterizer），
                    # 并强制软件合成。无 GPU 服务器上大背景图偶发空白/花屏多与此有关，
                    # 纯 CPU 光栅化+合成最稳定
                    '--disable-gpu-compositing',
                    '--force-color-profile=srgb',
                    # 允许加载本地资源和跨域
                    '--disable-web-security',
                    '--allow-file-access-from-files',
                    '--allow-running-insecure-content',
                    # 内存硬上限：渲染进程数与应用层并发槽位一致；
                    # 单渲染进程 V8 堆封顶，防止异常页面把整机吃空
                    f'--renderer-process-limit={self._capacity}',
                    '--js-flags=--max-old-space-size=512',
                    '--disable-background-networking',
                    '--disable-extensions',
                    '--disable-sync',
                    '--no-first-run',
                    # 性能优化
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                ],
                # 关键：关闭信号处理，加速启动
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
                # 超时设置
                timeout=30000,
                executable_path=browser_path
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
                    timeout=30000,executable_path=browser_path
                )
                logger.info("使用最小参数启动成功")
                return True
            except Exception as e2:
                logger.error(f"回退启动也失败: {e2}")
                return False
    async def firefox(self):
        start_time = time.time()
        # 使用最小的启动参数
        browser_path = minimal_screens_hot_service.setup_playwright(browser="firefox")
        if not browser_path:
            logger.error("未找到可用的 firefox 内核（Playwright 安装失败），跳过启动")
            return False
        try:
            logger.info(f"使用浏览器: {browser_path}")
            self.browser = await self.playwright.firefox.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',  # 截图不需要GPU加速
                ],
                # 关键：关闭信号处理，加速启动
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
                # 超时设置
                timeout=30000,
                executable_path=browser_path
            )

            elapsed = time.time() - start_time
            logger.info(f"浏览器启动完成，耗时: {elapsed:.2f}秒")
            return True

        except Exception as e:
            logger.error(f"浏览器启动失败: {e}")
            # 尝试回退方案
            try:
                self.browser = await self.playwright.firefox.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage'],
                    timeout=30000,executable_path=browser_path
                )
                logger.info("使用最小参数启动成功")
                return True
            except Exception as e2:
                logger.error(f"回退启动也失败: {e2}")
                return False


    # 会话页面缓存上限：每个常驻页面都占一份渲染内存，必须有界
    _SESSION_CACHE_MAX = 8
    _SESSION_TTL = 600

    async def create_page(self, session_id: str = None) -> Page:
        """创建优化页面 - 快速轻量"""

        # 如果有会话缓存且页面有效，复用
        if session_id and session_id in self.context_pages:
            page = self.context_pages[session_id]
            try:
                if not page.is_closed():
                    # 快速重置页面（同时重置图片追踪标志，确保新页面背景图能被追踪）
                    await page.evaluate("""
                        document.body.innerHTML = '';
                        window.__bg_images_tracked = false;
                        window.__images_total = 0;
                        window.__images_loaded = 0;
                    """)
                    self.context_pages.move_to_end(session_id)
                    self._page_ts[session_id] = time.time()
                    return page
            except:
                pass
            stale = self.context_pages.pop(session_id, None)
            self._page_ts.pop(session_id, None)
            if stale is not None:
                try:
                    await stale.context.close()
                except Exception:
                    pass

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

                // 2b. 字体就绪标记（避免截图时文字处于字体加载间隙）
                window.__fonts_ready = false;
                if (document.fonts && document.fonts.ready) {
                    document.fonts.ready.then(
                        () => { window.__fonts_ready = true; },
                        () => { window.__fonts_ready = true; }
                    );
                } else {
                    window.__fonts_ready = true;
                }

                // 3. 图片加载追踪（包括 <img> 和 CSS background-image）
                window.__images_loaded = 0;
                window.__images_total = 0;
                window.__bg_images_tracked = false;

                function __trackImages() {
                    // 3a. 追踪 <img> 元素
                    const images = document.images;
                    window.__images_total = images.length;
                    window.__images_loaded = 0;

                    for (let img of images) {
                        if (img.complete) {
                            window.__images_loaded++;
                        } else {
                            img.onload = img.onerror = () => {
                                window.__images_loaded++;
                            };
                        }
                    }

                    // 3b. 追踪 CSS background-image（解决 page-header 等背景图丢失问题）
                    if (window.__bg_images_tracked) return;
                    window.__bg_images_tracked = true;
                    try {
                        const seen = new Set();
                        // 仅扫描有 class 属性的元素，避免过度 getComputedStyle 调用
                        const elements = document.querySelectorAll('[class]');
                        for (const el of elements) {
                            // 大背景图（poster）挂在 .main-content::before 上，元素自身
                            // 是 background-image:none —— 只读元素会漏掉它，截图可能在
                            // 海报解码完成前就落盘。所以元素 + 伪元素一起扫。
                            for (const pseudo of [null, '::before', '::after']) {
                                const bg = getComputedStyle(el, pseudo).backgroundImage;
                                if (!bg || bg === 'none') continue;
                                const matches = bg.match(/url\(["']?([^"')]+)["']?\)/g);
                                if (!matches) continue;
                                for (const m of matches) {
                                    const urlMatch = m.match(/url\(["']?([^"')]+)["']?\)/);
                                    if (urlMatch && urlMatch[1] && !seen.has(urlMatch[1])) {
                                        seen.add(urlMatch[1]);
                                    }
                                }
                            }
                        }
                        if (seen.size > 0) {
                            window.__images_total += seen.size;
                            for (const imgUrl of seen) {
                                const img = new Image();
                                const done = () => { window.__images_loaded++; };
                                img.src = imgUrl;
                                // 优先用 decode()：等待图片真正解码完成（更接近“可上屏”状态），
                                // 比 onload 更能避免大 banner 背景图截图时空白；旧浏览器退回 onload
                                if (typeof img.decode === 'function') {
                                    img.decode().then(done, done);
                                } else {
                                    img.onload = img.onerror = done;
                                }
                            }
                        }
                    } catch(e) {
                        // 静默失败，背景图追踪是尽力而为的
                    }
                }

                if (document.readyState !== 'loading') {
                    __trackImages();
                } else {
                    document.addEventListener('DOMContentLoaded', __trackImages);
                }
            })();
        """)

        if session_id:
            self.context_pages[session_id] = page
            self._page_ts[session_id] = time.time()
            # 超出上限时淘汰最久未用的会话，并真正关掉它的上下文释放内存
            while len(self.context_pages) > self._SESSION_CACHE_MAX:
                old_sid, old_page = self.context_pages.popitem(last=False)
                self._page_ts.pop(old_sid, None)
                try:
                    await old_page.context.close()
                except Exception:
                    pass

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

    def _on_render_error(self, message: str) -> None:
        """浏览器端渲染失败时的统一出口。

        默认（`render_error_fallback=False`）只记日志、继续截图 —— 保持历史行为：
        用户收到的是一张**带着报错信息**的图，而不是什么都没有。
        置 True 时抛出 `BrowserRenderError`，让上层 `output_hikari` 回一条文本错误。
        """
        logger.error(message)
        if hikari_config.render_error_fallback:
            raise BrowserRenderError(message)

    @asynccontextmanager
    async def _render_slot(self):
        """获取一个渲染槽位（过载保护）。

        三层限制，从内到外：
          1. 排队数超过 `render_queue_size` → 立即 RenderBusyError（不再堆积任务）；
          2. 排队超过 `render_queue_timeout` 秒 → RenderBusyError；
          3. 拿到槽位后最多占用 `render_timeout` 秒（由调用方套硬超时）。
        没有这层限制时，每个请求都会 new 一个 Chromium 渲染进程，
        突发请求会把 2核4G 机器的内存直接打满。
        """
        if self._waiting >= hikari_config.render_queue_size:
            raise RenderBusyError('渲染请求过多，请稍后再试')
        self._waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=hikari_config.render_queue_timeout)
        except TimeoutError:
            raise RenderBusyError('渲染排队超时，请稍后再试') from None
        finally:
            self._waiting -= 1
        self._active += 1
        try:
            yield
        finally:
            self._active -= 1
            self._sem.release()
            try:
                await self._maybe_recycle_browser()
            except Exception as e:
                logger.error(f'检查浏览器内核重建失败: {e}')

    async def _maybe_recycle_browser(self):
        """周期性重建浏览器内核，释放长期运行累积的内存碎片。

        只有在没有任何渲染进行时才重建；重建期间独占全部槽位，新请求照常排队。
        """
        if self._active > 0 or self.request_count - self._last_recycle < 500:
            return
        if self._recycle_lock.locked():
            return
        # 先拿排他锁再占槽位：避免两个收尾任务互相等对方手里的槽位而死锁
        async with self._recycle_lock:
            if self._active > 0 or self.request_count - self._last_recycle < 500:
                return
            for _ in range(self._capacity):
                await self._sem.acquire()
            try:
                logger.info(f'已渲染 {self.request_count} 次，重建浏览器内核以释放内存')
                await self._restart_browser()
                self._last_recycle = self.request_count
            finally:
                for _ in range(self._capacity):
                    self._sem.release()

    async def _restart_browser(self):
        """关闭并重新拉起浏览器内核（调用方需保证没有页面在使用）。"""
        for page in list(self.context_pages.values()):
            try:
                await page.context.close()
            except Exception:
                pass
        self.context_pages.clear()
        self._page_ts.clear()
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        self.browser = None
        try:
            if self.user_browser == 'firefox':
                await self.firefox()
            else:
                await self.chromium()
        except Exception as e:
            logger.error(f'重建浏览器内核失败: {e}')

    async def screenshot(self, html_content: str, session_id: str = None, **kwargs) -> bytes:
        """核心截图入口：受并发槽位与硬超时保护。"""
        async with self._render_slot():
            try:
                async with asyncio.timeout(hikari_config.render_timeout):
                    return await self._screenshot_impl(html_content, session_id, **kwargs)
            except TimeoutError:
                logger.warning(f'渲染硬超时（>{hikari_config.render_timeout:.0f}s），已强制释放槽位')
                raise RenderTimeoutError('渲染超时，请稍后再试') from None
            finally:
                await self._auto_cleanup()

    async def _screenshot_impl(self, html_content: str, session_id: str = None, **kwargs) -> bytes:
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

            # =========================
            # 禁用动画（非常重要）
            # =========================
            await page.add_style_tag(content="""
            *,
            *::before,
            *::after {
                animation: none !important;
                transition: none !important;
                caret-color: transparent !important;
            }
            """)

            # 关键：使用最快加载模式
            await page.goto(
                f"file://{temp_file}",
                wait_until='networkidle',
                timeout=10000,  # 10秒超时
            )

            # =========================
            # 提前设置最终视口：让布局在就绪等待前定型
            # （原先在图片就绪之后才 set_viewport_size，重新布局后
            #   banner 背景来不及重绘就截图，是 page-header 偶发空白的诱因之一）
            # =========================
            view = kwargs["viewport"]
            await page.set_viewport_size(view)

            # =========================
            # 强制 reflow
            # =========================
            await page.evaluate("""
                            () => {
                                document.body.offsetHeight;
                            }
                            """)
            load_time = time.time() - load_start
            logger.debug(f"页面加载: {load_time:.2f}s")

            # =========================
            # 浏览器端渲染：等待渲染完成
            # =========================
            # 送进来的是「数据 + 模板源码」的外壳时，真正的整页要等 hikari-render.js
            # 在浏览器里渲染完才存在。判断方式是**看 HTML 里有没有渲染器脚本** ——
            # 这个服务也被 markdown / 纯文本渲染共用（那些页面没有渲染器，不必等）。
            # 渲染完 DOM 会被整体替换，所以这一步必须排在字体/图片等待**之前**。
            if 'hikari-render.js' in html_content:
                try:
                    await page.wait_for_function(
                        '() => window.__hikari_render_done !== undefined',
                        timeout=15000,
                    )
                    render_state = await page.evaluate('() => window.__hikari_render_done')
                except Exception:
                    self._on_render_error('等待浏览器端渲染超时（模板报错 / 资源缺失？）')
                else:
                    if render_state is not True:
                        self._on_render_error(f'浏览器端渲染失败: {render_state}')

            # 4. 智能等待渲染（load / 字体 / 图片解码 / 绘制稳定）
            await self._smart_wait(page)

            # =========================
            # 等待 compositor 提交两帧 + 微等待
            # 解决半渲染 / 背景图未上屏问题
            # =========================
            await page.evaluate("""
                            () => new Promise(resolve => {
                                requestAnimationFrame(() => {
                                    requestAnimationFrame(() => {
                                        resolve();
                                    });
                                });
                            })
                            """)
            await page.wait_for_timeout(100)
            # 5. 快速截图
            screenshot_start = time.time()
            # 输出格式：jpeg(默认，最快) / png / webp
            image_type = str(kwargs.get('type') or 'jpeg').lower()
            quality = kwargs.get('quality')
            if image_type == 'png':
                image_data = await page.screenshot(
                    type='png',
                    full_page=True,  # 只截取可视区域
                    omit_background=False,
                )
            elif image_type == 'webp':
                # Playwright >=1.62 原生支持 webp：quality 缺省或 >=100 时驱动会走「无损」编码，
                # 体积明显大于 jpeg@85，故与 jpeg 一致默认 85（有损）
                image_data = await page.screenshot(
                    type='webp',
                    quality=quality if quality is not None else 85,
                    full_page=True,  # 只截取可视区域
                    omit_background=False,
                )
            else:
                image_data = await page.screenshot(
                    type='jpeg',  # JPEG最快
                    quality=quality if quality is not None else 85,
                    full_page=True,  # 只截取可视区域
                    omit_background=False,
                )

            screenshot_time = time.time() - screenshot_start
            logger.debug(f"截图耗时: {screenshot_time:.2f}s")

            total_time = time.time() - load_start
            logger.info(f"请求{self.request_count} - 总耗时: {total_time:.2f}s")

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
        """GIF 截图入口：与 screenshot 共用同一套并发槽位与硬超时保护。"""
        async with self._render_slot():
            try:
                async with asyncio.timeout(hikari_config.render_timeout):
                    return await self._screenshot_gif_impl(html_content, session_id, fps, duration)
            except TimeoutError:
                logger.warning(f'GIF 渲染硬超时（>{hikari_config.render_timeout:.0f}s），已强制释放槽位')
                raise RenderTimeoutError('渲染超时，请稍后再试') from None
            finally:
                await self._auto_cleanup()

    async def _screenshot_gif_impl(self, html_content: str, session_id: str = None,
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
        """智能等待页面渲染完成（load / 字体 / 图片解码 / 绘制稳定）"""
        try:
            # 1. 等待基本加载
            await page.wait_for_load_state('load', timeout=5000)
            # 2. 检查自定义就绪标志
            await page.wait_for_function(
                "window.__screenshot_ready === true",
                timeout=3000
            )
            # 3. 等待字体就绪
            await page.wait_for_function(
                "window.__fonts_ready === true",
                timeout=3000
            )
            # 4. 等待图片加载/解码完成（如果有）
            await page.wait_for_function(
                """
                () => {
                    if (!window.__images_total) return true;
                    return window.__images_loaded >= window.__images_total;
                }
                """,
                timeout=5000
            )
            # 5. 强制提交两帧，确保 CSS 背景图等已真正上屏
            await page.evaluate(
                """
                () => new Promise(resolve => {
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => resolve());
                    });
                })
                """
            )
            # 6. 微等待确保渲染稳定
            await asyncio.sleep(0.1)
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

        # 每10分钟清理过期会话：空闲超过 TTL 的页面直接关闭并移出缓存，
        # 否则常驻页面会一直占着渲染内存（旧实现只移除已关闭的页面）
        if now - self.last_gc > 600:
            expired = [
                sid for sid, ts in self._page_ts.items()
                if now - ts > self._SESSION_TTL
            ]
            for sid in expired:
                page = self.context_pages.pop(sid, None)
                self._page_ts.pop(sid, None)
                if page is not None:
                    try:
                        await page.context.close()
                    except Exception:
                        pass

            gc.collect()
            self.last_gc = now
            if expired:
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
        self._page_ts.clear()

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
        # 只清截图临时文件、重置单例，保留已下载的浏览器内核
        try:
            for f in self.temp_dir.glob("temp_*.html"):
                f.unlink()
        except:
            pass
        type(self)._instance = None
        logger.info("截图服务已关闭（已保留 Playwright 浏览器内核）")

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

    @staticmethod
    def _expected_revision(browser: str) -> str:
        """读取当前安装的 Playwright 所期望的浏览器构建号（如 chromium-1234 中的 1234）。

        Playwright 每次发版都会配套升级浏览器内核；升级 playwright 后若仍用旧缓存内核，
        可能出现 CDP 协议不兼容 / 新功能（如 webp 截图）不可用的问题，需要据此触发重装。
        """
        try:
            import playwright
            browsers_json = Path(playwright.__file__).resolve().parent / 'driver' / 'package' / 'browsers.json'
            if browsers_json.exists():
                data = json.loads(browsers_json.read_text(encoding='utf-8'))
                for item in data.get('browsers', []):
                    if item.get('name') == browser:
                        return str(item.get('revision', ''))
        except Exception as e:
            logger.debug(f"读取 playwright 期望浏览器版本失败: {e}")
        return ''

    @staticmethod
    def _run_playwright_install(browser: str):
        """用 Playwright 自带的 node driver 安装浏览器内核。
        """
        env = dict(os.environ)
        try:
            from playwright._impl._driver import (
                compute_driver_executable,
                get_driver_env,
            )

            node, cli = compute_driver_executable()
            env.update(get_driver_env())
            cmd = [node, cli, "install", browser]
        except Exception as e:
            logger.warning(f"获取 Playwright driver 失败（{e}），回退到 python -m playwright")
            env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
            cmd = [sys.executable, "-m", "playwright", "install", browser]
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(get_cache_file() / "browsers")
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright/"
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    @staticmethod
    def setup_playwright(browser: str = "chromium") -> str:
        """准备浏览器内核，返回可执行文件路径（失败返回 None）。

        只有确实找到可执行文件才写 .<browser>-env 标记，避免一次失败后永不重试。
        """
        # 1. 确定安装路径
        browsers_path = get_cache_file() / "browsers"
        browsers_path.mkdir(parents=True, exist_ok=True)
        env_file = browsers_path / f".{browser}-env"
        expected_revision = minimal_screens_hot_service._expected_revision(browser)

        # 2. 快路径：标记匹配且内核真的在
        if env_file.exists():
            marker_text = env_file.read_text(encoding='utf-8', errors='ignore')
            marker_ok = (not expected_revision) or f"REVISION={expected_revision}" in marker_text
            if marker_ok:
                executable = minimal_screens_hot_service.find_executable(browser, browsers_path)
                if executable:
                    return executable
                logger.info(f"缓存标记存在但内核缺失（{browsers_path}），重新安装 {browser}")
            else:
                logger.info(
                    f"检测到 Playwright 升级或标记过期（期望 {browser} 构建 {expected_revision or '未知'}），"
                    f"将重新安装 {browser}"
                )

        # 3. 安装到插件缓存目录
        os.environ['PLAYWRIGHT_DOWNLOAD_HOST'] = 'https://npmmirror.com/mirrors/playwright/'
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(browsers_path)
        logger.info(f"🎯 Playwright 浏览器将安装到: {browsers_path}")

        # 4. 安装系统依赖（只有 Linux 需要）
        if sys.platform != "win32":
            logger.info("正在安装系统依赖...")
            try:
                from playwright._impl._driver import (
                    compute_driver_executable,
                    get_driver_env,
                )

                node, cli = compute_driver_executable()
                env = get_driver_env()
                env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
                subprocess.run([node, cli, "install-deps"], check=False, env=env)
            except Exception as e:
                logger.debug(f"跳过 install-deps: {e}")

        # 5. 安装浏览器
        logger.info(f"正在安装 {browser}...")
        result = minimal_screens_hot_service._run_playwright_install(browser)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:500]
            logger.error(f"❌ {browser} 安装失败（exit {result.returncode}）: {detail}")
            try:
                env_file.unlink()
            except OSError:
                pass
            return None

        # 6. 验证安装
        executable = minimal_screens_hot_service.find_executable(browser, browsers_path)
        if not executable:
            logger.error(f"❌ {browser} 安装后仍未找到可执行文件: {browsers_path}")
            try:
                env_file.unlink()
            except OSError:
                pass
            return None

        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(f"PLAYWRIGHT_BROWSERS_PATH={browsers_path}\n")
            f.write(f"REVISION={expected_revision}\n")
        logger.info(f"✅ {browser} 安装完成: {executable}")
        return executable

    @staticmethod
    def find_executable(browser_type: str = "chromium", browser_path: Path = None):
        system = platform.system().lower()
        config_file = get_cache_file() / "browsers-find-executable.json"
        try:
            if config_file.exists():
                patterns = json.loads(config_file.read_text())
            else:
                patterns = {
                    'chromium': {
                        'windows': 'chromium-*/chrome-win*/chrome.exe',
                        'linux': 'chromium-*/chrome-linux*/chrome',
                        'darwin': 'chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium'
                    },
                    'firefox': {
                        'windows': 'firefox-*/firefox*/firefox.exe',
                        'linux': 'firefox-*/firefox*/firefox',
                        'darwin': 'firefox-*/firefox*/Firefox.app/Contents/MacOS/firefox'
                    }
                }
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(patterns, f, indent=2, ensure_ascii=False)

            pattern = patterns.get(browser_type, {}).get(system)
            if pattern:
                matches = list(browser_path.glob(pattern))
                if matches:
                    # 多版本缓存共存时取构建号最大的（升级 playwright 后避免仍命中旧内核）
                    def _build_revision(p: Path) -> int:
                        m = re.search(rf'{re.escape(browser_type)}-(\d+)', str(p))
                        return int(m.group(1)) if m else 0
                    matches.sort(key=_build_revision, reverse=True)
                    return str(matches[0])
        except Exception as e:
            logger.error(f"无法找到浏览器: {e}")
        return None
