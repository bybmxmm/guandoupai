import time
import random
from engine.game import GameEngine
from engine.models import GamePhase
from engine.validator import validate_llm_output, validate_action_legal
from ai.bot import LLMAgent
from db import GameDB


def run_one_game(db: GameDB, game_index: int, version_tag: str) -> dict:
    """运行一局自动对局，数据写入数据库，返回本局统计。"""
    game = GameEngine()
    game.start_game()
    agents = [LLMAgent(i) for i in range(5)]
    session_id = db.start_session()
    illegal_count = 0
    format_error_count = 0
    retry_count = 0  # RAG+校验版本：记录重生成次数
    print(f"\n[{version_tag}] 第 {game_index} 局开始，session_id={session_id}")

    max_rounds = 20
    # =========【脚本看门狗：仅批量实验使用，不侵入GameEngine内部】=========
    stagnant_threshold = 5  # 残局连续N回合无击杀/策反则强制结束
    stagnant_counter = 0
    watchdog_forced_end = False
    watchdog_tie_reason = ""
    # ==================================================================

    while game.state.phase != GamePhase.FINISHED and game.state.round_num <= max_rounds:
        current_round = game.state.round_num
        round_had_kill = False
        round_had_bribe_success = False

        # 1. 所有存活玩家预生成决策
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
                print(f"  [格式错误] 玩家{player.player_id}：{msg}")
        # 2. 发言阶段（批量跑可以不打印，节省日志）
        for pid, data in decisions.items():
            if data:
                game.state.public_log.append(f"玩家{pid}发言：{data['speech']}")
        # 3. 行动阶段
        game.state.phase = GamePhase.ACTION
        for pid, data in decisions.items():
            if not data:
                continue
            player = game.state.players[pid]
            if not player.is_alive or player.available_skill is None:
                continue
            skill = data["action"]["skill"]
            target = data["action"]["target"]
            legal, msg = validate_action_legal(game.state, pid, skill, target)
            if not legal:
                illegal_count += 1
                result_msg = f"使用 {skill} 失败：{msg}"
                db.save_action(current_round, pid, skill, target, False, result_msg)
                continue
            result = game.player_action(pid, target)
            db.save_action(current_round, pid, skill, target, True, result)
            if "搜查结果" in result:
                agents[pid].add_private_memory(result)
            # ----解析行动返回结果，识别击杀、行贿成功事件----
            if "死亡" in result:
                round_had_kill = True
            if "本轮有官员被贿赂！" in result:
                round_had_bribe_success = True

        # 4. 结算 + 投票 + 回合推进
        game.settlement_phase()
        votes = {}
        for player in game.state.players:
            if player.is_alive:
                alive_targets = [p.player_id for p in game.state.players
                                 if p.is_alive and p.player_id != player.player_id]
                if alive_targets:
                    votes[player.player_id] = random.choice(alive_targets)
        game.vote_phase(votes)

        # ==========看门狗逻辑：判断残局停滞============
        if round_had_kill or round_had_bribe_success:
            stagnant_counter = 0
        else:
            stagnant_counter += 1

        alive_list = [p for p in game.state.players if p.is_alive]
        if len(alive_list) == 2:
            # 仅剩贪官、清官两个人存活
            id_set = {p.identity for p in alive_list}
            if len(id_set) == 2 and "corrupt" in [i.value for i in id_set] and "honest" in [i.value for i in id_set]:
                if stagnant_counter >= stagnant_threshold:
                    watchdog_forced_end = True
                    watchdog_tie_reason = f"看门狗：残局贪官+清官，连续{stagnant_counter}回合无击杀/策反，脚本强制平局"
                    print(f"⚠️ {watchdog_tie_reason}")
                    break
        # ==============================================

        if game.check_winner():
            break
        game.next_round()

    # ========== 修复winner类型兼容BUG ==========
    if watchdog_forced_end:
        winner = "tie_watchdog"
    else:
        if game.state.winner is not None:
            if hasattr(game.state.winner, "value"):
                winner = game.state.winner.value
            else:
                winner = game.state.winner
        else:
            winner = "unknown"

    total_rounds = game.state.round_num
    # 保存每个玩家本局结局
    for p in game.state.players:
        db.save_player_result(
            player_id=p.player_id,
            identity=p.identity.value,
            is_alive=p.is_alive,
            is_betrayed=p.is_betrayed,
            final_health=p.health
        )
    db.end_session(total_rounds, winner, illegal_count, format_error_count)
    print(f"[{version_tag}] 第 {game_index} 局结束 | 胜者:{winner} | 回合:{total_rounds} "
          f"| 非法:{illegal_count} | 格式错:{format_error_count}")
    return {
        "session_id": session_id,
        "version": version_tag,
        "winner": winner,
        "rounds": total_rounds,
        "illegal": illegal_count,
        "format_err": format_error_count,
    }


def main():
    # ============ 跑哪一组，就改这里 ============
    VERSION_TAG = "RAG+Validator"   # 基线组:"Baseline"，CoT组:"CoT"，实验组:"RAG+Validator"
    GAME_COUNT = 20                 # 每组跑 20 局
    # ============================================
    db = GameDB()
    results = []
    try:
        for i in range(1, GAME_COUNT + 1):
            res = run_one_game(db, i, VERSION_TAG)
            results.append(res)
            time.sleep(1)   # 避免大模型 API 限流
    finally:
        db.close()
    # 控制台汇总统计
    justice_win = sum(1 for r in results if r["winner"] == "justice")
    corrupt_win = sum(1 for r in results if r["winner"] == "corrupt")
    # 统计看门狗强制平局数量
    watchdog_tie_cnt = sum(1 for r in results if r["winner"] == "tie_watchdog")

    avg_illegal = sum(r["illegal"] for r in results) / len(results)
    avg_fmterr = sum(r["format_err"] for r in results) / len(results)
    print("\n" + "=" * 50)
    print(f"[{VERSION_TAG}] 共 {GAME_COUNT} 局跑完")
    print(f"正义胜:{justice_win}  贪官胜:{corrupt_win}  脚本强制平局:{watchdog_tie_cnt}")
    print(f"平均非法动作:{avg_illegal:.2f}  平均格式错误:{avg_fmterr:.2f}")
    print("=" * 50)


if __name__ == "__main__":
    main()

