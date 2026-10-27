import random
import json
from ai.bot import LLMAgent
from engine.models import Player, GameState

# ========== 身份‑合法技能映射，严格对应官斗牌规则文档 ==========
ALLOW_SKILL_MAP = {
    "corrupt": {"bribe", "assassinate"},
    "honest": {"search", "peoples_will"},
    "discipline": {"search", "detain"},
    "people": {"search", "report"}
}

class EnhancedAgent:
    def __init__(self, player_id: int):
        self.base_agent = LLMAgent(player_id)
        self.player_id = player_id

        # 普通兜底观望话术（拿到非法技能时使用）
        self.fallback_observe_pool = [
            "局势复杂，我继续观察场上各位玩家的表现。",
            "目前信息尚不充分，我选择继续观望，暂不释放技能。",
            "现在证据还不足，我保持观察，等待更好时机。",
            "局势扑朔迷离，我选择先不采取行动，静观其变。",
            "我需要收集更多情报，本回合不使用技能。"
        ]
        # 原有兜底举报话术（正常合法技能解析失败场景）
        self.fallback_speech_pool = [
            "我将行使我的权利，对场上可疑人员进行实名举报。",
            "经观察，我认为某位玩家行为可疑，现对其发起实名举报。",
            "根据当前局势，我选择对我怀疑的目标进行实名检举。",
            "我决定公开亮明态度，举报一名行为存疑的玩家。",
            "经过审慎考虑，我将对一名可疑人员行使举报权利。"
        ]

    def act(self, player: Player, state: GameState) -> str:
        raw_json_str = self.base_agent.act(player, state)
        print(f"【DEBUG-{self.player_id}】本回合分配给玩家的技能 = {player.available_skill}")
        print(f"【DEBUG-{self.player_id}】LLM原始输出：{raw_json_str}")

        identity_val = player.identity.value
        skill_is_legal = True
        assign_skill_name = None
        if player.available_skill is not None:
            assign_skill_name = player.available_skill.value
            if assign_skill_name not in ALLOW_SKILL_MAP[identity_val]:
                skill_is_legal = False

        # ===== 分配的技能对该身份非法：放弃本回合技能，action置None =====
        if not skill_is_legal:
            speech = random.choice(self.fallback_observe_pool)
            out_data = {
                "speech": speech,
                "action": None
            }
            out_json = json.dumps(out_data, ensure_ascii=False)
            print(f"【DEBUG-{self.player_id}】⚠️分配技能[{assign_skill_name}]与身份[{identity_val}]不匹配，本回合放弃技能，输出={out_json}")
            return out_json

        # ===== 技能合法，执行原有逻辑：强制覆盖skill =====
        try:
            data = json.loads(raw_json_str)
            bot_fixed_speech = "我将行使我的权利，对场上可疑人员进行实名举报。"
            if data.get("speech") == bot_fixed_speech:
                data["speech"] = random.choice(self.fallback_speech_pool)
            # 强制覆盖为引擎分配的合法skill
            if player.available_skill is not None:
                fixed_skill = player.available_skill.value
                data["action"]["skill"] = fixed_skill
                print(f"【DEBUG-{self.player_id}】✅强制覆盖skill为：{fixed_skill}")
            final_json = json.dumps(data, ensure_ascii=False)
            print(f"【DEBUG-{self.player_id}】修正后输出：{final_json}")
            return final_json

        except Exception as e:
            print(f"【DEBUG-{self.player_id}】解析异常，走兜底，err={e}")
            # 解析异常，但技能本身是合法的，生成合法动作
            alive_target_list = [
                p.player_id
                for p in state.players
                if p.is_alive and p.player_id != self.player_id
            ]
            safe_target = alive_target_list[0] if alive_target_list else 0
            safe_skill = player.available_skill.value if player.available_skill is not None else "report"
            fallback_data = {
                "speech": random.choice(self.fallback_speech_pool),
                "action": {
                    "skill": safe_skill,
                    "target": safe_target
                }
            }
            final_json = json.dumps(fallback_data, ensure_ascii=False)
            print(f"【DEBUG-{self.player_id}】兜底输出，skill={safe_skill}, target={safe_target}：{final_json}")
            return final_json

    def add_private_memory(self, info: str):
        self.base_agent.add_private_memory(info)



