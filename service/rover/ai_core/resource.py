"""AI 相关资源路径。"""

from rover.data_store import get_res_path

# 技能目录 - 每个技能一个子目录，内含 SKILL.md
SKILLS_PATH = get_res_path() / "ai_core" / "skills"
