import json
import logging
import threading
import time
import random
from typing import List, Dict, Any, Optional
from flask import Flask, jsonify, request, render_template_string
from pydantic import BaseModel
import engine
import world

app = Flask(__name__)

# --- Состояние веб-симуляции ---
class SimulationState:
    def __init__(self):
        self.lock = threading.Lock()
        self.started = False
        self.tick = 0
        self.game_over = False
        self.winner = None
        self.is_auto_running = False
        self.auto_speed = 1.0  # секунды между ходами
        self.logs = []
        self.agent_histories = {}
        self.agents = []
        self.arbiter = engine.ArbitorAI()
        self.current_events = []
        self.map_core = world.MapCore(5, 5)

    def start_or_reset(self):
        with self.lock:
            self.tick = 0
            self.game_over = False
            self.winner = None
            self.is_auto_running = False
            self.logs = []
            self.agent_histories = {}
            
            # Загрузка агентов из свежего agents_config.json
            agents_data = engine.load_agents("agents_config.json")
            self.arbiter = engine.ArbitorAI()
            self.agents = [engine.Stage1AI(state) for state in agents_data]
            self.current_events = []
            self.map_core = world.MapCore(5, 5)
            self.map_core.spawn_mines()

            for ai in self.agents:
                self.agent_histories[ai.state.name] = []

            self.started = True
            self.add_log("INFO", "Симуляция успешно запущена! Агенты загружены.")

    def add_log(self, level: str, message: str, agent_name: Optional[str] = None):
        log_entry = {
            "tick": self.tick,
            "timestamp": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "agent": agent_name
        }
        self.logs.append(log_entry)
        if len(self.logs) > 300:
            self.logs.pop(0)

    def do_step(self):
        with self.lock:
            if not self.started or self.game_over:
                return

            self.tick += 1
            self.add_log("INFO", f"--- НАЧАЛО ХОДА {self.tick} ---")
            
            for ai in self.agents:
                state = ai.state
                
                # Начисление пассивного дохода
                passive_inc = self.map_core.calculate_passive_income(state.name) if hasattr(self, 'map_core') else {"matter": 0, "energy": 0, "imagination": 0}
                state.balance.matter += state.income.matter + passive_inc["matter"]
                state.balance.energy += state.income.energy + passive_inc["energy"]
                state.balance.imagination += state.income.imagination + passive_inc["imagination"]
                
                self.add_log(
                    "INCOME", 
                    f"[{state.name}] получил доход (+{state.income.matter + passive_inc['matter']}M, +{state.income.energy + passive_inc['energy']}E, +{state.income.imagination + passive_inc['imagination']}I). Баланс: {state.balance.matter}M, {state.balance.energy}E, {state.balance.imagination}I",
                    state.name
                )

                # Запрос к LLM
                prompt = ai.generate_prompt(self.map_core)
                response_raw = engine.api_bridge.send(state.api_key, state.model, prompt)
                
                action_type = "pass"
                try:
                    action_data = json.loads(response_raw)
                    action_type = action_data.get("action", "pass")
                except Exception:
                    pass

                # Валидация Арбитром
                prev_balance = state.balance.model_dump()
                self.arbiter.check_elements(state, response_raw, self.map_core)
                new_balance = state.balance.model_dump()

                # Запись истории
                history_entry = {
                    "tick": self.tick,
                    "action": action_type,
                    "raw_response": response_raw,
                    "prev_balance": prev_balance,
                    "new_balance": new_balance,
                    "income": state.income.model_dump()
                }
                self.agent_histories[state.name].append(history_entry)

                if action_type == "capture":
                    tx, ty = action_data.get("target_x"), action_data.get("target_y")
                    self.add_log("ACTION", f"[{state.name}] ЗАХВАТЫВАЕТ клетку ({tx}, {ty})", state.name)
                elif action_type == "build_wall":
                    tx, ty = action_data.get("target_x"), action_data.get("target_y")
                    self.add_log("ACTION", f"[{state.name}] СТРОИТ СТЕНУ на ({tx}, {ty})", state.name)
                elif action_type == "upgrade_mine":
                    tx, ty = action_data.get("target_x"), action_data.get("target_y")
                    self.add_log("ACTION", f"[{state.name}] УЛУЧШАЕТ ШАХТУ на ({tx}, {ty})", state.name)
                elif action_type == "pass":
                    self.add_log("ACTION", f"[{state.name}] решил пропустить ход (PASS).", state.name)
                else:
                    self.add_log("ACTION", f"[{state.name}] действие: {action_type}", state.name)

                # Победа
                if (state.balance.matter >= 1500 and 
                    state.balance.energy >= 1500 and 
                    state.balance.imagination >= 1500):
                    self.game_over = True
                    self.winner = state.name
                    self.is_auto_running = False
                    self.add_log("VICTORY", f"🏆 АГЕНТ {state.name} ДОСТИГ 1500 ВСЕХ РЕСУРСОВ И ПОБЕДИЛ! 🏆", state.name)
                    break

sim = SimulationState()

def auto_run_loop():
    while True:
        time.sleep(sim.auto_speed)
        if sim.is_auto_running and not sim.game_over:
            sim.do_step()

auto_thread = threading.Thread(target=auto_run_loop, daemon=True)
auto_thread.start()

# --- API Endpoints ---

@app.route('/api/state', methods=['GET'])
def get_state():
    with sim.lock:
        agents_info = []
        for ai in sim.agents:
            st = ai.state
            last_hist = sim.agent_histories[st.name][-1] if sim.agent_histories[st.name] else None
            agents_info.append({
                "name": st.name,
                "model": st.model,
                "balance": st.balance.model_dump(),
                "income": st.income.model_dump(),
                "breakthroughs": st.breakthroughs,
                "last_action": last_hist["action"] if last_hist else "N/A",
                "total_actions": len(sim.agent_histories[st.name]),
                "history": sim.agent_histories[st.name]
            })

        events_info = [e.model_dump() for e in sim.current_events]

        return jsonify({
            "started": sim.started,
            "tick": sim.tick,
            "game_over": sim.game_over,
            "winner": sim.winner,
            "is_auto_running": sim.is_auto_running,
            "auto_speed": sim.auto_speed,
            "agents": agents_info,
            "events": events_info,
            "logs": sim.logs[-100:],
            "map": json.loads(sim.map_core.get_map_state_json()) if hasattr(sim, 'map_core') else []
        })

@app.route('/api/start', methods=['POST'])
def api_start():
    sim.start_or_reset()
    return jsonify({"success": True})

@app.route('/api/step', methods=['POST'])
def api_step():
    sim.do_step()
    return jsonify({"success": True, "tick": sim.tick})

@app.route('/api/toggle_auto', methods=['POST'])
def api_toggle_auto():
    with sim.lock:
        sim.is_auto_running = not sim.is_auto_running
    return jsonify({"is_auto_running": sim.is_auto_running})

# --- UI HTML ---
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Sandbox</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #090d16;
            --card-bg: rgba(21, 29, 46, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-cyan: #06b6d4;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body { background-color: var(--bg-dark); color: var(--text-main); min-height: 100vh; display: flex; flex-direction: column; }
        
        header {
            display: flex; justify-content: space-between; align-items: center;
            background: var(--card-bg); border-bottom: 1px solid var(--card-border);
            padding: 16px 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }
        .brand { font-size: 20px; font-weight: 700; color: var(--accent-cyan); }
        .controls { display: flex; gap: 12px; align-items: center; }
        
        .btn {
            background: rgba(255,255,255,0.05); border: 1px solid var(--card-border);
            color: #fff; padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: 0.2s;
        }
        .btn:hover { background: rgba(255,255,255,0.1); }
        .btn-primary { background: linear-gradient(135deg, var(--accent-cyan), #0284c7); border: none; }
        .btn-success { background: linear-gradient(135deg, var(--accent-emerald), #059669); border: none; }
        
        .tick-badge { font-weight: bold; color: var(--accent-amber); margin-right: 16px; }

        .start-screen {
            flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
        }
        .start-btn {
            font-size: 24px; padding: 16px 40px; border-radius: 12px; background: linear-gradient(135deg, #a855f7, var(--accent-cyan));
            color: #fff; border: none; cursor: pointer; box-shadow: 0 10px 30px rgba(168, 85, 247, 0.4); transition: 0.3s;
        }
        .start-btn:hover { transform: scale(1.05); }

        .main-layout {
            display: none; /* Скрыто до запуска */
            flex: 1; padding: 20px; display: grid; grid-template-columns: 300px 1fr; gap: 20px; height: calc(100vh - 70px);
        }

        /* Левая панель - Список ИИ */
        .sidebar { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 16px; overflow-y: auto; }
        .agent-list-item {
            padding: 12px; border: 1px solid transparent; border-radius: 8px; cursor: pointer;
            background: rgba(255,255,255,0.02); margin-bottom: 8px; transition: 0.2s;
        }
        .agent-list-item:hover { background: rgba(255,255,255,0.05); border-color: var(--card-border); }
        .agent-list-item.active { background: rgba(6, 182, 212, 0.1); border-color: var(--accent-cyan); }
        
        /* Правая панель - Детали и Консоль */
        .content-area { display: flex; flex-direction: column; gap: 20px; overflow: hidden; }
        
        .agent-details { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; flex: 1; overflow-y: auto; }
        .agent-details h2 { color: var(--accent-cyan); margin-bottom: 12px; }
        
        .terminal {
            background: #050811; border: 1px solid var(--card-border); border-radius: 12px; padding: 16px;
            font-family: 'JetBrains Mono', monospace; font-size: 13px; height: 35%; overflow-y: auto;
        }
        .log-item { line-height: 1.5; margin-bottom: 4px; }
        
        .progress-bar { height: 6px; background: rgba(255,255,255,0.1); border-radius: 4px; margin-top: 4px; }
        .progress-fill { height: 100%; border-radius: 4px; background: var(--accent-cyan); }
    </style>
</head>
<body>

    <header>
        <div class="brand">🤖 AI Sandbox</div>
        <div class="controls" id="headerControls" style="display: none;">
            <div class="tick-badge">⏱️ ХОД: <span id="tickCounter">0</span></div>
            <button class="btn btn-primary" onclick="doStep()">▶️ Сделать ход</button>
            <button class="btn btn-success" id="autoBtn" onclick="toggleAuto()">⏯️ Авто-запуск</button>
            <button class="btn" onclick="startSim()">🔄 Сброс (Перезагрузить JSON)</button>
        </div>
    </header>

    <div class="start-screen" id="startScreen">
        <h1 style="margin-bottom: 24px; font-size: 32px;">Симуляция готова к запуску</h1>
        <p style="color: var(--text-muted); margin-bottom: 32px;">Настройки агентов будут загружены из agents_config.json</p>
        <button class="start-btn" onclick="startSim()">ЗАПУСТИТЬ СИМУЛЯЦИЮ</button>
    </div>

    <div class="main-layout" id="mainLayout">
        <div class="sidebar">
            <h3 style="margin-bottom: 16px; color: var(--text-muted);">Список Агентов</h3>
            <div id="agentList"></div>
        </div>

        <div class="content-area">
            <div style="display: flex; gap: 20px; flex: 1; overflow: hidden;">
                <div class="agent-details" id="agentDetails" style="flex: 1;">
                    <div style="color: var(--text-muted); text-align: center; margin-top: 40px;">
                        Выберите агента из списка слева, чтобы увидеть подробную информацию и логи ходов.
                    </div>
                </div>
                <div class="map-container" style="flex: 1; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; display: flex; align-items: center; justify-content: center;">
                    <div id="mapGrid" style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; width: 100%; max-width: 400px; aspect-ratio: 1/1;">
                    </div>
                </div>
            </div>

            <div class="terminal" id="terminalLog"></div>
        </div>
    </div>

    <script>
        let selectedAgent = null;
        let globalData = null;

        async function fetchState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                globalData = data;
                renderUI(data);
            } catch (err) {
                console.error("API error:", err);
            }
        }

        async function startSim() {
            await fetch('/api/start', { method: 'POST' });
            selectedAgent = null;
            document.getElementById('startScreen').style.display = 'none';
            document.getElementById('mainLayout').style.display = 'grid';
            document.getElementById('headerControls').style.display = 'flex';
            fetchState();
        }

        async function doStep() { await fetch('/api/step', { method: 'POST' }); fetchState(); }
        async function toggleAuto() { await fetch('/api/toggle_auto', { method: 'POST' }); fetchState(); }

        function selectAgent(name) {
            selectedAgent = name;
            renderUI(globalData);
        }

        function renderUI(data) {
            if (!data.started) {
                document.getElementById('startScreen').style.display = 'flex';
                document.getElementById('mainLayout').style.display = 'none';
                document.getElementById('headerControls').style.display = 'none';
                return;
            }

            document.getElementById('tickCounter').innerText = data.tick;
            document.getElementById('autoBtn').innerText = data.is_auto_running ? "⏸️ Пауза" : "⏯️ Авто-запуск";

            // Рендер списка агентов
            const listContainer = document.getElementById('agentList');
            listContainer.innerHTML = '';
            
            data.agents.forEach(agent => {
                const div = document.createElement('div');
                div.className = `agent-list-item ${selectedAgent === agent.name ? 'active' : ''}`;
                div.onclick = () => selectAgent(agent.name);
                
                const mPct = Math.min(100, (agent.balance.matter / 200) * 100);
                
                div.innerHTML = `
                    <div style="font-weight: 600;">${agent.name}</div>
                    <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Модель: ${agent.model}</div>
                    <div style="font-size: 11px;">M: ${agent.balance.matter} | E: ${agent.balance.energy} | I: ${agent.balance.imagination}</div>
                    <div class="progress-bar"><div class="progress-fill" style="width: ${mPct}%"></div></div>
                `;
                listContainer.appendChild(div);
            });

            // Рендер деталей выбранного агента
            const detailsContainer = document.getElementById('agentDetails');
            if (selectedAgent) {
                const agent = data.agents.find(a => a.name === selectedAgent);
                if (agent) {
                    let historyHtml = agent.history.slice().reverse().map(h => `
                        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); padding: 12px; border-radius: 8px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <b>Ход ${h.tick}</b>
                                <span style="color: var(--accent-amber);">${h.action}</span>
                            </div>
                            <div style="font-family: monospace; font-size: 11px; color: #94a3b8; background: #000; padding: 8px; border-radius: 4px;">
                                Raw: ${h.raw_response}
                            </div>
                        </div>
                    `).join('');

                    detailsContainer.innerHTML = `
                        <h2>${agent.name} <span style="font-size: 14px; color: var(--text-muted);">(${agent.model})</span></h2>
                        <div style="display: flex; gap: 20px; margin-bottom: 20px;">
                            <div>
                                <h4 style="color: var(--text-muted);">Текущий Баланс</h4>
                                <div>Matter: <b>${agent.balance.matter}</b> / 200</div>
                                <div>Energy: <b>${agent.balance.energy}</b> / 200</div>
                                <div>Imagination: <b>${agent.balance.imagination}</b> / 200</div>
                            </div>
                            <div>
                                <h4 style="color: var(--text-muted);">Пассивный Доход</h4>
                                <div>Matter: +${agent.income.matter}</div>
                                <div>Energy: +${agent.income.energy}</div>
                                <div>Imagination: +${agent.income.imagination}</div>
                            </div>
                        </div>
                        <h3 style="margin-bottom: 10px; color: var(--text-muted);">История ответов:</h3>
                        <div>${historyHtml || '<p>Действий еще нет.</p>'}</div>
                    `;
                }
            }

            // Рендер терминала
            const terminal = document.getElementById('terminalLog');
            terminal.innerHTML = data.logs.map(log => 
                `<div class="log-item">
                    <span style="color: #64748b;">[${log.timestamp}]</span> 
                    <span style="color: ${log.level === 'STEAL' ? '#f59e0b' : (log.level === 'VICTORY' ? '#f43f5e' : '#38bdf8')};">
                        ${log.message}
                    </span>
                </div>`
            ).join('');
            terminal.scrollTop = terminal.scrollHeight;
            
            // Рендер карты
            const mapContainer = document.getElementById('mapGrid');
            if (data.map) {
                mapContainer.innerHTML = '';
                for(let y=0; y<5; y++){
                    for(let x=0; x<5; x++){
                        const cellData = data.map.find(c => c.x === x && c.y === y);
                        const div = document.createElement('div');
                        div.style.border = "1px solid rgba(255,255,255,0.1)";
                        div.style.borderRadius = "4px";
                        div.style.display = "flex";
                        div.style.flexDirection = "column";
                        div.style.alignItems = "center";
                        div.style.justifyContent = "center";
                        div.style.fontSize = "11px";
                        div.style.position = "relative";
                        div.style.aspectRatio = "1/1";
                        
                        let bgColor = "rgba(0,0,0,0.2)";
                        if (cellData && cellData.owner) {
                            if (cellData.owner.includes("Alpha")) bgColor = "rgba(244, 63, 94, 0.2)";
                            else if (cellData.owner.includes("Beta")) bgColor = "rgba(56, 189, 248, 0.2)";
                            else bgColor = "rgba(16, 185, 129, 0.2)";
                        }
                        div.style.background = bgColor;
                        
                        let html = "";
                        if (cellData) {
                            let icon = "";
                            if (cellData.structure === 'Wall') icon = "🧱";
                            else if (cellData.resource === 'Matter') icon = "⚛️";
                            else if (cellData.resource === 'Energy') icon = "⚡";
                            else if (cellData.resource === 'Imagination') icon = "💡";
                            
                            html += `<div style="font-size:24px;">${icon}</div>`;
                            if (cellData.level > 0) {
                                html += `<div style="color: var(--accent-amber); font-weight: bold;">Lvl ${cellData.level}</div>`;
                            }
                            if (cellData.owner) {
                                const initial = cellData.owner.charAt(0);
                                html += `<div style="position:absolute; top:4px; right:4px; font-weight:bold; color:#fff; background: rgba(0,0,0,0.5); padding: 2px 4px; border-radius: 4px; font-size:10px;">${initial}</div>`;
                            }
                        }
                        div.innerHTML = html;
                        mapContainer.appendChild(div);
                    }
                }
            }
        }

        setInterval(fetchState, 1000);
        fetchState();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("🚀 Запуск веб-панели управления AI Sandbox на http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
