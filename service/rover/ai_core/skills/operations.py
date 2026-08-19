"""技能操作。技能加载尚未接入，重载为空操作。"""

from rover.logger import logger


def _reload_skills() -> None:
    """重新扫描 SKILLS_PATH 下的技能。"""
    logger.debug("[AI 技能] 未接入技能加载，跳过重载")
