import streamlit as st
import time
import json
from datetime import datetime
from engine.game import GameEngine
from engine.models import GamePhase, Identity
from ai.enhanced_bot import EnhancedAgent
from engine.validator import validate_llm_output, validate_action_legal
from ai.nlp_extract_validator import RuleExtractorValidator
from db import GameDB
import pandas as pd
import matplotlib.pyplot as plt

ENABLE_UI_WATCHDOG = True
STAGNANT_THRESHOLD_UI = 5
ext_validator = RuleExtractorValidator()

st.set_page_config(page_title="官斗牌 - 多智能体博弈系统", layout="wide", initial_sidebar_state="expanded")
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

if 'game' not in st.session_state:
    st.session_state.game = None
    st.session_state.agents = None
    st.session_state.logs = []
    st.session_state.round = 0
    st.session_state.game_over = False
    st.session_state.illegal_stats = {"identity": 0, "target": 0, "format": 0}
    st.session_state.stagnant_counter_ui = 0
    st.session_state.watchdog_forced_end_ui = False
    st.session_state.is_simulating = False 
    st.session_state.auto_play = False 

def append_log(log_type: str, content: str):
    st.session_state.logs.append({"type": log_type, "content": content})

def render_log_panel():
    st.subheader("📜 公共对局日志")
    log_box = st.container(height=500, border=True)
    with log_box:
        for item in st.session_state.logs:
            t = item["type"]
            txt = item["content"]
            if t == "phase": st.markdown(f"--- \n### 🎬 {txt}")
            elif t == "system": st.markdown(f":gray[{txt}]")
            elif t == "nlp": st.markdown(f":blue[🧠 {txt}]")
            elif t == "illegal": st.markdown(f":red[⚠️ {txt}]")
            elif t == "success": st.markdown(f":green[✅ {txt}]")
            elif t == "speech": st.markdown(f"> 💬 **{txt}**")
            else: st.write(txt)

with st.sidebar:
    st.title("🎮 控制面板")
    st.subheader("对局操作")
    
    # 【修复1】：绑定 key，防止状态丢失
    st.checkbox("📜 开启剧本模式（角色扮演）", value=False, key="enable_scenario")
    
    if st.button("🔄 开始新对局", type="primary", use_container_width=True):
        st.session_state.game = GameEngine()
        # 【修复2】：直接从 session_state 读取最安全的布尔值
        is_scenario = st.session_state.get("enable_scenario", False)
        st.session_state.game.start_game(is_scenario_mode=is_scenario)
        game = st.session_state.game
        st.session_state.agents = []
        for player in game.state.players:
            agent = EnhancedAgent(player_id=player.player_id)
            st.session_state.agents.append(agent)
        st.session_state.logs = []
        append_log("phase", "=== 官斗牌 AI 对局开始 ===")
        if is_scenario:
            append_log("system", "🎭 剧本模式已激活！请留意各玩家的公开职位与专案线索。")
        st.session_state.round = 1
        st.session_state.game_over = False
        st.session_state.illegal_stats = {"identity": 0, "target": 0, "format": 0}
        st.session_state.stagnant_counter_ui = 0
        st.session_state.watchdog_forced_end_ui = False
        st.session_state.is_simulating = False
        st.session_state.auto_play = False 
        st.rerun()

    if st.session_state.game and not st.session_state.game_over:
        st.checkbox("⏩ 自动播放（每回合停顿3秒）", key="auto_play", disabled=st.session_state.is_simulating)
    else:
        st.session_state.auto_play = False
        st.checkbox("⏩ 自动播放（每回合停顿3秒）", value=False, disabled=True)

    trigger_next = st.button("▶️ 下一回合", use_container_width=True, disabled=st.session_state.is_simulating or st.session_state.auto_play)

    if st.session_state.game and not st.session_state.game_over:
        if (trigger_next or st.session_state.auto_play) and not st.session_state.is_simulating:
            st.session_state.is_simulating = True
            try:
                with st.spinner("⏳ 正在串行调用玩家大模型接口，规避并发限流..."):
                    game = st.session_state.game
                    agents = st.session_state.agents
                    current_round = game.state.round_num
                    decisions = {}
                    append_log("system", "[串行模式] 逐个调用AI")

                    for player in game.state.players:
                        pid = player.player_id
                        if not player.is_alive or player.available_skill is None:
                            decisions[pid] = None
                            append_log("system", f"[串行] 玩家{pid} 跳过（死亡/无技能）")
                            continue
                        
                        # 【新增】：把分配到的公开职位打出来，方便你确认剧本模式生效
                        if game.state.is_scenario_mode:
                            append_log("system", f"[剧本] 玩家{pid} 的公开职位是：{player.public_position}")
                            
                        agent = agents[pid]
                        raw_output = agent.act(player, game.state)
                        check_res = ext_validator.extract_action(str(raw_output))
                        append_log("nlp", f"[NLP抽取器]玩家{pid}: {check_res}")
                        valid, data, msg = validate_llm_output(str(raw_output))
                        if valid:
                            decisions[pid] = data
                        else:
                            decisions[pid] = None
                            append_log("illegal", f"[警告] 玩家{pid} 输出格式错误：{msg}")
                            st.session_state.illegal_stats["format"] += 1
                        time.sleep(0.2)

                    append_log("phase", f"第 {current_round} 回合 发言阶段")
                    for pid, data in decisions.items():
                        if data:
                            append_log("speech", f"玩家{pid}：{data['speech']}")

                    append_log("phase", "行动阶段")
                    game.state.phase = GamePhase.ACTION
                    for pid, data in decisions.items():
                        if not data: continue
                        player = game.state.players[pid]
                        if not player.is_alive or player.available_skill is None: continue
                        skill = data["action"]["skill"]
                        target = data["action"]["target"]
                        legal, msg = validate_action_legal(game.state, pid, skill, target)
                        if not legal:
                            append_log("illegal", f"[非法] 玩家{pid} 使用 {skill} 失败：{msg}")
                            if "身份不匹配" in msg:
                                st.session_state.illegal_stats["identity"] += 1
                            else:
                                st.session_state.illegal_stats["target"] += 1
                            continue
                        
                        result = game.player_action(pid, target)
                        if "[非法]" in result or "失败" in result or "误抓" in result or "战力不足" in result:
                            append_log("illegal", f"[技能结算] {result}")
                        else:
                            append_log("success", f"[技能结算] {result}")
                            
                        if "搜查结果" in result:
                            agents[pid].add_private_memory(result)

                    old_log_len = len(game.state.public_log)
                    game.settlement_phase()
                    for new_log in game.state.public_log[old_log_len:]:
                        append_log("system", new_log)

                    votes = {}
                    for player in game.state.players:
                        if player.is_alive:
                            alive_targets = [p.player_id for p in game.state.players if p.is_alive and p.player_id != player.player_id]
                            if alive_targets:
                                import random
                                votes[player.player_id] = random.choice(alive_targets)
                    
                    old_log_len = len(game.state.public_log)
                    game.vote_phase(votes)
                    for new_log in game.state.public_log[old_log_len:]:
                        append_log("system", new_log)

                    if ENABLE_UI_WATCHDOG and not st.session_state.watchdog_forced_end_ui:
                        round_had_kill_ui = False
                        round_had_bribe_success_ui = False
                        recent_logs = st.session_state.logs[-12:]
                        for log_item in recent_logs:
                            cnt = log_item["content"]
                            if "死亡" in cnt: round_had_kill_ui = True
                            if "本轮有官员被贿赂！" in cnt: round_had_bribe_success_ui = True
                        if round_had_kill_ui or round_had_bribe_success_ui:
                            st.session_state.stagnant_counter_ui = 0
                        else:
                            st.session_state.stagnant_counter_ui += 1
                            append_log("system", f"[看门狗DEBUG]连续无进展回合数={st.session_state.stagnant_counter_ui}")
                        
                        if st.session_state.stagnant_counter_ui >= STAGNANT_THRESHOLD_UI:
                            st.session_state.watchdog_forced_end_ui = True
                            game.state.winner = "tie_watchdog"
                            game.state.phase = GamePhase.FINISHED
                            append_log("illegal", f"⚠️看门狗触发：连续{STAGNANT_THRESHOLD_UI}回合无击杀/策反，判定平局")

                    if game.check_winner() or st.session_state.watchdog_forced_end_ui:
                        append_log("phase", f"🏁 游戏结束，胜者阵营：{game.state.winner}")
                        st.session_state.game_over = True
                    else:
                        game.next_round()
                        st.session_state.round = game.state.round_num
            finally:
                st.session_state.is_simulating = False
            
            if st.session_state.auto_play and not st.session_state.game_over:
                time.sleep(3)
            
            st.rerun()

    st.divider()
    if st.session_state.game is not None:
        export_payload = json.dumps({
            "round": st.session_state.round,
            "game_over": st.session_state.game_over,
            "winner": str(st.session_state.game.state.winner) if st.session_state.game_over else None,
            "log_list": st.session_state.logs,
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, ensure_ascii=False, indent=2)
        st.download_button(label="📥 导出本局完整日志JSON", data=export_payload, file_name=f"官斗牌对局_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json", use_container_width=True)

st.title("🏛️ 官斗牌 - 多智能体博弈系统")

if st.session_state.game:
    cols = st.columns(5)
    identity_color = {"people": "blue", "honest": "green", "discipline": "orange", "corrupt": "red"}
    identity_name = {"people": "人民", "honest": "清官", "discipline": "纪委", "corrupt": "贪官"}
    
    for idx, player in enumerate(st.session_state.game.state.players):
        with cols[idx]:
            opacity = "0.4" if not player.is_alive else "1.0"
            bg_color = "#f0f2f6" if not player.is_alive else "#ffffff"
            
            with st.container():
                # 【修复3】：如果是剧本模式，职位显示为绿色并加粗
                if st.session_state.game.state.is_scenario_mode:
                    pos_text = f"👔 职位: {player.public_position}"
                    pos_color = "#28a745"
                else:
                    pos_text = "纯竞技模式"
                    pos_color = "#007bff"
                
                st.markdown(f"""
                <div style="opacity: {opacity}; background-color: {bg_color}; padding: 10px; border-radius: 10px; border: 1px solid #ddd;">
                    <h4 style="margin:0;">玩家 {idx}</h4>
                    <p style="margin:5px 0; color: {pos_color};"><b>{pos_text}</b></p>
                    <p style="margin:5px 0;">状态: {'💀 死亡' if not player.is_alive else '❤️ 血量: ' + str(player.health)}</p>
                    <p style="margin:0;">技能: {player.available_skill.value if player.available_skill and player.is_alive else '无'}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if st.session_state.game_over:
                    id_val = player.identity.value
                    st.markdown(f":{identity_color[id_val]}[**隐藏身份：{identity_name[id_val]}**]")
                    if player.is_betrayed:
                        st.caption("⚠️ 已被策反")
                else:
                    show_id = st.checkbox(f"查验身份", key=f"show_{idx}")
                    if show_id:
                        id_val = player.identity.value
                        st.markdown(f":{identity_color[id_val]}[**隐藏身份：{identity_name[id_val]}**]")
                        if player.is_betrayed:
                            st.caption("⚠️ 已被策反")

    st.divider()
    log_col, chart_col = st.columns([2, 1])
    with log_col:
        render_log_panel()
        
    with chart_col:
        st.subheader("📈 全局局面")
        st.metric("当前回合", f"第 {st.session_state.round} 回合")
        
        if st.session_state.game.state.is_scenario_mode:
            st.info(f"**📢 当前专案线索**\n\n{st.session_state.game.state.current_clue}")
            
        alive_count = sum(1 for p in st.session_state.game.state.players if p.is_alive)
        justice_count = sum(1 for p in st.session_state.game.state.players if p.is_alive and not p.is_betrayed and p.identity in [Identity.PEOPLE, Identity.HONEST, Identity.DISCIPLINE])
        corrupt_count = sum(1 for p in st.session_state.game.state.players if p.is_alive and (p.identity == Identity.CORRUPT or p.is_betrayed))
        
        col1, col2, col3 = st.columns(3)
        col1.metric("存活人数", alive_count)
        col2.metric("正义", justice_count)
        col3.metric("贪官", corrupt_count)
        
        st.divider()
        st.subheader("🚨 非法动作统计")
        stats = st.session_state.illegal_stats
        st.markdown(f"""
        - 格式解析失败：<span style="color:red;">{stats['format']} 次</span>
        - 身份权限越界：<span style="color:red;">{stats['identity']} 次</span>
        - 目标选择无效：<span style="color:red;">{stats['target']} 次</span>
        """, unsafe_allow_html=True)
        
        if st.session_state.game_over:
            st.success(f"🏆 获胜阵营：{st.session_state.game.state.winner}")