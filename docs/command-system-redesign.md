# Hikari-core 指令系统现状与重构方案

> 状态：评审稿；**声明式命令树重构暂缓**。本文档只记录当前实现与重构方案（历史问题与已完成修复不再记录）
> 范围：指令路由 + 参数解析（`hikari_core/commands/`）

---

## 1. 现状

### 1.1 当前实现

```
init_hikari_no_output (hikari_core/__init__.py)
  └─ analyze_command (commands/parser.py)
       ├─ Command_List = Command_Text.split()      (html.unescape + strip)
       │    └─ _merge_paren_groups                  (半角 () 内容合并为单 token，如 (AI deal))
       ├─ route_command (commands/router.py)      (扁平表路由 + 二级路由 + 智能提示)
       │    └─ _match_level                       (大小写不敏感子串匹配)
       ├─ extract_with_me                         (me 身份；@ 由接入端处理)
       └─ extract_with_function                   (_HANDLERS 分发到 _handle_*)
  └─ hikari.Function(hikari)                      (执行 API 处理器)
```

- **指令表**：`first_command_list` 扁平表 + 5 个二级列表（ship / recent / rank / clan）
- **匹配**：大小写不敏感**整词匹配**（token 与别名整词相等才命中，2025-09 机制整改废弃子串 `find`）；
  列表顺序不再决定"长词优先"，仅在个别组合（如 `recent 随机` 同时含两命令词）作为确定性 tie-break；
  同层兄弟指令共享别名会被不变量测试（matrix `test_no_shared_alias_within_level`）拦截
- **输错智能提示**：`route_command` 未命中时按相似度（前缀重合 + difflib）给出候选；
  **建议守卫（`_suggest_guarded`，一级/二级共用）**：剩余 token 含服务器关键词 → 判定为
  "服务器+昵称"数据查询，不做任何命令猜测；剔除 `me` / 天数(≤3位数字) / 日期 等参数型 token 后，
  仅"疑似命令词"参与相似度——昵称/船名等数据 token 永远不会触发"未识别"误报；
  `command_suggest_max` / `command_suggest_dedupe` 可配置
- **身份指定**：`me` 可缺省——有指令匹配且未指定服务器关键词时默认查自己（`Search_Type=1`），显式 `me` 或 `服务器+昵称`（`Search_Type=3`）均可；`wws me` 单独使用正常（查询自己水表）；未匹配到任何指令且非身份查询的输入给出未识别提示；`@` 提及由接入端转换为 `me` 后传入，SDK 不再解析；**括号分组昵称**：游戏昵称/船名不含 `()`，故被半角 `()` 包裹的内容合并为单个 token（`cn (AI deal) recent` 的昵称为 `AI deal`），仅 token 以 `(` 开头才合并，`大和(测试)` 这类单 token 内部括号不受影响
- **身份解析单一入口**：`extract_with_me` 一次性判定 显式 me / 服务器+昵称 / me 缺省——
  存在服务器关键词且功能允许服务器槽位时**前置提取到 `Input.Server` 并从 token 移除**，
  主流身份族（水表/近期/单船/排行/军团/CW/ships/sx/box/ban/update）的 `_handle_*`
  不再各自重复 match 服务器（消除口径分叉）；
  例外集 `_NO_SERVER_SLOT_FUNCS`：`roll`/`search_ship`（国别词与服务器词重叠——
  `europe` 既是欧服服务器词又是欧洲国别词，只能在自己的参数语义内消费）与绑定族
  （历史遗留语义，见设计债 5）；
  `_is_identity_query` 供 parser 门禁与路由守卫共用同一口径
- **中英文**：`command_language` 切换提示与帮助页语言；帮助为本地 H5（help-zh.html / help-en.html），不显示版本信息
- **既有行为（已确认）**：点号风格（`ship.rank` / `cw.rank` / `clan.rank` / `cw.recent`）保留；缩写别名（`set` / `sd` / `recents` / `box`）保留；`update` 不抢占 `update_ship` / `update_style`（整词匹配天然保证，无需人工排序）
- **测试**：`tests/test_command_matrix.py` 行为矩阵（路由全别名 / 身份×参数解析 / 建议守卫 / 别名不变量，6 组）+ `tests/test_command_suggest.py`（28 条无网络单元测试）；整改期间语义变更必须同步矩阵

### 1.2 设计债（结构性，非功能性 bug）

> 2025-09 机制整改（方案 A）已完成 1/2/3 类债的机制性修复（整词匹配、守卫式建议、建议/身份口径统一），
> 并修复 `get_ClanRank` 从 `_HANDLERS` 漏注册（导入被删 → 军团排行解析空字段、静默失效）与
> `verify_and_add_admin` 返回值 int/bool 不一致；新增行为矩阵测试。残余设计债：

1. ~~**子串匹配 + 列表顺序强耦合**~~ → 已改整词匹配；顺序仅作组合歧义的确定性 tie-break，
   新增同层别名由不变量测试拦截
2. ~~**两级路由靠哨兵值表达**~~ → 保留 `func=None`/`default_func` 哨兵（结构债仍在，见下）
3. **参数解析手写散落（部分残留）**：`parser.py` 15 个 `_handle_*` 仍按位置索引消费 token；
   服务器字段已前置统一提取（身份族），但 `roll`/`search_ship`/绑定族因词汇重叠或历史语义
   保留自身解析（`_NO_SERVER_SLOT_FUNCS` 显式声明例外）；彻底收敛需声明式参数 schema
4. **功能声明分散**：新增一个功能需同时改动指令表、`_HANDLERS`、参数解析、`_USAGE` 用法提示、帮助页，共 5 处
   （`get_ClanRank` 漏注册即此类分散的代价）
5. **绑定/特殊绑定历史包袱**：`special_bind` 等旧指令语义与 README 不完全一致，待产品确认后收敛

---

## 2. 方案：声明式命令树 + 类型化 token 解析

核心思想：把「扁平别名表 + 手写解析」升级为「命令树 + 参数 schema + 统一解析器」。每个功能只在一处声明，路由、参数绑定、校验、报错、用法提示全部由框架推导。

### 2.1 新模块结构

```
hikari_core/commands/
  base.py      # Command / Argument / Router / TokenStream（框架）
  account.py   # info / recent / recents / ship / ship_recent 命令声明
  clan.py      # clan / cw_rank / cw_recent / clan_rank
  bind.py      # bind / special_bind / change / delete / 查询绑定
  other.py     # help / roll / sx / box / ban / 搜船名 / 更新
  __init__.py  # COMMAND_TREE 注册中心
parser.py      # 重写为: normalize → route → bind → identity
```

### 2.2 核心声明

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
    hint: str = ''             # 生成报错/用法提示

@dataclass(frozen=True)
class Command:
    name: str                            # 唯一 id
    aliases: tuple[str, ...]             # (主别名, 中文别名)
    handler: Callable | None = None
    args: tuple[Argument, ...] = ()
    subcommands: tuple['Command', ...] = ()
    default_sub: str | None = None       # 显式声明二级兜底，替代 func=None 哨兵
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

### 2.3 路由与绑定

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

### 2.4 身份解析

`Search_Type` 改用 `IntEnum`（`ME / SERVER_NAME`；`@` 由接入端处理，SDK 不再解析）；优先级：token 命中服务器表 → server+name，否则 me。

### 2.5 可测性

`Router.route` 是纯输入（tokens → Function + Input），可写大量无网络单元测试。

> 注：帮助文本维持本地中英双语 H5（help-zh.html / help-en.html），不自动生成。

---

## 3. 迁移路线（低风险渐进，可随时回退）

| 阶段 | 内容 | 风险 |
|---|---|---|
| 1 | 新增 `commands/` 声明模块 + `Router`，与旧 `select_command` 并行，先用 `help`/`roll` 等 2-3 个命令灰度切换 | 零 |
| 2 | 参数解析从 `_HANDLERS` 迁到各 Command 的 schema，**保留现有错误文案，行为等价** | 低 |
| 3 | 收敛别名（产品决策，需拍板）：删 `set`/`sd`/点号风格或标记 deprecated；`ship.rank` 与 `rank ship` 二选一 | 中（影响用户习惯） |
| 4 | 删除旧 `first_command_list` 扁平表、`_HANDLERS`；补单元测试 | 低 |
