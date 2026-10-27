from typing import Optional
from .models import Player, GameState, Identity, SkillType

# 【修改提醒 1】：严格按照规则文档 4.1 配置技能可用身份
SKILL_ALLOWED_IDENTITIES = {
    SkillType.BRIBE: [Identity.CORRUPT],
    SkillType.SEARCH: [Identity.HONEST, Identity.DISCIPLINE, Identity.PEOPLE], # 搜查：正义阵营均可
    SkillType.REPORT: [Identity.PEOPLE], # 实名举报：仅人民
    SkillType.DETAIN: [Identity.DISCIPLINE], # 留置：仅纪委
    SkillType.PEOPLES_WILL: [Identity.HONEST], # 人民的名义：仅清官
    SkillType.ASSASSINATE: [Identity.CORRUPT], # 灭口：仅贪官
}

# 【修改提醒 2】：动态计算技能使用上限，不再写死
def get_max_uses(skill: SkillType, player_count: int) -> int:
    if skill in [SkillType.BRIBE, SkillType.ASSASSINATE]:
        return player_count - 2  # 行贿/灭口：实际玩家数 - 2
    elif skill == SkillType.PEOPLES_WILL:
        return player_count - 1  # 人民的名义：实际玩家数 - 1
    else:
        return 99  # 搜查、举报、留置无全局次数上限

def check_skill_legal(state: GameState, player_id: int, skill: SkillType, target_id: Optional[int] = None) -> tuple[bool, str]:
    """统一校验技能合法性，返回(是否合法, 错误信息)"""
    player = state.players[player_id]

    # 1. 玩家存活校验
    if not player.is_alive:
        return False, "玩家已死亡，无法使用技能"

    # 2. 本回合技能权限校验
    if player.available_skill != skill:
        return False, "本回合未获得该技能使用权"

    # 3. 身份权限校验（【修改提醒 3】：处理被策反者的技能权限）
    allowed_ids = SKILL_ALLOWED_IDENTITIES[skill]
    # 如果被策反了，实际按贪官算；否则按原身份算
    actual_identity = Identity.CORRUPT if player.is_betrayed else player.identity
    if actual_identity not in allowed_ids:
        return False, f"身份不匹配，{skill.value}仅允许{[i.value for i in allowed_ids]}使用"

    # 4. 使用次数校验
    max_uses = get_max_uses(skill, len(state.players))
    if player.skill_used[skill] >= max_uses:
        return False, f"技能{skill.value}已达使用上限（上限{max_uses}次）"

    # 5. 目标合法性校验
    need_target_skills = [
        SkillType.BRIBE, SkillType.SEARCH, SkillType.REPORT,
        SkillType.DETAIN, SkillType.PEOPLES_WILL, SkillType.ASSASSINATE
    ]
    if skill in need_target_skills:
        if target_id is None:
            return False, "该技能需要指定目标"
        if target_id < 0 or target_id >= len(state.players):
            return False, "目标玩家不存在"
        target = state.players[target_id]
        if not target.is_alive:
            return False, "目标玩家已死亡"
        if target_id == player_id:
            return False, "不能对自己使用技能"

    return True, "合法"

# 【修改提醒 4】：新增战力计算函数，用于比拼
def get_player_power(player: Player) -> int:
    base_power = sum(player.power_cards)
    # 纪委被动：铁面无私 +4（仅在被作为行贿/灭口目标时生效，此处简化直接加）
    if player.identity == Identity.DISCIPLINE and not player.is_betrayed:
        base_power += 4
    return base_power

def execute_bribe(state: GameState, player_id: int, target_id: int) -> str:
    """行贿：比拼战力，胜利则策反"""
    legal, msg = check_skill_legal(state, player_id, SkillType.BRIBE, target_id)
    if not legal:
        return f"[非法] 行贿失败：{msg}"

    player = state.players[player_id]
    target = state.players[target_id]
    player.skill_used[SkillType.BRIBE] += 1

    p_power = get_player_power(player)
    t_power = get_player_power(target)

    if p_power > t_power:
        # 【修改提醒 5】：不再直接修改 identity，而是打上 is_betrayed 标记，符合规则
        if target.identity in [Identity.HONEST, Identity.DISCIPLINE]:
            target.is_betrayed = True
            return f"[行贿] 成功！玩家{player_id}策反了玩家{target_id}（战力{p_power} vs {t_power}）"
        return f"[行贿] 玩家{player_id}战力胜出，但目标并非清官/纪委（战力{p_power} vs {t_power}）"
    else:
        return f"[行贿] 失败！玩家{player_id}战力不足（战力{p_power} vs {t_power}）"

def execute_search(state: GameState, player_id: int, target_id: int) -> str:
    """搜查：获取目标真实身份（私密反馈）"""
    legal, msg = check_skill_legal(state, player_id, SkillType.SEARCH, target_id)
    if not legal:
        return f"[非法] 搜查失败：{msg}"

    player = state.players[player_id]
    target = state.players[target_id]
    player.skill_used[SkillType.SEARCH] += 1

    state.public_log.append(f"[搜查] 玩家{player_id}对玩家{target_id}进行了身份调查")
    return f"[搜查结果] 玩家{target_id}的身份是：{target.identity.value}"

def execute_report(state: GameState, player_id: int, target_id: int) -> str:
    """实名举报：比拼战力，赢且是贪官则公开"""
    legal, msg = check_skill_legal(state, player_id, SkillType.REPORT, target_id)
    if not legal:
        return f"[非法] 举报失败：{msg}"

    player = state.players[player_id]
    target = state.players[target_id]
    player.skill_used[SkillType.REPORT] += 1

    p_power = get_player_power(player)
    t_power = get_player_power(target)

    if p_power > t_power and (target.identity == Identity.CORRUPT or target.is_betrayed):
        return f"[实名举报] 成功！玩家{player_id}公开了玩家{target_id}的贪官身份！"
    else:
        return f"[实名举报] 失败。玩家{player_id}战力不足或目标不是贪官"

def execute_detain(state: GameState, player_id: int, target_id: int) -> str:
    """留置：限制目标下轮行动或反噬（【修改提醒 6】：修正为规则文档效果，不再扣血）"""
    legal, msg = check_skill_legal(state, player_id, SkillType.DETAIN, target_id)
    if not legal:
        return f"[非法] 留置失败：{msg}"

    player = state.players[player_id]
    target = state.players[target_id]
    player.skill_used[SkillType.DETAIN] += 1

    if target.identity == Identity.CORRUPT or target.is_betrayed:
        return f"[留置] 玩家{player_id}对玩家{target_id}执行留置，目标本轮无法使用技能"
    else:
        return f"[留置] 目标非贪官，纪委玩家{player_id}误审，下轮战力-3"

def execute_peoples_will(state: GameState, player_id: int, target_id: int) -> str:
    """人民的名义：清官专属，比拼战力击杀"""
    legal, msg = check_skill_legal(state, player_id, SkillType.PEOPLES_WILL, target_id)
    if not legal:
        return f"[非法] 人民的名义失败：{msg}"

    player = state.players[player_id]
    target = state.players[target_id]
    player.skill_used[SkillType.PEOPLES_WILL] += 1

    p_power = get_player_power(player)
    t_power = get_player_power(target)

    if p_power > t_power and (target.identity == Identity.CORRUPT or target.is_betrayed):
        target.health = 0
        target.is_alive = False
        return f"[人民的名义] 玩家{player_id}成功击杀贪官玩家{target_id}！"
    elif p_power > t_power and not (target.identity == Identity.CORRUPT or target.is_betrayed):
        return f"[人民的名义] 误抓！玩家{player_id}目标非贪官，弃置1张技能牌"
    else:
        return f"[人民的名义] 失败，玩家{player_id}战力不足，下轮战力-1"

def execute_assassinate(state: GameState, player_id: int, target_id: int) -> str:
    """灭口：贪官专属，比拼战力击杀（【修改提醒 7】：修正为战力比拼，不再看生命值）"""
    legal, msg = check_skill_legal(state, player_id, SkillType.ASSASSINATE, target_id)
    if not legal:
        return f"[非法] 灭口失败：{msg}"

    player = state.players[player_id]
    target = state.players[target_id]
    player.skill_used[SkillType.ASSASSINATE] += 1

    p_power = get_player_power(player)
    t_power = get_player_power(target)

    if p_power > t_power:
        target.health = 0
        target.is_alive = False
        return f"[灭口] 玩家{player_id}成功将玩家{target_id}灭口，目标死亡！"
    else:
        return f"[灭口] 失败，贪官玩家{player_id}战力不足，下轮战力-3"

# 技能执行器映射
SKILL_EXECUTORS = {
    SkillType.BRIBE: execute_bribe,
    SkillType.SEARCH: execute_search,
    SkillType.REPORT: execute_report,
    SkillType.DETAIN: execute_detain,
    SkillType.PEOPLES_WILL: execute_peoples_will,
    SkillType.ASSASSINATE: execute_assassinate,
}