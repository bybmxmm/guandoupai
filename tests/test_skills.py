import pytest
from engine.models import Identity, Position, SkillType, GameState, Player
from engine.skills import check_skill_legal, execute_detain

@pytest.fixture
def test_state():
    """构造测试用游戏状态，身份固定"""
    players = [
        Player(0, Identity.CORRUPT, Position.MAGISTRATE),
        Player(1, Identity.HONEST, Position.GOVERNOR),
        Player(2, Identity.DISCIPLINE, Position.INSPECTOR),
        Player(3, Identity.PEOPLE, Position.SQUIRE),
        Player(4, Identity.PEOPLE, Position.MERCHANT),
    ]
    for p in players:
        p.power_cards = [10, 5, 3]
    return GameState(players=players)

def test_bribe_identity_check(test_state):
    """清官无法使用行贿技能"""
    test_state.players[1].available_skill = SkillType.BRIBE
    legal, msg = check_skill_legal(test_state, 1, SkillType.BRIBE, 2)
    assert legal is False
    assert "身份不匹配" in msg

def test_bribe_target_dead(test_state):
    """无法对已死亡玩家使用技能"""
    test_state.players[0].available_skill = SkillType.BRIBE
    test_state.players[1].is_alive = False
    legal, msg = check_skill_legal(test_state, 0, SkillType.BRIBE, 1)
    assert legal is False
    assert "目标玩家已死亡" in msg

def test_detain_hit_corrupt(test_state):
    """留置命中贪官造成2点伤害"""
    test_state.players[2].available_skill = SkillType.DETAIN
    result = execute_detain(test_state, 2, 0)
    assert "命中贪官" in result
    assert test_state.players[0].health == 0
    assert test_state.players[0].is_alive is False

def test_detain_miss_backfire(test_state):
    """留置未命中反噬自身1点伤害"""
    test_state.players[2].available_skill = SkillType.DETAIN
    result = execute_detain(test_state, 2, 3)
    assert "自身受到1点反噬伤害" in result
    assert test_state.players[2].health == 1
    assert test_state.players[2].is_alive is True
