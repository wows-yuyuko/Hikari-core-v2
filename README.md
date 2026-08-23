# Hikari-core

**战舰世界 yuyuko 平台 BOT SDK** —— 指令解析 + yuyuko API 查询 + 模板渲染出图。

```bash
pip install hikari-core
```

- 环境要求：Python 3.11 ~ 3.12
- 依赖：`httpx` / `APScheduler` / `jinja2` / `pydantic` / `playwright` / `loguru` / `pillow`
- 首次使用会自动下载 playwright chromium 浏览器（用于模板渲染截图）

---

## 接入方式

### 1. 基础流程

```python
import asyncio

from hikari_core import init_hikari, set_hikari_config

set_hikari_config(
    token='你的APIKey:Token',   # 请联系开发者获取
    game_path='./data',        # 缓存目录（浏览器/模板/舰船图）
    command_language='zh',     # 指令提示语言: zh / en
)

async def on_message(platform: str, platform_id: str, text: str):
    """接入端在收到消息时调用。text 为去掉 wws 前缀后的指令文本。"""
    hikari = await init_hikari(platform, platform_id, text)

    if hikari.Status == 'success':
        # Output.Data 为图片 bytes（auto_image=True 时）或文本
        return hikari.Output.Data
    elif hikari.Status == 'wait':
        # 需要用户选择（如船名/绑定多选）：提示用户回复序号，暂存 hikari 对象
        return hikari.Output.Data
    else:
        # failed / error：Output.Data 为提示文案
        return hikari.Output.Data
```

### 2. 参数说明

| 参数 | 说明 |
|---|---|
| `init_hikari(platform, PlatformId, command_text, GroupId=None, Ignore_List=None)` | `platform`：平台类型（`QQ` / `QQ_CHANNEL` / `QQ_OFFICIAL` 等）；`PlatformId`：发送者 ID；`command_text`：指令文本（**不带 wws 前缀**）；`GroupId`：群号；`Ignore_List`：禁用的功能函数列表 |

`Hikari_Model` 关键字段：

| 字段 | 说明 |
|---|---|
| `Status` | `success`（输出图片/文本）/ `wait`（等待用户选择）/ `failed` / `error`（提示文案） |
| `Output.Data` | 图片 bytes 或文本 |
| `Output.Template` / `Output.Width` / `Output.Height` | 使用的模板与视口参数 |

### 3. 多选（wait）回调

当出现多个匹配（如船名重名、绑定列表）时返回 `wait` 状态，接入端引导用户回复序号后回调：

```python
from hikari_core import callback_hikari

async def on_user_reply(stored_hikari, reply_index: int):
    stored_hikari.Input.Select_Index = reply_index
    hikari = await callback_hikari(stored_hikari)
    return hikari.Output.Data
```

### 4. 配置项（`set_hikari_config`）

| 参数 | 说明 |
|---|---|
| `token` | yuyuko API 凭据 |
| `proxy` | 访问 WG 的代理（如 `http://localhost:7890`） |
| `auto_rendering` / `auto_image` | 是否自动渲染模板 / 是否自动截图出图 |
| `use_broswer` | `chromium`（默认）/ `firefox` |
| `game_path` | 缓存目录路径（推荐放在 bot 目录下） |
| `command_language` | `zh`（默认）/ `en`，切换指令提示与帮助页语言 |
| `command_suggest_max` | 指令输错智能提示条数（默认 3，0 关闭） |
| `command_suggest_dedupe` | 同功能多别名只提示一条（默认开启） |
| `save_template_html` | 调试：渲染时额外保存 HTML 到 `<缓存目录>/template_html/`（默认关闭） |

---

## 关于 @ 提及的处理

**SDK 内部不再解析 @ 消息**，@ 的处理完全由接入端负责：

- 接入端应在把消息交给 SDK 前，**将 @ 提及转换为等价的 `me` 指令文本**。例如用户"@机器人 大和"或"@群友 单船 大和"，接入端应转换为 `me 大和` / `me 单船 大和` 再调用 `init_hikari`。
- **不要**把原始 @ token（如 `CQ:at,qq=123`、`<@!123>`）直接拼进 `command_text`——SDK 不识别这些格式，会当作普通参数导致解析错乱。
- SDK 内的身份指定仅两种：
  - `me` —— 查询发送者自己
  - `<服务器> <昵称>` —— 指定服务器与游戏昵称

---

## 支持的指令

> 以下指令中的 `wws` 前缀由接入端去除，`command_text` 不包含它；`<必填>`、`[可选]`。

### 📊 水表查询

| 指令 | 说明 |
|---|---|
| `wws <服务器> <昵称>` | 查询账号总表（水表） |
| `wws ship <船名>` / `wws 单船 <船名>` | 查询单船水表（支持多词英文船名，如 `Jean Bart`） |
| `wws recent [天数或日期]` / `wws 近期` | 查询账号近期战绩 |
| `wws ship <船名> recent [天数或日期]` | 查询单船近期战绩（也可 `wws recent ship <船名>`） |
| `wws recents` / `wws 单场近期` | 查询单场近期战绩 |

### 🏆 排行榜

| 指令 | 说明 |
|---|---|
| `wws ship.rank <服务器> <船名>` | 单船排行榜（也可 `wws rank ship …`） |
| `wws cw.rank [服务器] [赛季]` | 军团战排行榜（留空为全服最新赛季） |
| `wws clan.rank <服务器> <公会TAG>` | 军团排行榜（也可 `wws rank clan …`） |

### 🛡️ 军团 / 公会

| 指令 | 说明 |
|---|---|
| `wws clan <服务器> <公会TAG>` / `wws 军团 …` | 查询公会基础信息 |
| `wws cw.recent <服务器> <公会TAG> [赛季] [队数]` | 查询公会军团战近期战绩 |

### 🔗 账号绑定

| 指令 | 说明 |
|---|---|
| `wws bind <服务器> <昵称>` / `wws 绑定 …` | 绑定游戏账号 |
| `wws special_bind <AID>` / `wws 特殊绑定 <AID>` | 按 AID 绑定（网页版复制指令） |
| `wws bind_list me` / `wws 查询绑定 me` | 查看绑定列表 |
| `wws change_bind [序号]` / `wws 切换绑定 [序号]` | 切换绑定（无序号弹出选择列表） |
| `wws delete_bind <序号>` / `wws 删除绑定 <序号>` | 删除绑定 |

### 🎮 娱乐

| 指令 | 说明 |
|---|---|
| `wws roll [国家] [舰种] [等级]` / `wws 随机 …` | 随机抽船（可过滤条件） |
| `wws sx` / `wws 扫雪` | 查询扫雪收益 |
| `wws ban [服务器] [昵称]` / `wws 封号记录 …` | 查询封禁记录（仅国服） |
| `wws box` / `wws sd` / `wws 圣诞船池` | 查询圣诞箱船池 |
| `wws search_ship <国家> <舰种> <等级>` / `wws 搜船名 …` | 按条件查询船名 |

### ⚙️ 系统

| 指令 | 说明 |
|---|---|
| `wws help` / `wws 帮助` | 查看中/英双语 H5 帮助页 |
| `wws check_version` / `wws 检查更新` | 检查版本；检测到新版本时自动 `git pull origin main` 同步仓库 |
| `wws update_style` / `wws 更新样式` | 从 OSS 更新模板样式 |
| `wws update_ship` / `wws 更新战舰` | 更新战舰图片资源 |

---

## 其他

- **模板渲染**：Jinja2 模板（`hikari_core/Template/*-v5.html`）+ playwright 截图出图；模板资源可通过 OSS 清单更新
- **调试**：开启 `save_template_html` 后，每次渲染的 HTML 会保存到缓存目录 `template_html/`，可在浏览器直接打开复现
- **测试**：`python tests/test_command_suggest.py`（指令路由单测）、`python tests/test_templates_render.py`（模板渲染回归）
- **版本号**：定义于 `hikari_core/__init__.py` 的 `__version__`
- **许可证**：GNU General Public License（详见 [LICENSE](LICENSE)）
