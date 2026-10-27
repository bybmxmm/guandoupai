import time
import random
from engine.game import GameEngine
from engine.models import GamePhase
from engine.validator import validate_llm_output, validate_action_legal
from ai.bot import LLMAgent
from db import GameDB  # 导入数据库模块

def run_one_game(db: GameDB, game_index: int) -> dict:
    """运行一局游戏，并存入数据库，返回统计数据"""
    game = GameEngine()
    game.start_game()
    agents = [LLMAgent(i) for i in range(5)]

    # 开启数据库对局记录
    session_id = db.start_session()
    illegal_count = 0
    format_error_count = 0

    print(f"\n{'='*40}")
    print(f"第 {game_index} 局开始，session_id={session_id}")
    print('='*40)

    max_rounds = 20
    while game.state.phase != GamePhase.FINISHED and game.state.round_num <= max_rounds:
        current_round = game.state.round_num

        # 1. 预生成所有存活玩家决策
        decisions = {}
        for player in game.state.players:
            if not player.is_alive or player.available_skill is None:
                decisions[player.player_id] = None
                continue

            agent = agents[player.player_id]
            raw_output = agent.act(player, game.state)
            valid, data, msg = validate_llm_output(raw_output)

            if valid:
                decisions[player.player_id] = data
            else:
                decisions[player.player_id] = None
                format_error_count += 1
                print(f"[警告] 玩家{player.player_id} 输出格式错误：{msg}")

        # 2. 发言阶段
        print(f"\n--- 第 {current_round} 回合 发言阶段 ---")
        for pid, data in decisions.items():
            if data:
                speech = data["speech"]
                print(f"玩家{pid}：{speech}")
                game.state.public_log.append(f"玩家{pid}发言：{speech}")

        # 3. 行动阶段
        print(f"\n--- 第 {current_round} 回合 行动阶段 ---")
        game.state.phase = GamePhase.ACTION

        for pid, data in decisions.items():
            if not data:
                continue

            player = game.state.players[pid]
            if not player.is_alive or player.available_skill is None:
                continue

            skill = data["action"]["skill"]
            target = data["action"]["target"]

            # 规则合法性校验
            legal, msg = validate_action_legal(game.state, pid, skill, target)
            if not legal:
                illegal_count += 1
                result_msg = f"使用 {skill} 失败：{msg}"
                print(f"[非法] 玩家{pid} {result_msg}")
                game.state.public_log.append(f"[非法] 玩家{pid}{result_msg}")
                # 存入数据库
                db.save_action(current_round, pid, skill, target, False, result_msg)
                continue

            # 执行技能
            result = game.player_action(pid, target)
            print(result)
            db.save_action(current_round, pid, skill, target, True, result)

            # 搜查结果存入私有记忆
            if "搜查结果" in result:
                agents[pid].add_private_memory(result)

        # 4. 结算阶段
        game.settlement_phase()

        # 5. 投票阶段
        votes = {}
        for player in game.state.players:
            if player.is_alive:
                alive_targets = [p.player_id for p in game.state.players
                               if p.is_alive and p.player_id != player.player_id]
                if alive_targets:
                    votes[player.player_id] = random.choice(alive_targets)
        game.vote_phase(votes)

        # 6. 胜负判定
        if game.check_winner():
            break

        game.next_round()
        time.sleep(0.5)

    # 游戏结束，写入结果
    winner = game.state.winner if game.state.winner else "unknown"

    total_rounds = game.state.round_num

    # 保存玩家最终状态
    for p in game.state.players:
        db.save_player_result(
            player_id=p.player_id,
            identity=p.identity.value,
            is_alive=p.is_alive,
            is_betrayed=p.is_betrayed,
            final_health=p.health
        )

    # 更新对局总表
    db.end_session(total_rounds, winner, illegal_count, format_error_count)

    print(f"\n第 {game_index} 局结束，胜者：{winner}，总回合：{total_rounds}")
    return {
        "session_id": session_id,
        "winner": winner,
        "rounds": total_rounds,
        "illegal_count": illegal_count,
        "format_error_count": format_error_count
    }


def main():
    # ==============================================
    # 【需要你修改】想跑多少局就改这个数字
    # ==============================================
    GAME_COUNT = 10  # 批量跑10局

    db = GameDB()
    results = []

    try:
        for i in range(1, GAME_COUNT + 1):
            res = run_one_game(db, i)
            results.append(res)
    finally:
        db.close()

    # 控制台输出汇总
    print("\n" + "="*50)
    print(f"全部 {GAME_COUNT} 局跑完，结果已存入MySQL数据库")
    justice_win = sum(1 for r in results if r["winner"] == "justice")
    corrupt_win = sum(1 for r in results if r["winner"] == "corrupt")
    print(f"正义阵营胜场：{justice_win}  |  贪官阵营胜场：{corrupt_win}")
    print("="*50)


if __name__ == "__main__":
    main()
