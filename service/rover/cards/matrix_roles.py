"""矩阵卡的角色 id。

上游给模板的角色项只有图标和命座, 没有 id, 点击注解就无从下手。
构图时每个真实角色都会取一次流派徽标, 借这一步把 id 顺手记下来。
"""

from rover.logger import logger


def _patch(m) -> None:
    original = m.get_skill_branch_emblem_b64

    def get_skill_branch_emblem_b64(role_id, branch_index):
        from rover.html_actions import record_role_id

        try:
            record_role_id(role_id)
        except Exception as e:
            logger.debug(f"[鸣潮·交互] 矩阵角色 id 记录失败: {e}")
        return original(role_id, branch_index)

    m.get_skill_branch_emblem_b64 = get_skill_branch_emblem_b64


PATCHES = {"XutheringWavesUID": {"wutheringwaves_abyss.draw_matrix_card": _patch}}
