"""后台管理注册桩。吃下插件的声明, 不提供 Web 界面。"""

from dataclasses import dataclass
from typing import Any, Type


@dataclass
class PageSchema:
    label: str
    icon: str = ""


class AdminModel:
    model: Any = None
    pk_name: str = "id"
    page_schema: Any = None


class Site:
    def register_admin(self, *admin_cls: Type[AdminModel], _ADD: bool = False) -> Type[AdminModel]:
        return admin_cls[0]


site = Site()

__all__ = ["PageSchema", "AdminModel", "Site", "site"]
