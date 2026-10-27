import pymysql
from datetime import datetime
import os

# 【修改提醒 1】：导入 dotenv 库，用于加载 .env 文件中的环境变量
from dotenv import load_dotenv
load_dotenv()  # 自动读取项目根目录下的 .env 文件

# ==============================================
# 【修改提醒 2】：数据库配置从 .env 文件中动态读取，防止密码泄露
# ==============================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),      # 从环境变量读取，若无则默认本地
    "port": int(os.getenv("DB_PORT", 3306)),        # 从环境变量读取端口并转为整数
    "user": os.getenv("DB_USER", "root"),           # 从环境变量读取用户名
    "password": os.getenv("DB_PASSWORD"),           # 从环境变量读取密码（去掉默认值，强制必须提供）
    "database": os.getenv("DB_NAME", "guandoupai_db"), # 从环境变量读取数据库名
    "charset": "utf8mb4"
}

class GameDB:
    def __init__(self):
        self.conn = pymysql.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor()
        self.current_session_id = None

    def start_session(self) -> int:
        """开启一局新对局，返回session_id"""
        sql = "INSERT INTO game_sessions (start_time) VALUES (%s)"
        self.cursor.execute(sql, (datetime.now(),))
        self.conn.commit()
        self.current_session_id = self.cursor.lastrowid
        return self.current_session_id

    def end_session(self, total_rounds: int, winner: str, illegal_count: int, format_error_count: int):
        """结束对局，更新结果"""
        sql = """
            UPDATE game_sessions
            SET end_time=%s, total_rounds=%s, winner=%s, illegal_action_count=%s, format_error_count=%s
            WHERE session_id=%s
        """
        self.cursor.execute(sql, (
            datetime.now(), total_rounds, winner,
            illegal_count, format_error_count, self.current_session_id
        ))
        self.conn.commit()

    def save_player_result(self, player_id: int, identity: str, is_alive: bool, is_betrayed: bool, final_health: int):
        """保存玩家最终状态"""
        sql = """
            INSERT INTO game_players (session_id, player_id, identity, is_alive, is_betrayed, final_health)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        self.cursor.execute(sql, (
            self.current_session_id, player_id, identity,
            1 if is_alive else 0, 1 if is_betrayed else 0, final_health
        ))
        self.conn.commit()

    def save_action(self, round_num: int, player_id: int, skill: str, target_id: int, is_legal: bool, result_msg: str):
        """保存单条动作日志"""
        sql = """
            INSERT INTO game_actions (session_id, round_num, player_id, skill, target_id, is_legal, result_msg)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        self.cursor.execute(sql, (
            self.current_session_id, round_num, player_id,
            skill, target_id, 1 if is_legal else 0, result_msg
        ))
        self.conn.commit()

    def close(self):
        """关闭连接"""
        self.cursor.close()
        self.conn.close()
