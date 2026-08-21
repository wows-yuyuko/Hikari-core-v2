"""模板注册中心 — 所有模板配置的集中定义。

将散落在各文件中的 ``set_template_info(template_name, width, height)``
调用集中到此处，通过 ``Templates.XXX.apply_to(hikari)`` 使用。

用法::

    from hikari_core.core.template_registry import Templates

    Templates.WWS_SHIP.apply_to(hikari)
    # 等价于旧写法: hikari.set_template_info('wws-ship.html', 800, 100)
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
    """模板注册中心 — 所有模板配置的集中定义"""

    # 选择列表
    SELECT_SHIP: TemplateConfig = TemplateConfig("select-ship-v3.html", 680, 100)
    SELECT_CLAN: TemplateConfig = TemplateConfig("select-clan.html", 360, 100)

    # 水表
    WWS_SHIP: TemplateConfig = TemplateConfig("wws-ship.html", 800, 100)
    WWS_SHIP_RECENT: TemplateConfig = TemplateConfig("wws-ship-recent.html", 800, 100)
    WWS_INFO: TemplateConfig = TemplateConfig("wws-info.html", 920, 1000)
    WWS_INFO_RECENT: TemplateConfig = TemplateConfig("wws-info-recent.html", 1200, 100)
    WWS_INFO_RECENTS: TemplateConfig = TemplateConfig("wws-info-recents.html", 1200, 100)

    # 公会
    WWS_CLAN: TemplateConfig = TemplateConfig("wws-clan.html", 1200, 100)
    WWS_CLAN_CW: TemplateConfig = TemplateConfig("wws-clan-cw.html", 1200, 100)
    CW_RANK: TemplateConfig = TemplateConfig("cw-rank.html", 1300, 100)

    # 排行榜
    SHIP_RANK: TemplateConfig = TemplateConfig("ship-rank-v2.html", 1300, 100)

    # 绑定
    BIND_LIST: TemplateConfig = TemplateConfig("bind-list.html", 900, 240)

    # 其他
    WWS_BAN: TemplateConfig = TemplateConfig("wws-ban.html", 900, 100)
    WWS_UNBAN: TemplateConfig = TemplateConfig("wws-unban.html", 900, 100)
    WWS_SX: TemplateConfig = TemplateConfig("wws-sx.html", 920, 1000)
    WWS_BOX_CHRISTMAS: TemplateConfig = TemplateConfig("wws-box-christmas.html", 920, 1000)
    TEXT: TemplateConfig = TemplateConfig("text.html", 800, 10)
