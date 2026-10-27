from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# 隐藏身份枚举
class Identity(Enum):
    CORRUPT = "corrupt"      # 贪官
    HONEST = "honest"        # 清官
    DISCIPLINE = "discipline" # 纪委
    PEOPLE = "people"        # 人民

# 公开职位枚举（保留兼容）
class Position(Enum):
    MAGISTRATE = "magistrate"   # 知县
    GOVERNOR = "governor"       # 知府
    INSPECTOR = "inspector"     # 巡按
    SQUIRE = "squire"           # 乡绅
    MERCHANT = "merchant"       # 商户

# 游戏阶段枚举（状态机）
class GamePhase(Enum):
    READY = "ready"           
    ROLL_SKILL = "roll_skill" 
    SPEECH = "speech"         
    ACTION = "action"         
    SETTLEMENT = "settlement" 
    VOTE = "vote"             
    END_ROUND = "end_round"   
    FINISHED = "finished"     

# 技能类型枚举
class SkillType(Enum):
    BRIBE = "bribe"                
    SEARCH = "search"              
    REPORT = "report"              
    DETAIN = "detain"              
    PEOPLES_WILL = "peoples_will"  
    ASSASSINATE = "assassinate"    

@dataclass
class Player:
    player_id: int                  
    identity: Identity              
    position: Position              
    health: int = 2                 
    power_cards: List[int] = field(default_factory=list) 
    available_skill: Optional[SkillType] = None  
    skill_used: Dict[SkillType, int] = field(default_factory=dict) 
    is_alive: bool = True           
    is_betrayed: bool = False       
    
    # 【新增】：剧本模式专属——公开职位（字符串）
    public_position: str = "普通公职人员" 

    def __post_init__(self):
        for skill in SkillType:
            self.skill_used[skill] = 0

@dataclass
class GameState:
    players: List[Player]
    round_num: int = 1
    phase: GamePhase = GamePhase.READY
    public_log: List[str] = field(default_factory=list)
    winner: Optional[str] = None  
    vote_targets: Dict[int, int] = field(default_factory=dict) 
    
    # 【新增】：剧本模式专属状态
    is_scenario_mode: bool = False  
    current_clue: str = "暂无线索"    