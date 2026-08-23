# Hikari-core 指令系统现状与重构方案

> 状态：评审稿；**声明式命令树重构暂缓**。本文档只记录当前实现与重构方案（历史问题与已完成修复不再记录）
> 范围：指令路由 + 参数解析（`hikari_core/commands/`）

---

## 1. 现状

### 1.1 当前实现

```
init_hikari_no_output (hikari_core/__init__.py)
  └─ analyze_command (commands/parser.py)
       ├─ Command_List = Command_Text.split()     (html.unescape + strip)
       ├─ route_command (commands/router.py)      (扁平表路由 + 二级路由 + 智能提示)
       │    └─ _match_level                       (大小写不敏感子串匹配)
       ├─ extract_with_me                         (me 身份；@ 由接入端处理)
       └─ extract_with_function                   (_HANDLERS 分发到 _handle_*)
  └─ hikari.Function(hikari)                      (执行 API 处理器)
```

- **指令表**：`first_command_list` 扁平表 + 5 个二级列表（ship / recent / rank / clan）
- **匹配**：大小写不敏感子串匹配，长词 / 含 `ship` 子串的英文别名需人工保证靠前
- **身份指定**：`me` 可缺省——有指令匹配且未指定服务器关键词时默认查自己（`Search_Type=1`），显式 `me` 或 `服务器+昵称`（`Search_Type=3`）均可；`wws me` 单独使用正常（查询自己水表）；未匹配到任何指令且非身份查询的输入给出未识别提示；`@` 提及由接入端转换为 `me` 后传入，SDK 不再解析；括号指定账号语法已移除
- **输错智能提示**：`route_command` 未命中时按相似度（前缀重合 + difflib）给出候选，`command_suggest_max` / `command_suggest_dedupe` 可配置
- **中英文**：`command_language` 切换提示与帮助页语言；帮助为本地 H5（help-zh.html / help-en.html），不显示版本信息
- **既有行为（已确认）**：点号风格（`ship.rank` / `cw.rank` / `clan.rank` / `cw.recent`）保留；缩写别名（`set` / `sd` / `recents` / `box`）保留
- **测试**：`tests/test_command_suggest.py` 22 条无网络单元测试（路由 / 智能提示 / 中英文 / 多词英文船名 / 大小写不敏感）

### 1.2 设计债（结构性，非功能性 bug）

1. **子串匹配 + 列表顺序强耦合**：命中依赖 `first_command_list` 顺序，新增指令需人工保证长词 / 英文别名靠前，插错位置即静默错乱
2. **两级路由靠哨兵值表达**：`command` 用 `func=None` 表示进入二级、`default_func` 表示兜底，均为隐式约定
3. **参数解析手写散落**：`parser.py` 15 个 `_handle_*` 按位置索引消费 token（如昵称 / 船名顺序固定），报错文案手写
4. **功能声明分散**：新增一个功能需同时改动指令表、`_HANDLERS`、参数解析、`_USAGE` 用法提示、帮助页，共 5 处

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
