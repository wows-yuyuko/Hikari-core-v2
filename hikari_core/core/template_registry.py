"""模板注册中心 — 所有模板配置的集中定义。

将散落在各文件中的 ``set_template_info(template_name, width, height)``
调用集中到此处，通过 ``Templates.XXX.apply_to(hikari)`` 使用。

用法::

    from hikari_core.core.template_registry import Templates

    Templates.WWS_SHIP.apply_to(hikari)
    # 等价于旧写法: hikari.set_template_info('wws-ship-v5.html', 800, 100)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Hikari_Model


@dataclass(frozen=True)
class TemplateConfig:
    """单个模板配置"""

    name: str
    width: int
    height: int

    def apply_to(self, hikari: Hikari_Model) -> Hikari_Model:
        """将模板配置应用到 Hikari_Model 实例，返回实例本身以支持链式调用"""
        hikari.Output.Template = self.name
        hikari.Output.Width = self.width
        hikari.Output.Height = self.height
        return hikari


class Templates:
    """模板注册中心 — 所有模板配置的集中定义

    ▍width 口径：**模板页面的实际宽度**，不是"随便给个初始视口"。
      改这里的 width 不会改变出图宽度（full_page 截图按内容 scrollWidth 截，
      实测 800/920/1200 视口下 info 与单船出图都仍是 1500 宽），所以两者保持一致
      纯粹是为了口径统一 —— 避免以后某天模板里出现 vw/vh/@media 时踩坑。

    页面宽度来源：
      - 共用 main-v6.css 的 .page-box / .main-content = **1500px**（info/单船/近期系/ships/clan/sx/box）
      - 模板自带覆盖：ship-rank 1300 / cw-rank 2160 / clan-cw 1200 / ban·unban·bind-list 900 /
        select-clan 360
      - help 系为流式页（卡片 860 居中，不引 main-v6.css），宽度由视口决定 → 900
      - 未对齐（保留未动，改了会缩窄出图）：select-ship 页面 660，注册表给 680 → 右侧多 20px 留白
    """

    # 选择列表（v6 统一风格）
    SELECT_SHIP: TemplateConfig = TemplateConfig("select-ship-v6.html", 680, 100)
    SELECT_CLAN: TemplateConfig = TemplateConfig("select-clan-v6.html", 360, 100)

    # 水表（v6 统一风格）
    WWS_SHIP: TemplateConfig = TemplateConfig("wws-ship-v6.html", 1500, 100)
    WWS_SHIP_RECENT: TemplateConfig = TemplateConfig("wws-ship-recent-v6.html", 1500, 100)
    WWS_INFO: TemplateConfig = TemplateConfig("wws-info-v6.html", 1500, 1000)
    # 旧接口(/user/info v1 数据)兼容层,最新代码已不调用,保留按需回退
    # WWS_INFO_V5: TemplateConfig = TemplateConfig("wws-info-v5.html", 920, 1000)
    WWS_INFO_RECENT: TemplateConfig = TemplateConfig("wws-info-recent-v6.html", 1500, 100)
    WWS_INFO_RECENT_RANDOM: TemplateConfig = TemplateConfig("wws-info-recent-random-v6.html", 1500, 100)
    WWS_INFO_RECENT_RANK: TemplateConfig = TemplateConfig("wws-info-recent-rank-v6.html", 1500, 100)
    WWS_INFO_RECENTS: TemplateConfig = TemplateConfig("wws-info-recents-v6.html", 1500, 100)
    WWS_SHIPS: TemplateConfig = TemplateConfig("wws-ships-v6.html", 1500, 100)

    # 公会（v6 统一风格）
    WWS_CLAN: TemplateConfig = TemplateConfig("wws-clan-v6.html", 1500, 100)
    WWS_CLAN_CW: TemplateConfig = TemplateConfig("wws-clan-cw-v6.html", 1200, 100)
    CW_RANK: TemplateConfig = TemplateConfig("cw-rank-v6.html", 2160, 100)

    # 排行榜（v6 统一风格）
    SHIP_RANK: TemplateConfig = TemplateConfig("ship-rank-v6.html", 1300, 100)

    # 绑定（v6 统一风格）
    BIND_LIST: TemplateConfig = TemplateConfig("bind-list-v6.html", 900, 240)

    # 其他（v6 统一风格）
    WWS_BAN: TemplateConfig = TemplateConfig("wws-ban-v6.html", 900, 100)
    WWS_UNBAN: TemplateConfig = TemplateConfig("wws-unban-v6.html", 900, 100)
    WWS_SX: TemplateConfig = TemplateConfig("wws-sx-v6.html", 1500, 1000)
    WWS_BOX_CHRISTMAS: TemplateConfig = TemplateConfig("wws-box-christmas-v6.html", 1500, 1000)

    # 帮助（中/英 H5 帮助页）
    HELP_ZH: TemplateConfig = TemplateConfig("help-zh.html", 900, 10)
    HELP_EN: TemplateConfig = TemplateConfig("help-en.html", 900, 10)
