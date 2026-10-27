import random
from engine.game import GameEngine
from engine.models import GamePhase


def random_ai_actions(game: GameEngine):
    """随机AI：为存活玩家随机选择技能目标"""
    actions = {}
    for player in game.state.players:
        if player.is_alive and player.available_skill:
            alive_targets = [p.player_id for p in game.state.players if p.is_alive and p.player_id != player.player_id]
            if alive_targets:
                actions[player.player_id] = random.choice(alive_targets)
    return actions


def random_ai_votes(game: GameEngine):
    """随机AI：随机投票"""
    votes = {}
    for player in game.state.players:
        if player.is_alive:
            alive_targets = [p.player_id for p in game.state.players if p.is_alive and p.player_id != player.player_id]
            if alive_targets:
                votes[player.player_id] = random.choice(alive_targets)
    return votes


if __name__ == "__main__":
    game = GameEngine()
    game.start_game()

    # 自动运行直到游戏结束
    while game.state.phase != GamePhase.FINISHED:
        actions = random_ai_actions(game)
        votes = random_ai_votes(game)
        game.run_full_turn(actions, votes)

    # 打印对局日志
    for log in game.state.public_log:
        print(log)

    print(f"\n最终胜者阵营：{game.state.winner}")
    print("\n身份揭晓：")
    for p in game.state.players:
        status = "存活" if p.is_alive else "死亡"
        betrayed = "（已策反）" if p.is_betrayed else ""
        print(f"玩家{p.player_id}: {p.identity.value} | {status}{betrayed}")
