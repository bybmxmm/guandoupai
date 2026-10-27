import json
from typing import Dict, Any, Tuple
from .models import GameState, SkillType
from .skills import check_skill_legal


def validate_llm_output(raw_output: str) -> Tuple[bool, Dict[str, Any], str]:
    """第一层：校验JSON格式与字段完整性"""
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        return False, {}, "输出不是合法JSON格式"

    if "speech" not in data or "action" not in data:
        return False, {}, "缺少必填字段：speech 或 action"

    action = data["action"]
    if "skill" not in action or "target" not in action:
        return False, {}, "action字段缺少 skill 或 target"

    try:
        SkillType(action["skill"])
    except ValueError:
        return False, {}, f"不存在的技能类型：{action['skill']}"

    if not isinstance(action["target"], int):
        return False, {}, "target必须是整数类型的玩家编号"

    return True, data, "格式合法"


def validate_action_legal(state: GameState, player_id: int, skill_name: str, target_id: int) -> Tuple[bool, str]:
    """第二层：校验动作是否符合游戏规则"""
    try:
        skill = SkillType(skill_name)
    except ValueError:
        return False, f"技能{skill_name}不存在"

    legal, msg = check_skill_legal(state, player_id, skill, target_id)
    return legal, msg
