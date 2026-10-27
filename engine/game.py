import random
from typing import List, Dict
from .models import Player, GameState, Identity, Position, GamePhase, SkillType
from .skills import SKILL_EXECUTORS
# 【新增】：导入剧本生成器
from .scenario import get_random_position, get_random_clue 

class GameEngine:
    def __init__(self, player_count: int = 5):
        self.player_count = player_count
        self.state = None
        self._init_power_deck()

    def _init_power_deck(self):
        self.deck = []
        for _ in range(4):
            for point in range(1, 14):
                self.deck.append(point)
        random.shuffle(self.deck)

    def _draw_power_cards(self, count: int) -> List[int]:
        cards = []
        for _ in range(count):
            if not self.deck:
                self._init_power_deck()
            cards.append(self.deck.pop())
        return cards

    def _assign_identities(self) -> List[Identity]:
        identities = [
            Identity.CORRUPT, Identity.HONEST, Identity.DISCIPLINE,
            Identity.PEOPLE, Identity.PEOPLE,
        ]
        random.shuffle(identities)
        return identities

    def _assign_positions(self) -> List[Position]:
        positions = list(Position)
        random.shuffle(positions)
        return positions[:self.player_count]

    # 【修改】：增加模式开关参数
    def start_game(self, is_scenario_mode: bool = False):
        """初始化游戏，进入第一回合"""
        identities = self._assign_identities()
        positions = self._assign_positions()
        players = []
        for i in range(self.player_count):
            player = Player(
                player_id=i,
                identity=identities[i],
                position=positions[i],
                power_cards=self._draw_power_cards(5),
                # 【新增】：分配公开职位
                public_position=get_random_position() if is_scenario_mode else "普通公职人员"
            )
            players.append(player)
            
        self.state = GameState(players=players)
        # 【新增】：记录模式
        self.state.is_scenario_mode = is_scenario_mode
        
        if self.state.is_scenario_mode:
            self.state.public_log.append("📜【剧本模式已开启】请代入你们的公开职位进行发言，隐藏身份绝不可直接暴露！")
            
        self.state.public_log.append("游戏开始，5名玩家身份已秘密分配")
        self._start_round()

    def _start_round(self):
        """开启新回合：投骰获取技能"""
        self.state.vote_targets.clear()
        self.state.public_log.append(f"\n=== 第 {self.state.round_num} 回合 ===")
        self.state.phase = GamePhase.ROLL_SKILL
        
        # 【新增】：如果是剧本模式，每回合抽一张线索卡
        if self.state.is_scenario_mode:
            self.state.current_clue = get_random_clue()
            self.state.public_log.append(f"📢【专案公告】{self.state.current_clue}")
            
        dice_skill_map = {
            1: SkillType.BRIBE, 2: SkillType.SEARCH, 3: SkillType.REPORT,
            4: SkillType.DETAIN, 5: SkillType.PEOPLES_WILL, 6: SkillType.ASSASSINATE,
        }
        identity_allow_skills = {
            Identity.CORRUPT: {SkillType.BRIBE, SkillType.ASSASSINATE},
            Identity.HONEST: {SkillType.SEARCH, SkillType.PEOPLES_WILL},
            Identity.DISCIPLINE: {SkillType.SEARCH, SkillType.DETAIN},
            Identity.PEOPLE: {SkillType.SEARCH, SkillType.REPORT},
        }
        for player in self.state.players:
            if player.is_alive:
                dice = random.randint(1, 6)
                rolled_skill = dice_skill_map[dice]
                actual_identity = Identity.CORRUPT if player.is_betrayed else player.identity
                allow_set = identity_allow_skills[actual_identity]
                
                if rolled_skill in allow_set:
                    player.available_skill = rolled_skill
                    self.state.public_log.append(f"玩家{player.player_id}投出{dice}点，获得技能：{rolled_skill.value}")
                else:
                    player.available_skill = None
                    self.state.public_log.append(f"玩家{player.player_id}投出{dice}点，技能{rolled_skill.value}与身份不匹配，本回合无可用技能")
            else:
                player.available_skill = None
        self.state.phase = GamePhase.SPEECH

    def player_action(self, player_id: int, target_id: int = None) -> str:
        if self.state.phase != GamePhase.ACTION:
            return "[错误] 当前不是行动阶段"
        player = self.state.players[player_id]
        if not player.is_alive or player.available_skill is None:
            return "[错误] 该玩家无法行动"
        skill = player.available_skill
        executor = SKILL_EXECUTORS[skill]
        result = executor(self.state, player_id, target_id)
        self.state.public_log.append(result)
        return result

    def settlement_phase(self):
        self.state.phase = GamePhase.SETTLEMENT
        for player in self.state.players:
            if player.is_alive:
                player.power_cards.extend(self._draw_power_cards(1))
                if player.health <= 0:
                    player.is_alive = False
                    self.state.public_log.append(f"⚰️ [死亡播报] 玩家{player.player_id} 已阵亡！")
        self.state.public_log.append("[结算] 所有存活玩家补充1张战力牌")
        self.state.phase = GamePhase.VOTE

    def vote_phase(self, votes: Dict[int, int]):
        if self.state.phase != GamePhase.VOTE:
            return
        for voter_id, target_id in votes.items():
            voter = self.state.players[voter_id]
            if voter.is_alive and target_id is not None:
                self.state.vote_targets[target_id] = self.state.vote_targets.get(target_id, 0) + 1
        if self.state.vote_targets:
            max_votes = max(self.state.vote_targets.values())
            top_targets = [pid for pid, v in self.state.vote_targets.items() if v == max_votes]
            if len(top_targets) == 1:
                target = self.state.players[top_targets[0]]
                target.health -= 1
                if target.health <= 0:
                    target.is_alive = False
                    self.state.public_log.append(f"[投票] 玩家{top_targets[0]}得票最多（{max_votes}票），扣除1点生命值。")
                    self.state.public_log.append(f"⚰️ [死亡播报] 玩家{top_targets[0]} 被公投处决！")
                else:
                    self.state.public_log.append(f"[投票] 玩家{top_targets[0]}得票最多（{max_votes}票），扣除1点生命值")
            else:
                self.state.public_log.append("[投票] 平票，无人受到伤害")
        else:
            self.state.public_log.append("[投票] 无人参与投票，无结果")
        self.state.phase = GamePhase.END_ROUND

    def check_winner(self) -> bool:
        alive_honest = [p for p in self.state.players if p.is_alive and p.identity == Identity.HONEST and not p.is_betrayed]
        all_initial_honest = [p for p in self.state.players if p.identity == Identity.HONEST]
        all_corrupt_dead = all(not p.is_alive for p in self.state.players if p.identity == Identity.CORRUPT or p.is_betrayed)
        
        if all_corrupt_dead and len(alive_honest) >= 1:
            self.state.winner = "justice"
            self.state.phase = GamePhase.FINISHED
            self.state.public_log.append("\n=== 游戏结束：正义阵营胜利（所有贪官死亡且清官存活）===")
            return True

        all_justice_dead = all(not p.is_alive or p.is_betrayed for p in self.state.players if p.identity in [Identity.HONEST, Identity.DISCIPLINE])
        all_honest_betrayed = len(all_initial_honest) > 0 and all(p.is_betrayed for p in all_initial_honest)
        
        if all_justice_dead or all_honest_betrayed:
            self.state.winner = "corrupt"
            self.state.phase = GamePhase.FINISHED
            reason = "所有清官和纪委阵亡/被策反" if all_justice_dead else "所有清官均已被策反"
            self.state.public_log.append(f"\n=== 游戏结束：贪官阵营胜利（{reason}）===")
            return True
        return False

    def next_round(self):
        if self.state.phase == GamePhase.FINISHED:
            return
        self.state.round_num += 1
        self._start_round()

    def run_full_turn(self, actions: Dict[int, int], votes: Dict[int, int]):
        if self.state.phase == GamePhase.FINISHED:
            return
        self.state.phase = GamePhase.ACTION
        for pid, tid in actions.items():
            if self.state.players[pid].is_alive:
                self.player_action(pid, tid)
        self.settlement_phase()
        self.vote_phase(votes)
        if not self.check_winner():
            self.next_round()