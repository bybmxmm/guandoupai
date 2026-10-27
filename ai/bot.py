import os
os.environ["PYTHONUTF8"] = "1"

from dotenv import load_dotenv
load_dotenv()  

from openai import OpenAI
from engine.models import Player, GameState
import json
import random  
from ai.nlp_rule_rag import RuleRAG
from ai.nlp_extract_validator import RuleExtractorValidator
from engine.scenario import get_position_persona 

api_key = os.getenv("DASHSCOPE_API_KEY")

client = OpenAI(
    api_key=api_key,  
    base_url="https://ws-g0v22m2xzd0ba1vu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rule_path = os.path.join(base_dir, "rule_doc.txt")
rag = RuleRAG(rule_file_path=rule_path)
ext_validator = RuleExtractorValidator()  

class LLMAgent:
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.private_memory = []  
        
        self.fallback_speeches = [
            "我将行使我的权利，对场上可疑人员进行实名举报。",
            "经过我的一番推理，我发现某位玩家极其可疑，我决定立刻举报他。",
            "局势越来越焦灼了，不能再坐以待毙，我必须采取行动。",
            "别以为我什么都没看出来，我这就向大家揭露一个事实。",
            "为了正义，我哪怕拼尽全力，也要揪出隐藏在暗处的坏人。"
        ]

    def _build_prompt(self, player: Player, state: GameState, error_hint: str = "") -> str:
        current_skill = player.available_skill.value if player.available_skill else "无"
        identity = player.identity.value
        
        query = f"身份{identity}，技能{current_skill}，技能权限、使用限制、合法目标、阵营胜利条件"
        retrieved_rule_text = rag.retrieve_rule(query, top_k=3)
        public_logs = state.public_log[-15:] if len(state.public_log) > 15 else state.public_log
        
        # 【修复核心】：把不可违反的铁律放在最前面，无论什么模式都生效
        mode_prompt = """
> 🚨【系统最高铁律】：无论在什么情况下，绝对禁止在公开发言中直接说出你的隐藏身份名称（例如直接说“我是清官”、“我是贪官”、“我是纪委”、“我是人民”）。一旦你直接暴露，系统将判定你严重违规！你必须像一个真正的政客一样，通过伪装、指控、讲逻辑来玩游戏，而不是直接把底牌亮出来！
"""

        # 如果是剧本模式，追加人设约束
        if state.is_scenario_mode:
            persona = get_position_persona(player.public_position)
            clue_text = state.current_clue
            mode_prompt += f"""
【剧本模式：角色扮演强制指令】
你的公开职位是：{player.public_position}。
你的人设风格：{persona}
本回合公共线索：{clue_text}

> 🎭 你现在必须完全代入 {player.public_position} 的角色进行发言。你可以利用公开线索去诬陷别人、为自己开脱。请尽情展现你的演技，迷惑其他玩家！
"""

        prompt = f"""
{mode_prompt}
【从原始规则文档检索得到的相关规则片段】
{retrieved_rule_text}

=== 你的绝对真实信息（只有你自己知道，绝不能直接说出来） ===
玩家编号：{self.player_id}
隐藏身份：{identity}
生命值：{player.health}
战力牌：{player.power_cards}
本回合分配技能：{current_skill}
> ⚠️最高优先级约束：你只能使用上面分配给你的这一个技能，不允许自选其他技能！

=== 公共对局日志 ===
{chr(10).join(public_logs)}

=== 你的私有记忆（只有你能看到）===
{chr(10).join(self.private_memory) if self.private_memory else '暂无'}

【推理步骤要求】
1. 确认自己身份、本回合唯一可用技能。
2. 构思一段符合身份或人设的发言，绝不能直接自爆身份。
3. 只能选择存活、非自己的玩家作为目标。
"""
        if error_hint:
            prompt += f"\n⚠️上一轮输出违反游戏规则：{error_hint}，请严格修正，输出合法JSON！"
        prompt += """
【输出硬性要求】
只输出严格JSON，禁止额外解释、markdown、多余文字
格式：
{"speech": "你的公开发言", "action": {"skill": "技能英文名称", "target": 目标玩家编号}}
"""
        return prompt.strip()

    def act(self, player: Player, state: GameState, retry_times=2) -> str | None:
        current_skill = player.available_skill.value if player.available_skill else "无"
        error_msg = ""
        for attempt in range(retry_times):
            user_prompt = self._build_prompt(player, state, error_hint=error_msg)
            try:
                response = client.chat.completions.create(
                    model="qwen-plus",
                    messages=[
                        {"role": "system", "content": "你是桌游《官斗牌》的玩家。你极其聪明且善于伪装，遵守最高铁律，输出合法JSON。"},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.8, # 温度调高一点，让 AI 戏精一点
                    response_format={"type": "json_object"}
                )
                raw_text = response.choices[0].message.content
                json.loads(raw_text)
                extract_res = ext_validator.extract_action(raw_text)
                ok, check_msg = ext_validator.validate_by_rule(extract_res, player, state, current_skill)
                if ok:
                    return raw_text
                else:
                    error_msg = check_msg
                    continue
            except Exception as e:
                error_msg = f"LLM调用或解析异常:{str(e)}"
                continue

        alive_target_list = [p.player_id for p in state.players if p.is_alive and p.player_id != self.player_id]
        safe_target = alive_target_list[0] if alive_target_list else 0
        fallback_data = {
            "speech": random.choice(self.fallback_speeches),
            "action": {"skill": "report", "target": safe_target}
        }
        print(f"[玩家{self.player_id}] NLP校验重试耗尽，返回兜底动作，原因：{error_msg}")
        return json.dumps(fallback_data, ensure_ascii=False)

    def add_private_memory(self, info: str):
        self.private_memory.append(info)
        