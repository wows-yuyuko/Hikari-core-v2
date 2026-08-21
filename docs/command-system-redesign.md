# Hikari-core 指令系统审查与重构设计

> 状态：评审稿（待团队确认）
> 范围：指令路由 + 参数解析（`command_select.py` / `analyze.py` / `utils.py` / `model.py` 相关部分）
> 背景：当前指令支持的别名与触发方式过多（同一功能最多可达 10 种写法），路由与参数解析散落多处，新增功能需要同时改动 5 个文件。

---

## 1. 现状：指令处理流水线

```
init_hikari_no_output (__init__.py:50)
  └─ analyze_command (analyze.py:32)
       ├─ extract_with_special_name   (括号提取账号名, analyze.py:50)
       ├─ select_command              (关键词路由, command_select.py:111)
       │    └─ findFunction_and_replaceKeywords  (扁平表 + 子串匹配)
       ├─ extract_with_me_or_at       (me/@ 提取, analyze.py:64)
       └─ extract_with_function       (按函数对象二次分发到 _HANDLERS, analyze.py:423)
  └─ hikari.Function(hikari)          (执行真正的 API 处理器)
```

当前要完整支持一个功能，需要散落修改 **5 处**：

| # | 文件 | 内容 |
|---|---|---|
| 1 | `command_select.py` | `first_command_list` 注册 + import 处理器 |
| 2 | `analyze.py` | import 处理器 + `_HANDLERS` 分发表 |
| 3 | `analyze.py` | 手写 `_handle_*` 参数解析函数 |
| 4 | 远程 OSS | `wws_help.txt` 帮助文本 |
| 5 | （可选） | `tests/auto_test.py` 冒烟样例 |

核心痛点：**指令的定义、匹配、参数解析、帮助文案没有一处集中的声明**。

---

## 2. 问题清单

### 2.1 P0 — 路由方式过多且互为冗余

同一语义存在多条独立语法路线：

| 语义 | 可达触发方式（去重后） |
|---|---|
| `get_ShipRank` | `ship.rank` / `单船排行榜` / `战舰排行榜` / `rank` / `排行榜` / `rank ship` / `rank 单船` / `排行榜 单船` / `rank 战舰` / `排行榜 战舰` — **10 种** |
| `get_ShipRecent` | `ship X recent` / `单船 X 近期` / `recent ship X` / `近期 单船 X` — 4+ 种 |
| `get_ClanRank` | `clan.rank` / `军团排行榜` / `公会排行榜` / `rank clan` / `rank 军团` / `rank 公会` / `排行榜 军团` / `clan rank` / `军团 排行榜` — **9 种** |
| `get_ClanInfo` | `clan` / `军团` / `公会` / `工会`（错别字兼容） |
| `set_BindInfo` | `bind` / `绑定` / `set`（英文单词做指令） |
| `get_BindInfo` | `查询绑定` / `绑定查询` / `绑定列表` / `查绑定` |
| box | `box` / `sd`（无意义缩写）/ `圣诞船池` |

根因：`command_select.py:62-93` 的 `first_command_list` 同时保留了「点号风格（`ship.rank`）」和「二级路由（`rank ship`）」两条语法路线，`recent` / `recents` / `recent ship` / `ship recent` 又互相交叉。每新增一个功能，别名与维护成本叠加，帮助文档必然与代码脱节。

### 2.2 P0 — 匹配语义不统一、大小写敏感不一致

三套匹配函数并存：

| 函数 | 位置 | 语义 | 现状 |
|---|---|---|---|
| `match_keywords` | utils.py:35 | 精确匹配、忽略大小写 | analyze 参数解析在用 |
| `find_and_replace_keywords` | utils.py:55 | 子串匹配、区分大小写 | **死代码，全项目无调用** |
| `findFunction_and_replaceKeywords` | command_select.py:96 | 子串匹配、**区分大小写** | 路由在用 |

实际 bug：`wws SHIP 大和` / `wws Rank ship` 路由不到任何命令，落到兜底 `get_AccountInfo`，把 `SHIP` 当游戏昵称去请求 API。全角/半角括号（`（）` vs `()`）也未做 token 归一化。

### 2.3 P1 — 子串匹配 + 列表顺序强耦合

`findFunction_and_replaceKeywords` 用 `match_kw.find(kw) + 1`（command_select.py:100）做子串命中，再 `str.replace(kw, '')` 删除（:101）。

- `'ship'` 会子串命中 `'ship.rank'`；`'recent'` 会命中 `'recents'`；`'rank'` 会命中 `'ship.rank'` / `'clan.rank'`。当前全靠列表顺序兜住：`ship.rank`(13) 必须在 `rank`(17) 前，`recents`(19) 必须在 `recent`(20) 前。注释（:62）只约束"同命令内长词靠前"，**跨命令顺序是纯人工约定**，新增指令插错位置即静默错乱。
- 命中即返回第一个匹配，无最长匹配、无歧义检测、无候选提示。
- `str.replace` 替换 token 内所有出现；`'sd'` 这类双字母缩写命中面过大。

### 2.4 P1 — 两级路由靠哨兵值表达

`command` dataclass（command_select.py:34-39）用 `func=None` 表示"进入二级"，`default_func` 表示"二级未命中兜底"。`rank`→默认单船排行、`recent`→默认账号近期、`ship`→默认单船信息、`clan`→默认公会信息，全是隐式约定；`command(None, default_func, None)`（:106）的临时对象构造可读性差。

### 2.5 P1 — 参数解析全部手写、散落、易错

`analyze.py` 中 15 个 `_handle_*` 函数，每个都在做位置索引校验（如 :175/:187/:240/:256）、手写错误文案、重复调用 `match_keywords(…, servers)`（:176/:189/:223/:258/:286/:298/:322/:341/:361 共 9 处）、数字/日期/赛季提取（`_extract_day_and_date_params`、`_pop_digits_from_list`、`_handle_cw_rank`…）。

具体缺陷：

- `_parse_ship_query_params`（analyze.py:184-199）取 `Command_List[0]` / `[1]` 作为船名 → **带空格的英文船名（如 "Jean Bart"）永远查不了**，直接报"参数缺少或溢出"。
- `Search_Type` 1/2/3 魔数（model.py:36），仅靠注释说明。
- 平台特判 `_apply_qq_official_default`（analyze.py:88-97）埋在通用解析链路中。

### 2.6 P1 — 括号提取 `(名字)` 是第三种身份指定方式，且有毒

`extract_with_special_name`（analyze.py:50-61）正则 `(\(|（)(.*?)(\)|）)` 会把**任何**括号内容当账号名：`wws (1)` 的账号名是 `1`；船名带括号（`大和(测试)`）会被整体吞掉导致解析失败。与 me/@、server+name 三种身份指定方式并存，并与船名、备注产生歧义。

### 2.7 P2 — 重复与死代码

- `Func` Protocol 定义两处：command_select.py:28-31（`**kwargs` 签名）与 model.py:7-10（`hikari` 签名）——前者与实际签名不符，且两处都未真正用于运行时类型检查。
- `find_and_replace_keywords`（utils.py:55-74）全项目无调用。
- `levels` 列表 `'4'` 重复（data_source.py:47-48）。
- `__init__.py:15` `from .command_select import *` 通配导入，符号来源不可追踪。
- `matching.match_keywords` 字段（data_source.py:15）与 `match_keywords()` 函数（utils.py:35）同名，易混淆。
- `get_help` 从 OSS 远程拉取 `wws_help.txt`（game/help.py:24-38），指令表在代码里，两侧天然不同步。
- 测试 `tests/test.py`、`tests/auto_test.py` 依赖真实网络/账号/浏览器，无法作为指令路由的回归单测。

---

## 3. 目标设计：声明式命令树 + 类型化 token 解析

核心思想：把「扁平别名表 + 手写解析」升级为「命令树 + 参数 schema + 统一解析器」。每个功能只在一处声明，路由、参数绑定、校验、报错、帮助文本全部由框架推导。

### 3.1 新模块结构

```
hikari_core/commands/
  base.py      # Command / Argument / Router / TokenStream（框架）
  account.py   # info / recent / recents / ship / ship_recent 命令声明
  clan.py      # clan / cw_rank / cw_recent / clan_rank
  bind.py      # bind / special_bind / change / delete / 查询绑定
  other.py     # help / roll / sx / box / ban / 搜船名 / 更新
  __init__.py  # COMMAND_TREE 注册中心 + build_help()
analyze.py     # 重写为: normalize → route → bind → identity
```

### 3.2 核心声明

```python
# commands/base.py
class Kind(StrEnum):
    SERVER = 'server'    # 亚服/asia/国服/cn...（用 servers 表精确匹配）
    ACCOUNT = 'account'  # 游戏昵称（可含空格）
    SHIP = 'ship'        # 船名（剩余 token 合并，支持多词英文船名）
    INT = 'int'          # 天数/赛季/序号（≤3 位数字）
    DATE = 'date'        # 2024-05-30
    REST = 'rest'        # 剩余全部 token

@dataclass(frozen=True)
class Argument:
    kind: Kind
    target: str                # 写入 hikari.Input 的字段名
    required: bool = True
    hint: str = ''             # 生成报错/帮助

@dataclass(frozen=True)
class Command:
    name: str                            # 唯一 id
    aliases: tuple[str, ...]             # (主别名, 中文别名)
    handler: Callable | None = None
    args: tuple[Argument, ...] = ()
    subcommands: tuple['Command', ...] = ()
    default_sub: str | None = None       # 显式声明二级兜底，替代 func=None 哨兵
    help: str = ''
```

```python
# commands/account.py —— 声明即完成注册，不再需要 _HANDLERS
SHIP = Command(
    name='ship',
    aliases=('ship', '单船'),
    handler=get_ShipInfo,
    args=(Argument(Kind.SHIP, 'ShipInfo.nameCn'),),
    subcommands=(
        Command('ship_recent', ('recent', '近期'), get_ShipRecent,
                args=(Argument(Kind.SHIP, 'ShipInfo.nameCn'),
                      Argument(Kind.INT, 'Recent_Day', required=False),
                      Argument(Kind.DATE, 'Recent_Date', required=False))),
    ),
)
```

### 3.3 路由与绑定

```python
class Router:
    async def route(self, hikari, raw_tokens) -> Hikari_Model:
        tokens = normalize(raw_tokens)      # casefold + 全角→半角 + 去空
        cmd, rest = self._match(tokens, self.root)
        if cmd is None:
            return hikari.error(await suggest_candidates(tokens))  # 歧义/未命中提示
        hikari.Function = cmd.handler
        return bind_args(cmd, hikari, rest)  # 按 schema 顺序消费，缺参/多参模板化报错
```

匹配规则（消除子串依赖）：

1. 精确匹配别名（长别名优先）；
2. 精确失败 → 前缀匹配并给出候选提示；
3. 仅显式声明 `fuzzy=True` 的词允许子串，命中多个 → 返回歧义列表而非静默取第一个。

### 3.4 身份解析独立成 `identity.py`

`Search_Type` 改用 `IntEnum`（`ME / AT / SERVER_NAME`）；优先级固定：token 命中服务器表 → server+name，否则 me/@。括号语法删除，或收紧为 `(服务器 名字)` 显式双参数，避免与船名冲突。

### 3.5 帮助自动生成

`build_help(COMMAND_TREE)` 从命令声明生成中文帮助文本（别名、参数、示例），本地生成作为默认，远程 `wws_help.txt` 降级为可选覆盖。指令表与帮助永不分叉。

### 3.6 可测性

`Router.route` 是纯输入（`tokens → Function + Input`），可写大量无网络的单元测试；`tests/auto_test.py` 的每个样例都可转成 `assert` 用例。

---

## 4. 分阶段迁移路线（低风险渐进，可随时回退）

| 阶段 | 内容 | 风险 |
|---|---|---|
| 1 | 新增 `commands/` 模块 + `Router`，与旧 `select_command` 并行，先用 `help`/`roll` 等 2-3 个命令灰度切换 | 零 |
| 2 | 参数解析从 `_HANDLERS` 迁到各 Command 的 schema，**保留现有错误文案，行为等价** | 低 |
| 3 | 收敛别名（产品决策，需拍板）：删 `set`/`sd`/点号风格或标记 deprecated；`ship.rank` 与 `rank ship` 二选一 | 中（影响用户习惯） |
| 4 | 删除旧 `command_select` 扁平表、`_HANDLERS`、死代码 `find_and_replace_keywords`；补单元测试 | 低 |
| 5 | 帮助文本自动生成，替换远程 txt | 低 |

---

## 5. 立即可做的低风险修复（不依赖大重构）

1. `findFunction_and_replaceKeywords` 改为大小写不敏感（对齐 `match_keywords`）；
2. 删除死代码 `find_and_replace_keywords`（utils.py:55-74）；
3. 删除 `levels` 重复的 `'4'`（data_source.py:48）；
4. 合并重复的 `Func` Protocol，统一签名（command_select.py:28 vs model.py:7）；
5. `_parse_ship_query_params` 船名改为"剩余 token 合并"，修复英文多词船名；
6. 括号提取正则收紧为 `(服务器 名字)` 或移除。

---

## 6. 决策记录（已全部确认）

| # | 决策 | 选项 | 状态 |
|---|---|---|---|
| D1 | `ship.rank` / `cw.rank` / `clan.rank` / `cw.recent` 点号风格是否保留 | 保留 / 移除（统一二级路由 `rank ship` 等）| **已确认：保留** |
| D2 | `set`、`sd`、`recents`、`box` 等缩写别名 | 保留 / 移除 / 标记 deprecated | **已确认：全部保留** |
| D3 | `工会`（错别字）等兼容别名 | 保留并注释 / 移除 | **已确认：移除，输错由智能提示兜底** |
| D4 | `(括号)` 指定账号语法 | 移除 / 收紧为 `(服务器 名字)` | **已确认：保留** |
| D5 | 帮助文本 | 远程 txt 继续维护 / 自动生成（推荐）| **已实施：不自动生成；改为本地中英双语 H5 帮助页（help-zh.html / help-en.html），随 `command_language` 切换，版本号动态注入** |

## 7. 已实施：指令收敛 + 输错智能提示（feat/command-suggest 分支）

### 7.1 别名收敛

- `('clan', '军团', '公会', '工会')` → `('clan', '军团', '公会')`，移除错别字别名 `工会`。
- `set` / `sd` / `recents` 等缩写别名按决策 D2 全部保留。

### 7.2 输错智能提示

未匹配到任何指令时，对输入 token 做相似度匹配（前缀重合 + difflib 字符序列相似度，阈值 0.5），给出"你是不是想输入"提示：

```
未识别的指令，你是不是想输入（最多显示 3 条）：
  wws 单船 <船名>
  wws rank 单船 <服务器> <船名>
  wws recent 单船 <船名> [天数或日期]
更多帮助请发送：wws help
```

特性：

- **多条提示**：同一输入可命中多条指令线（如 `recebt` → recent / ship recent / recents 三条）；
- **最大条数可配置**：`set_hikari_config(command_suggest_max=N)`，默认 3，设为 0 关闭智能提示；
- **同效果去重可配置**：同一功能的多别名（如 `ship.rank` 与 `rank` 都是单船排行）只提示一条，`set_hikari_config(command_suggest_dedupe=False)` 关闭；
- **中文别名优先展示**：提示展示命中的那个别名（输入 `单传` 提示 `单船`），并附带参数用法；
- **合法身份查询不误报**：`me` / `@` / `服务器+昵称` 等默认账号查询不会触发提示；
- **二级指令同样覆盖**：`ship 大和 recebt` 会提示 `wws recent <船名> [天数或日期]`；
- **兼容性**：`select_command` / `findFunction_and_replaceKeywords` 保持原签名不变。

### 7.2 中英文设置

`set_hikari_config(command_language='en')` 切换指令提示语言（默认 `zh`）：

- **英文模式**下智能提示默认展示英文指令与英文参数用法：

  ```
  Unrecognized command. Did you mean (max 3 shown):
    wws ship <ship name>
    wws rank ship <server> <ship name>
    wws recent ship <ship name> [days or date]
  More help: send "wws help"
  ```

- 为原本只有中文别名的指令补充英文别名（英文模式下的指令入口）：

  | 功能 | 英文别名 | 功能 | 英文别名 |
  |---|---|---|---|
  | 更新样式 | `update_style` | 切换绑定 | `change_bind` |
  | 更新战舰 | `update_ship` | 查询绑定 | `bind_list` |
  | 删除绑定 | `delete_bind` | 特殊绑定 | `special_bind` |
  | 搜船名 | `search_ship` | | |

  > 注意：`search_ship` / `update_ship` 等含 `ship` 子串的英文别名，其指令条目必须排在 `ship` / `ship.rank` 之前（已按此调整列表顺序），否则会被子串匹配截胡。

- 匹配仍为中英双语（中文模式输入英文、英文模式输入中文均可命中），仅提示展示语言随配置切换。
- 帮助指令输出本地中英双语 H5 页面（`help-zh.html` / `help-en.html`），随 `command_language` 切换；顶部版本号由 `get_help` 动态注入（获取失败则隐藏），远程 `wws_help.txt` 已停用。

### 7.3 实现位置

| 文件 | 改动 |
|---|---|
| `hikari_core/commands/router.py`（原 `command_select.py`） | 新增 `route_command`（带建议路由）、`_suggest`、`_token_similarity`、`_flatten_entries`、`_is_identity_query`、`render_suggest_message`、`_display_alias`；`_match_level` 重构匹配层；移除 `工会` 别名；补充英文别名并调整列表顺序；`_USAGE` 双语文案 |
| `hikari_core/commands/parser.py`（原 `analyze.py`） | 改用 `route_command`，有建议时直接返回提示错误 |
| `hikari_core/core/config.py`（原 `config.py`） | 新增 `command_suggest_max` / `command_suggest_dedupe` / `command_language` 配置 |
| `tests/test_command_suggest.py` | 19 条无网络单元测试（路由回归 + 智能提示 + 去重/上限/中英文配置） |

## 8. 项目结构按功能域重构（refactor/feature-structure 分支）

将原先「顶层平铺 + `moudle`（拼写错误）/`game` 语义模糊」的结构，重构为「core 基础设施 → commands 指令系统 → features 业务功能」三层：

```
hikari_core/
├── __init__.py            # 顶层公共 API（init_hikari / Hikari_Model / 各功能函数，保持不变）
├── core/                  # 框架基础设施（不依赖业务）
│   ├── config.py  model.py  utils.py  cache_utils.py
│   ├── http_client.py（原 HttpClient_Pool.py）  http_error_handler.py  template_registry.py
│   ├── constants.py       # 原 data_source.py 数据常量（服务器/国家/舰种/等级/template_path/__version__）
│   └── render_helpers.py  # 原 data_source.py 渲染辅助（PR 颜色/排行解析/set_render_params）
├── commands/              # 指令系统
│   ├── router.py          # 原 command_select.py（指令表 + 路由 + 智能提示）
│   └── parser.py          # 原 analyze.py（指令解析）
├── features/              # 业务功能
│   ├── api.py             # 原 moudle/publicAPI.py（共享 API 辅助）
│   ├── account/           # 账号水表：info / recent / recents（原 wws_info / wws_recent / wws_recents）
│   ├── ship/              # 战舰：info / recent / rank（原 wws_ship_info / wws_ship_recent / wws_shiprank）
│   ├── clan/              # 军团/公会：info / rank / cw_rank / cw_recent
│   ├── bind.py            # 绑定（原 wws_bind）
│   ├── fun.py             # 娱乐：ban / box / roll / sx（原 game 下 4 个小文件合并）
│   └── system.py          # 系统维护：help / 版本 / 模板与战舰缓存更新（原 game/help.py）
├── Html_Render/  Template/   # 渲染引擎与模板资源（保持不动）
```

**要点**

- 分层依赖：`features → core`，`commands → features + core`，`core` 不依赖任何业务模块。
- 实时监控功能（monitor_list / test_monitor / add_monitor / delete_monitor / reset_monitor）已整体删除（`features/monitor.py` 移除，原 wws_real_game）。
- `data_source.py` 按职责拆分为 `core/constants.py`（数据常量）与 `core/render_helpers.py`（渲染辅助）；`template_path` 已修正为指向 `hikari_core/Template`。
- 娱乐类 4 个小文件（ban_search/box_check/roll/sx）合并进 `features/fun.py`。
- **破坏性变更（按决策：不保留兼容 shim）**：旧路径 `hikari_core.moudle.*`、`hikari_core.game.*`、`hikari_core.config`、`hikari_core.command_select`、`hikari_core.analyze`、`hikari_core.data_source`、`hikari_core.HttpClient_Pool` 等均已删除，外部引用需同步迁移到新路径；顶层 `from hikari_core import init_hikari / Hikari_Model / get_ShipInfo` 等公共 API 不受影响。建议随此重构将版本提升至 2.0。
- 测试：`tests/test_command_suggest.py` 19 条全部通过；`py_compile` 全量通过。
