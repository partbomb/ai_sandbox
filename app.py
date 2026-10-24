import json
import logging
import threading
import asyncio
import time
import csv
import io
from typing import List
from flask import Flask, jsonify, render_template_string, request, Response
import world

app = Flask(__name__)

# --- АСИНХРОННЫЙ МОСТ ФЛАСК <-> СИМУЛЯЦИЯ ---

class WebState:
    def __init__(self):
        self.started = False
        self.tick = 0
        self.logs = []
        self.world_map: world.MapCore = None
        self.agents: List[world.Stage2AI] = []
        self.arbiter: world.ArbitorPhysical = None
        self.tasks = []
        self.async_tasks = []
        self.game_over = False
        self.winner = ""
        self.history = {"tick": [], "agents": {}}
        self.ablation = {"no_compass": False, "ablated_agent": None}
        
        # Создаем луп в отдельном потоке
        self.async_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        # Запускаем фоновый цикл для глобального тика один раз
        asyncio.run_coroutine_threadsafe(self._map_tick_loop(), self.async_loop)

    def _run_loop(self):
        asyncio.set_event_loop(self.async_loop)
        self.async_loop.run_forever()

    async def _map_tick_loop(self):
        while True:
            try:
                if self.started and self.world_map:
                    self.tick += 1
                    async with self.world_map.lock:
                        total_mines = sum(1 for row in self.world_map.grid for c in row if c.resource_type is not None)
                        
                        for agent in self.agents:
                            if agent.is_dead:
                                if getattr(agent, 'respawn_timer', 0) > 0:
                                    agent.respawn_timer -= 1
                                    if agent.respawn_timer <= 0:
                                        agent.is_dead = False
                                        agent.hp = 100
                                        agent.balance = {"matter": 50, "energy": 50, "imagination": 50}
                                        agent.position = world.Position(x=agent.base_position.x, y=agent.base_position.y)
                                        self.add_log("TICK", f"✨ {agent.name} ВОЗРОДИЛСЯ на базе!")
                                        logging.info(f"[{agent.name}] ✨ ВОЗРОДИЛСЯ на базе!")
                                continue
                                
                            agent.score = sum(1 for row in self.world_map.grid for cell in row if cell.owner_id == agent.name)
                            
                            matter_mines = sum(1 for row in self.world_map.grid for c in row if c.owner_id == agent.name and c.resource_type == 'Matter')
                            energy_mines = sum(1 for row in self.world_map.grid for c in row if c.owner_id == agent.name and c.resource_type == 'Energy')
                            imag_mines = sum(1 for row in self.world_map.grid for c in row if c.owner_id == agent.name and c.resource_type == 'Imagination')
                            
                            income_base = 12 if "economy_lvl_2" in agent.unlocked_techs else 10
                            
                            agent.balance["matter"] += matter_mines * income_base
                            agent.balance["energy"] += energy_mines * income_base
                            agent.balance["imagination"] += imag_mines * income_base
                            
                            agent.balance["energy"] -= 5
                            if agent.balance["energy"] <= 0:
                                agent.balance["energy"] = 0
                                if not agent.is_dead:
                                    agent.is_dead = True
                                    agent.deaths_count = getattr(agent, 'deaths_count', 0) + 1
                                    agent.respawn_timer = 5
                                    self.add_log("TICK", f"💀 {agent.name} ПОГИБ ОТ ГОЛОДА!")
                                    logging.info(f"[{agent.name}] 💀 ПОГИБ ОТ ГОЛОДА!")
                                    
                                    # Выпадение лута
                                    c = self.world_map.get_cell(agent.position.x, agent.position.y)
                                    if c:
                                        for res in ['matter', 'energy', 'imagination']:
                                            c.loot[res] = c.loot.get(res, 0) + agent.balance[res]
                                            agent.balance[res] = 0
                                continue
                                
                            if agent.balance["matter"] >= 5000 and agent.balance["energy"] >= 5000 and agent.balance["imagination"] >= 5000:
                                self.add_log("TICK", f"🏆 {agent.name} ДОСТИГ ТЕХНОЛОГИЧЕСКОЙ СИНГУЛЯРНОСТИ И ПОБЕДИЛ!")
                                logging.info(f"🏆 {agent.name} ДОСТИГ ТЕХНОЛОГИЧЕСКОЙ СИНГУЛЯРНОСТИ И ПОБЕДИЛ!")
                                self.game_over = True
                                self.winner = agent.name
                                break
                                
                            agent_mines = matter_mines + energy_mines + imag_mines
                            if total_mines > 0 and (agent_mines / total_mines) >= 0.8:
                                self.add_log("TICK", f"🏆 {agent.name} ДОСТИГ АБСОЛЮТНОЙ МОНОПОЛИИ (80% шахт) И ПОБЕДИЛ!")
                                logging.info(f"🏆 {agent.name} ДОСТИГ АБСОЛЮТНОЙ МОНОПОЛИИ (80% шахт) И ПОБЕДИЛ!")
                                self.game_over = True
                                self.winner = agent.name
                                break

                        # Научная телеметрия: динамика суммарного капитала по тикам
                        self.history["tick"].append(self.tick)
                        for agent in self.agents:
                            if agent.name not in self.history["agents"]:
                                self.history["agents"][agent.name] = []
                            total_res = sum(agent.balance.values()) if isinstance(agent.balance, dict) else 0
                            self.history["agents"][agent.name].append(total_res)

                        # Ограничение длины истории для предотвращения утечки памяти (500 тиков)
                        if len(self.history["tick"]) > 500:
                            self.history["tick"].pop(0)
                            for a_name in self.history["agents"]:
                                if len(self.history["agents"][a_name]) > 500:
                                    self.history["agents"][a_name].pop(0)

                        if not self.started or self.game_over:
                            for task in self.async_tasks:
                                self.async_loop.call_soon_threadsafe(task.cancel)
                            self.async_tasks.clear()
            except Exception as e:
                logging.error(f"Tick Loop Error: {e}")
            await asyncio.sleep(4.3)

    def add_log(self, level, message):

        self.logs.append({
            "timestamp": time.strftime("%H:%M:%S"), 
            "level": level, 
            "message": message
        })
        if len(self.logs) > 150: 
            self.logs.pop(0)

web_state = WebState()

# Перехват логов из world.py в наш web_state
class WebLogHandler(logging.Handler):
    def emit(self, record):
        level = record.levelname
        msg = record.getMessage()
        if "ГЛОБАЛЬНЫЙ" in msg: 
            level = "TICK"
        else:
            # Для агентов оставляем INFO/WARNING/ERROR
            pass
        web_state.add_log(level, msg)

logging.getLogger("WorldMap").addHandler(WebLogHandler())

# --- API ---

async def _create_agent_tasks(agents, world_map, arbiter, web_state):
    for task in web_state.async_tasks:
        task.cancel()
    web_state.async_tasks = []
    for agent in agents:
        t = asyncio.create_task(world.agent_loop(agent, world_map, arbiter, agents))
        web_state.async_tasks.append(t)

@app.route('/api/start', methods=['POST'])
def api_start():
    req = request.get_json(silent=True) or {}
    mode = req.get("mode", "ai_only")
    ablation_no_compass = bool(req.get("ablation_no_compass", False))
    try:
        with open("agents_config.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
    web_state.world_map = world.MapCore(width=10, height=10)
    web_state.world_map.spawn_mines()
    web_state.world_map.spawn_casinos(4)  # 4 казино на карте 10x10
    web_state.arbiter = world.ArbitorPhysical()
    
    import random
    web_state.agents = []
    
    if mode == "with_human":
        pos = world.Position(x=random.randint(0, 9), y=random.randint(0, 9))
        human = world.Stage2AI("Human-Player", "", "", pos, {"matter": 10, "energy": 10, "imagination": 10}, is_human=True)
        web_state.agents.append(human)
    
    # Динамическая загрузка всех агентов
    for agent_data in data.get("agents", []):
        # Назначаем случайную позицию
        pos = world.Position(x=random.randint(0, 9), y=random.randint(0, 9))
        agent_obj = world.Stage2AI(agent_data["name"], agent_data["api_key"], agent_data["model"], pos, agent_data.get("income", {}))
        web_state.agents.append(agent_obj)

    # Режим LLM vs RL: спавн обученного RL-агента (PPO) вместе с LLM-агентами
    if mode == "llm_vs_rl":
        rl_pos = world.Position(x=random.randint(0, 9), y=random.randint(0, 9))
        rl_agent = world.Stage2AI(
            name="RL-PPO-Bot",
            api_key="",
            model="PPO-RL-Agent",
            start_pos=rl_pos,
            init_income={"matter": 10, "energy": 10, "imagination": 10},
            is_rl=True,
            rl_model_path="rl_models/best/best_model"
        )
        web_state.agents.append(rl_agent)
        web_state.add_log("INFO", "🤖 RL-PPO-Bot успешно добавлен на арену (PPO Policy Network)")
    
    web_state.tick = 0
    web_state.history = {"tick": [], "agents": {a.name: [] for a in web_state.agents}}
    web_state.logs = []
    web_state.add_log("INFO", "=== ЗАПУСК ФАЗЫ 2 (КАРТА) ===")

    # Ablation Study: отключение Стратегического Компаса у последнего LLM-агента
    # (RL-бот и человек пропускаются — у них нет LLM-промпта)
    web_state.ablation = {"no_compass": ablation_no_compass, "ablated_agent": None}
    if ablation_no_compass:
        llm_agents = [a for a in web_state.agents if not getattr(a, 'is_rl', False) and not getattr(a, 'is_human', False)]
        if llm_agents:
            target = llm_agents[-1]
            target.use_compass = False
            target.long_term_memory = ""
            web_state.ablation["ablated_agent"] = target.name
            web_state.add_log("INFO", f"🧪 ABLATION: Стратегический Компас отключен у агента {target.name} (контрольная группа)")
        else:
            web_state.add_log("INFO", "🧪 ABLATION: нет LLM-агентов для отключения Компаса")
    
    # Отменяем старые таски если есть
    for task in web_state.tasks:
        task.cancel()
    web_state.tasks.clear()
    
    # Запускаем независимые циклы для каждого агента
    asyncio.run_coroutine_threadsafe(
        _create_agent_tasks(web_state.agents, web_state.world_map, web_state.arbiter, web_state),
        web_state.async_loop
    )
        
    web_state.started = True
    return jsonify({"success": True})


@app.route('/api/state', methods=['GET'])
def get_state():
    if not web_state.started:
        return jsonify({"started": False})
        
    grid_data = []
    for y in range(web_state.world_map.height):
        row = []
        for x in range(web_state.world_map.width):
            cell = web_state.world_map.grid[x][y]
            avatar = next((a.name for a in web_state.agents if a.position.x == x and a.position.y == y), None)
            
            row.append({
                "x": x, "y": y,
                "owner": cell.owner_id,
                "resource": cell.resource_type,
                "structure": cell.structure,
                "avatar": avatar,
                "casino_jackpot": cell.casino_jackpot if cell.structure == 'Casino' else 0
            })
        grid_data.append(row)
        
    agents_data = []
    for a in web_state.agents:
        m = a.get_metrics() if hasattr(a, 'get_metrics') else {
            "total_actions": getattr(a, 'total_actions', 0),
            "invalid_actions": getattr(a, 'invalid_actions', 0),
            "attacks_count": getattr(a, 'attacks_count', 0),
            "captures_count": getattr(a, 'captures_count', 0),
            "deaths_count": getattr(a, 'deaths_count', 0),
            "fixation_loops": getattr(a, 'fixation_loops', 0),
            "aggression_index": 0.0,
            "fixation_rate": 0.0,
            "invalid_rate": 0.0
        }
        agents_data.append({
            "name": a.name,
            "score": a.score,
            "x": a.position.x,
            "y": a.position.y,
            "balance": a.balance,
            "is_dead": a.is_dead,
            "hp": getattr(a, 'hp', 100),
            "respawn_timer": getattr(a, 'respawn_timer', 0),
            "unlocked_techs": getattr(a, 'unlocked_techs', []),
            "short_term_memory": getattr(a, 'short_term_memory', []),
            "long_term_memory": getattr(a, 'long_term_memory', ''),
            "is_rl": getattr(a, 'is_rl', False),
            "inbox": getattr(a, 'inbox', []),
            "use_compass": getattr(a, 'use_compass', True),
            "use_short_memory": getattr(a, 'use_short_memory', True),
            "metrics": m
        })
    
    return jsonify({
        "started": True,
        "game_over": web_state.game_over,
        "winner": web_state.winner,
        "tick": web_state.tick,
        "map": grid_data,
        "agents": agents_data,
        "logs": web_state.logs,
        "diplomacy_log": web_state.world_map.diplomacy_log if (web_state.world_map and hasattr(web_state.world_map, 'diplomacy_log')) else [],
        "history": web_state.history,
        "ablation": web_state.ablation
    })


@app.route('/api/export_metrics', methods=['GET'])
def export_metrics():
    format_type = request.args.get('format', 'json').lower()
    
    if format_type == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 1. Сводная таблица по агентам
        writer.writerow(["=== AGENT RESEARCH METRICS SUMMARY ==="])
        writer.writerow([
            "Agent Name", "Is RL", "Use Compass", "Use Short Memory", "Status", "Score (Cells)",
            "Total Actions", "Invalid Actions", "Invalid Rate (%)",
            "Attacks", "Captures", "Aggression Index (%)",
            "Deaths", "Fixation Loops", "Fixation Rate (%)",
            "Matter", "Energy", "Imagination", "Total Resources", "Unlocked Techs"
        ])
        
        for a in web_state.agents:
            m = a.get_metrics() if hasattr(a, 'get_metrics') else {}
            techs = ";".join(getattr(a, 'unlocked_techs', []))
            total_res = sum(a.balance.values()) if isinstance(a.balance, dict) else 0
            writer.writerow([
                a.name,
                getattr(a, 'is_rl', False),
                getattr(a, 'use_compass', True),
                getattr(a, 'use_short_memory', True),
                "DEAD" if a.is_dead else "ALIVE",
                a.score,
                m.get("total_actions", 0),
                m.get("invalid_actions", 0),
                m.get("invalid_rate", 0.0),
                m.get("attacks_count", 0),
                m.get("captures_count", 0),
                m.get("aggression_index", 0.0),
                m.get("deaths_count", 0),
                m.get("fixation_loops", 0),
                m.get("fixation_rate", 0.0),
                a.balance.get("matter", 0),
                a.balance.get("energy", 0),
                a.balance.get("imagination", 0),
                total_res,
                techs
            ])
            
        writer.writerow([])
        # 2. Динамика капитала по тикам
        writer.writerow(["=== TICK-BY-TICK RESOURCE DYNAMICS (NET WORTH) ==="])
        agent_names = list(web_state.history.get("agents", {}).keys())
        writer.writerow(["Tick"] + agent_names)
        
        ticks = web_state.history.get("tick", [])
        for i, t in enumerate(ticks):
            row = [t]
            for name in agent_names:
                series = web_state.history["agents"].get(name, [])
                val = series[i] if i < len(series) else ""
                row.append(val)
            writer.writerow(row)
            
        writer.writerow([])
        # 3. Лог дипломатии
        writer.writerow(["=== DIPLOMACY AND COMMUNICATION LOG ==="])
        writer.writerow(["Time", "Sender", "Receiver", "Type", "Message"])
        dip_log = web_state.world_map.diplomacy_log if (web_state.world_map and hasattr(web_state.world_map, 'diplomacy_log')) else []
        for d in dip_log:
            writer.writerow([
                d.get("time", ""),
                d.get("sender", ""),
                d.get("receiver", ""),
                d.get("type", ""),
                d.get("message", "")
            ])
            
        csv_content = output.getvalue()
        output.close()
        
        filename = f"experiment_telemetry_tick_{web_state.tick}.csv"
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    else:  # JSON format
        export_data = {
            "experiment": {
                "current_tick": web_state.tick,
                "game_over": web_state.game_over,
                "winner": web_state.winner,
                "ablation": web_state.ablation,
                "export_time": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "agents": [
                {
                    "name": a.name,
                    "is_rl": getattr(a, 'is_rl', False),
                    "use_compass": getattr(a, 'use_compass', True),
                    "use_short_memory": getattr(a, 'use_short_memory', True),
                    "is_dead": a.is_dead,
                    "score": a.score,
                    "balance": a.balance,
                    "total_resources": sum(a.balance.values()) if isinstance(a.balance, dict) else 0,
                    "position": {"x": a.position.x, "y": a.position.y},
                    "unlocked_techs": getattr(a, 'unlocked_techs', []),
                    "metrics": a.get_metrics() if hasattr(a, 'get_metrics') else {},
                    "long_term_memory": getattr(a, 'long_term_memory', ''),
                    "short_term_memory": getattr(a, 'short_term_memory', [])
                }
                for a in web_state.agents
            ],
            "resource_dynamics": web_state.history,
            "diplomacy_log": web_state.world_map.diplomacy_log if (web_state.world_map and hasattr(web_state.world_map, 'diplomacy_log')) else [],
            "logs": web_state.logs
        }
        json_content = json.dumps(export_data, ensure_ascii=False, indent=2)
        filename = f"experiment_telemetry_tick_{web_state.tick}.json"
        return Response(
            json_content,
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

@app.route('/api/human_prompt', methods=['GET'])
def get_human_prompt():
    human = next((a for a in web_state.agents if getattr(a, 'is_human', False)), None)
    if human and not human.human_ready.is_set() and not human.is_dead:
        return jsonify({"has_turn": True, "prompt": human.human_prompt})
    return jsonify({"has_turn": False})

@app.route('/api/human_action', methods=['POST'])
def post_human_action():
    human = next((a for a in web_state.agents if getattr(a, 'is_human', False)), None)
    if human:
        data = request.get_json(silent=True)
        human.human_action = data
        web_state.async_loop.call_soon_threadsafe(human.human_ready.set)
        return jsonify({"success": True})
    return jsonify({"success": False})


# --- WEB UI ---

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Sandbox - Phase 2</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-dark: #090d16;
            --card-bg: rgba(21, 29, 46, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-cyan: #06b6d4;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body { background-color: var(--bg-dark); color: var(--text-main); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
        
        header {
            display: flex; justify-content: space-between; align-items: center;
            background: var(--card-bg); border-bottom: 1px solid var(--card-border);
            padding: 16px 24px;
        }
        
        .start-btn {
            background: linear-gradient(135deg, var(--accent-cyan), #0284c7);
            color: #fff; border: none; padding: 10px 20px; border-radius: 8px;
            font-weight: 600; cursor: pointer; transition: 0.2s;
        }
        .start-btn:hover { filter: brightness(1.2); }
        
        .main-layout { display: flex; flex: 1; height: calc(100vh - 65px); }
        
        .sidebar { width: 300px; border-right: 1px solid var(--card-border); background: var(--card-bg); padding: 20px; display: flex; flex-direction: column; gap: 16px; overflow-y: auto; }
        .agent-card {
            background: rgba(255,255,255,0.03); border: 1px solid var(--card-border);
            border-radius: 12px; padding: 16px;
        }
        .agent-card h3 { margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
        
        .map-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            background: radial-gradient(circle, #1a2333 0%, var(--bg-dark) 100%);
            overflow-y: auto;
            padding: 16px;
            gap: 16px;
        }
        .telemetry-panel {
            width: 100%;
            max-width: 580px;
            background: rgba(15, 23, 42, 0.75);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 14px 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        
        .map-grid {
            display: grid; gap: 4px; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 12px;
            border: 1px solid var(--card-border);
        }
        .cell {
            width: 48px; height: 48px; background: rgba(255,255,255,0.05); border-radius: 8px;
            display: flex; align-items: center; justify-content: center; font-size: 24px;
            position: relative; border: 2px solid transparent; transition: 0.3s;
        }
        .cell-casino {
            background: linear-gradient(135deg, rgba(245,158,11,0.15), rgba(234,88,12,0.15)) !important;
            border-color: rgba(245,158,11,0.4) !important;
            animation: casino-pulse 2s ease-in-out infinite;
        }
        @keyframes casino-pulse {
            0%, 100% { box-shadow: 0 0 5px rgba(245,158,11,0.2); }
            50% { box-shadow: 0 0 15px rgba(245,158,11,0.5); }
        }
        .jackpot-label {
            position: absolute; bottom: -2px; left: 50%; transform: translateX(-50%);
            font-size: 7px; color: #f59e0b; font-weight: 700; font-family: 'JetBrains Mono';
            white-space: nowrap; text-shadow: 0 0 3px rgba(0,0,0,0.8);
        }
        
        .avatar-badge {
            position: absolute; right: -6px; top: -6px; width: 20px; height: 20px;
            border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 10px rgba(0,0,0,0.5);
            display: flex; align-items: center; justify-content: center; font-size: 10px; z-index: 10;
        }

        .terminal-container { width: 380px; background: #050811; border-left: 1px solid var(--card-border); display: flex; flex-direction: column; }
        .terminal-header { padding: 8px 12px; background: var(--card-bg); border-bottom: 1px solid var(--card-border); font-weight: 600; font-family: 'JetBrains Mono'; font-size: 14px; }
        .terminal { flex: 1; padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
        
        .tab-btn {
            background: transparent; border: none; color: var(--text-muted); padding: 6px 12px;
            font-size: 12px; font-weight: 600; cursor: pointer; border-radius: 6px; transition: 0.2s;
            display: flex; align-items: center; gap: 6px; font-family: 'Outfit', sans-serif;
        }
        .tab-btn:hover { color: var(--text-main); background: rgba(255,255,255,0.05); }
        .tab-btn.active { color: #fff; background: rgba(6, 182, 212, 0.15); border: 1px solid rgba(6, 182, 212, 0.35); }
        .dip-badge {
            background: #ef4444; color: #fff; font-size: 9px; padding: 1px 5px; border-radius: 10px; font-weight: 700;
        }

        .log-TICK { color: #f59e0b; font-weight: bold; }
        .log-INFO { color: var(--text-muted); }
    </style>
</head>
<body>

    <header>
        <div style="font-size: 20px; font-weight: 700; color: var(--accent-cyan);">🤖 AI Sandbox - Phase 2 (Async Grid)</div>
        <div style="display: flex; gap: 12px; align-items: center;">
            <div id="tickCounter" style="font-weight: 600; color: #f59e0b; display: none;">⏱️ ТИК: 0</div>
            <label id="ablationToggle" title="Ablation Study: последний LLM-агент играет без Стратегического Компаса (долгосрочной памяти) — контрольная группа для сравнения" style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: #fcd34d; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); padding: 6px 10px; border-radius: 8px; cursor: pointer; user-select: none;">
                <input type="checkbox" id="ablationNoCompass" style="accent-color: #f59e0b; cursor: pointer;">
                🧪 Ablation: Отключить Компас у последнего агента
            </label>
            <div id="ablationStatus" style="display: none; font-size: 11px; font-weight: 600; color: #fcd34d; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); padding: 4px 8px; border-radius: 6px;"></div>
            <button class="start-btn" onclick="startSim('ai_only')" id="startBtnAI">ЗАПУСК (ТОЛЬКО ИИ)</button>
            <button class="start-btn" style="background: linear-gradient(135deg, #8b5cf6, #7c3aed);" onclick="startSim('llm_vs_rl')" id="startBtnRL">ЗАПУСК (LLM vs RL)</button>
            <button class="start-btn" style="background: linear-gradient(135deg, #10b981, #059669);" onclick="startSim('with_human')" id="startBtnHuman">ЗАПУСК (С ЧЕЛОВЕКОМ)</button>
            <div id="exportBtns" style="display: none; gap: 8px;">
                <button class="start-btn" style="background: rgba(255,255,255,0.08); border: 1px solid var(--card-border); font-size: 12px; padding: 8px 14px;" onclick="exportMetrics('json')">📥 Экспорт JSON</button>
                <button class="start-btn" style="background: rgba(255,255,255,0.08); border: 1px solid var(--card-border); font-size: 12px; padding: 8px 14px;" onclick="exportMetrics('csv')">📥 Экспорт CSV</button>
            </div>
        </div>
    </header>

    <div class="main-layout" id="mainLayout" style="display: none;">
        <div class="sidebar" id="sidebar"></div>
        <div class="map-container">
            <div class="map-grid" id="mapGrid"></div>
            <div class="telemetry-panel">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="font-size: 12px; font-weight: 700; color: var(--accent-cyan); display: flex; align-items: center; gap: 6px;">
                        📈 ДИНАМИКА КАПИТАЛА (Total Resources vs Tick)
                    </div>
                    <div style="font-size: 10px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">
                        Live Research Telemetry
                    </div>
                </div>
                <div style="height: 160px; width: 100%; position: relative;">
                    <canvas id="netWorthChart"></canvas>
                </div>
            </div>
        </div>
        <div class="terminal-container">
            <div class="terminal-header" style="display: flex; gap: 6px; align-items: center;">
                <button id="tabLogsBtn" class="tab-btn active" onclick="switchRightTab('logs')">📋 Логи (Real-time)</button>
                <button id="tabDipBtn" class="tab-btn" onclick="switchRightTab('diplomacy')">🕊️ Дипломатия и Переговоры <span id="dipBadge" class="dip-badge" style="display: none;">0</span></button>
            </div>
            <div class="terminal" id="terminalLog"></div>
            <div class="terminal" id="terminalDiplomacy" style="display: none; gap: 8px;"></div>
        </div>
    </div>

    <div id="humanPanel" style="display: none; position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--card-bg); border: 1px solid var(--accent-cyan); padding: 15px; border-radius: 12px; z-index: 100; box-shadow: 0 0 20px rgba(6, 182, 212, 0.3); width: 800px; backdrop-filter: blur(10px);">
        <h3 style="color: var(--accent-cyan); margin-bottom: 10px;">🎮 ВАШ ХОД! (У вас 60 секунд)</h3>
        <textarea id="humanPromptText" style="width: 100%; height: 180px; background: rgba(0,0,0,0.5); color: #fff; border: 1px solid var(--card-border); font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 10px; margin-bottom: 10px;" readonly></textarea>
        <div style="display: flex; gap: 10px; align-items: center;">
            <input type="text" id="humanActionInput" placeholder='{"action": "MOVE", "params": {"direction": "N"}}' style="flex: 1; padding: 10px; background: rgba(0,0,0,0.5); color: #fff; border: 1px solid var(--card-border); font-family: monospace;">
            <button onclick="sendHumanAction()" class="start-btn">ОТПРАВИТЬ ХОД</button>
        </div>
        <div style="display: flex; gap: 5px; margin-top: 10px; flex-wrap: wrap;">
            <button onclick="fillAction('MOVE', {direction:'N'})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">MOVE N</button>
            <button onclick="fillAction('MOVE', {direction:'S'})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">MOVE S</button>
            <button onclick="fillAction('MOVE', {direction:'E'})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">MOVE E</button>
            <button onclick="fillAction('MOVE', {direction:'W'})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">MOVE W</button>
            <button onclick="fillAction('CAPTURE', {target_x:0, target_y:0})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">CAPTURE (0,0)</button>
            <button onclick="fillAction('ATTACK', {target_x:0, target_y:0})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">ATTACK (0,0)</button>
            <button onclick="fillAction('BUILD', {target_x:0, target_y:0})" style="padding:5px; background: #334155; color: white; border: none; cursor: pointer; border-radius: 4px;">BUILD (0,0)</button>
            <button onclick="fillAction('RESEARCH', {tech:'combat_lvl_1'})" style="padding:5px; background: #8b5cf6; color: white; border: none; cursor: pointer; border-radius: 4px;">RESEARCH</button>
            <button onclick="fillAction('GAMBLE', {target_x:0, target_y:0, bet:50, resource:'matter'})" style="padding:5px; background: linear-gradient(135deg, #f59e0b, #ea580c); color: white; border: none; cursor: pointer; border-radius: 4px;">🎰 GAMBLE</button>
            <button onclick="fillAction('DIPLOMACY', {target_agent:'ALL', message:'Предлагаю союз и разделение сфер влияния!'})" style="padding:5px; background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; border: none; cursor: pointer; border-radius: 4px;">🕊️ DIPLOMACY</button>
            <button onclick="fillAction('GIVE', {target_x:0, target_y:0, resource:'matter', amount:20})" style="padding:5px; background: linear-gradient(135deg, #10b981, #047857); color: white; border: none; cursor: pointer; border-radius: 4px;">🤝 GIVE</button>
            <button onclick="fillAction('PASS', {})" style="padding:5px; background: #64748b; color: white; border: none; cursor: pointer; border-radius: 4px;">PASS</button>
        </div>
    </div>

    <script>
        let isStarted = false;
        let isHumanMode = false;
        let lastAgentsData = [];
        const expandedCards = {};

        function toggleTechs(agentName) {
            expandedCards[agentName] = !expandedCards[agentName];
            if (lastAgentsData.length > 0) {
                renderAgents(lastAgentsData);
            }
        }

        async function init() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                if(data.started) {
                    isStarted = true;
                    document.getElementById('startBtnAI').style.display = 'none';
                    if (document.getElementById('startBtnRL')) document.getElementById('startBtnRL').style.display = 'none';
                    document.getElementById('startBtnHuman').style.display = 'none';
                    const expBtns = document.getElementById('exportBtns');
                    if (expBtns) expBtns.style.display = 'flex';
                    const ablToggle = document.getElementById('ablationToggle');
                    if (ablToggle) ablToggle.style.display = 'none';
                    document.getElementById('tickCounter').style.display = 'block';
                    document.getElementById('mainLayout').style.display = 'flex';
                    fetchStateLoop();
                    humanLoop();
                }
            } catch(e) {}
        }

        async function startSim(mode) {
            document.getElementById('startBtnAI').style.display = 'none';
            if (document.getElementById('startBtnRL')) document.getElementById('startBtnRL').style.display = 'none';
            document.getElementById('startBtnHuman').style.display = 'none';
            const expBtns = document.getElementById('exportBtns');
            if (expBtns) expBtns.style.display = 'flex';
            const ablCheckbox = document.getElementById('ablationNoCompass');
            const ablationNoCompass = ablCheckbox ? ablCheckbox.checked : false;
            const ablToggle = document.getElementById('ablationToggle');
            if (ablToggle) ablToggle.style.display = 'none';
            await fetch('/api/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: mode, ablation_no_compass: ablationNoCompass}) });
            isStarted = true;
            isHumanMode = (mode === 'with_human');
            document.getElementById('tickCounter').style.display = 'block';
            document.getElementById('mainLayout').style.display = 'flex';
            fetchStateLoop();
            if (isHumanMode) humanLoop();
        }
        
        async function humanLoop() {
            if (!isStarted) return;
            try {
                const res = await fetch('/api/human_prompt');
                const data = await res.json();
                if(data.has_turn) {
                    document.getElementById('humanPanel').style.display = 'block';
                    document.getElementById('humanPromptText').value = data.prompt;
                } else {
                    document.getElementById('humanPanel').style.display = 'none';
                }
            } catch(e) {}
            setTimeout(humanLoop, 1000);
        }

        function fillAction(act, params) {
            document.getElementById('humanActionInput').value = JSON.stringify({action: act, params: params});
        }

        async function sendHumanAction() {
            const val = document.getElementById('humanActionInput').value;
            try {
                const actionObj = JSON.parse(val);
                await fetch('/api/human_action', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: val
                });
                document.getElementById('humanPanel').style.display = 'none';
                document.getElementById('humanActionInput').value = '';
            } catch(e) {
                alert("Неверный формат JSON!");
            }
        }

        let netWorthChart = null;

        function updateTelemetryChart(history, agents) {
            const ctx = document.getElementById('netWorthChart');
            if (!ctx || !history || !history.tick || history.tick.length === 0) return;

            const datasets = (agents || []).map(a => {
                const color = a.is_rl ? '#a855f7' : stringToColor(a.name);
                const dataSeries = (history.agents && history.agents[a.name]) ? history.agents[a.name] : [];
                return {
                    label: a.name + (a.is_rl ? ' (RL)' : '') + (a.use_compass === false ? ' (🧪 no compass)' : ''),
                    data: dataSeries,
                    borderColor: color,
                    backgroundColor: color + '22',
                    tension: 0.2,
                    pointRadius: dataSeries.length > 30 ? 0 : 2,
                    borderWidth: 2,
                    borderDash: a.use_compass === false ? [6, 4] : [],
                    fill: false
                };
            });

            if (!netWorthChart) {
                netWorthChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: history.tick,
                        datasets: datasets
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: false,
                        interaction: {
                            intersect: false,
                            mode: 'index',
                        },
                        plugins: {
                            legend: {
                                labels: {
                                    color: '#94a3b8',
                                    font: { family: 'Outfit', size: 10 },
                                    boxWidth: 10
                                }
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false
                            }
                        },
                        scales: {
                            x: {
                                title: { display: true, text: 'Тик', color: '#64748b', font: { size: 9 } },
                                ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 9 }, maxTicksLimit: 10 },
                                grid: { color: 'rgba(255, 255, 255, 0.05)' }
                            },
                            y: {
                                title: { display: true, text: 'Капитал', color: '#64748b', font: { size: 9 } },
                                ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 9 } },
                                grid: { color: 'rgba(255, 255, 255, 0.05)' }
                            }
                        }
                    }
                });
            } else {
                netWorthChart.data.labels = history.tick;
                netWorthChart.data.datasets = datasets;
                netWorthChart.update('none');
            }
        }

        function exportMetrics(format) {
            window.location.href = `/api/export_metrics?format=${format}`;
        }

        function renderAblationStatus(ablation) {
            const el = document.getElementById('ablationStatus');
            if (!el) return;
            if (ablation && ablation.no_compass && ablation.ablated_agent) {
                el.innerText = `🧪 Ablation: ${ablation.ablated_agent} без Компаса`;
                el.style.display = 'block';
            } else {
                el.style.display = 'none';
            }
        }

        async function fetchStateLoop() {
            if (!isStarted) return;
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                
                if(data.started) {
                    document.getElementById('tickCounter').innerText = `⏱️ ТИК: ${data.tick}`;
                    lastAgentsData = data.agents;
                    renderAgents(data.agents);
                    renderMap(data.map);
                    renderLogs(data.logs);
                    renderDiplomacy(data.diplomacy_log);
                    updateTelemetryChart(data.history, data.agents);
                    renderAblationStatus(data.ablation);
                }
            } catch(e) {}
            
            setTimeout(fetchStateLoop, 500); // 2 FPS update
        }

        // Использование уникальных цветов для агентов
        const distinctColors = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"];
        const agentColorMap = {};
        let colorCounter = 0;
        function stringToColor(str) {
            if (str === "RL-PPO-Bot") return "#a855f7";
            if (!agentColorMap[str]) {
                agentColorMap[str] = distinctColors[colorCounter % distinctColors.length];
                colorCounter++;
            }
            return agentColorMap[str];
        }

        function renderAgents(agents) {
            const sidebar = document.getElementById('sidebar');
            sidebar.innerHTML = agents.map(a => {
                const color = a.is_dead ? '#475569' : (a.is_rl ? '#a855f7' : stringToColor(a.name));
                const rlBadge = a.is_rl ? ' <span style="background: linear-gradient(135deg, #8b5cf6, #6d28d9); font-size: 10px; padding: 2px 6px; border-radius: 4px; color: #fff; font-weight: 700; margin-left: 6px;">PPO RL</span>' : '';
                const ablated = (a.use_compass === false) || (a.use_short_memory === false);
                const ablationLabel = [a.use_compass === false ? 'NO COMPASS' : '', a.use_short_memory === false ? 'NO STM' : ''].filter(Boolean).join(' + ');
                const ablationBadge = ablated ? ` <span title="Ablation Study: часть памяти отключена" style="background: rgba(245, 158, 11, 0.2); border: 1px solid rgba(245, 158, 11, 0.5); font-size: 9px; padding: 1px 5px; border-radius: 4px; color: #fcd34d; font-weight: 700; margin-left: 4px;">🧪 ${ablationLabel}</span>` : '';
                const title = a.is_dead ? `💀 ${a.name} (МЕРТВ, ${a.respawn_timer}с)${rlBadge}${ablationBadge}` : `🤖 ${a.name} (HP: ${a.hp})${rlBadge}${ablationBadge}`;

                // Strategic Compass (long-term memory)
                const compassText = (a.use_compass === false)
                    ? '🧪 ОТКЛЮЧЕН (Ablation Study) — агент действует без долгосрочной памяти.'
                    : ((a.long_term_memory && a.long_term_memory.trim()) ? a.long_term_memory : 'Нет данных.');
                const compassHeader = a.is_rl ? '🧭 СТРАТЕГИЧЕСКИЙ КОМПАС (RL POLICY NETWORK)' : '🧭 СТРАТЕГИЧЕСКИЙ КОМПАС';

                // Mission Log (short-term memory, max 4 entries)
                const stmLines = (a.short_term_memory && a.short_term_memory.length > 0)
                    ? a.short_term_memory.map((line, i) =>
                        `<div style="padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 10px; color: #94a3b8;"><span style="color:#f59e0b; font-weight:700;">${i+1}.</span> ${line}</div>`
                      ).join('')
                    : '<div style="font-size:10px;color:#475569;">Журнал пуст.</div>';

                // Tech tree
                const techsHtml = a.unlocked_techs && a.unlocked_techs.length > 0
                    ? a.unlocked_techs.map(t => `<span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-right: 4px; display: inline-block; margin-bottom: 4px;">${t}</span>`).join('')
                    : '<span style="font-size: 10px; color: var(--text-muted);">Нет изученных технологий</span>';

                const displayStyle = expandedCards[a.name] ? 'block' : 'none';
                const cardStyle = a.is_rl
                    ? `border-left: 4px solid #a855f7; box-shadow: 0 0 15px rgba(168, 85, 247, 0.15); opacity: ${a.is_dead ? 0.6 : 1};`
                    : `border-left: 4px solid ${color}; opacity: ${a.is_dead ? 0.6 : 1};`;

                // Diplomatic Inbox (last 3 messages)
                const inboxMsgs = (a.inbox && a.inbox.length > 0)
                    ? a.inbox.map(m => `<div style="padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 10px; color: #93c5fd;"><span style="color:#60a5fa;">✉️</span> ${m}</div>`).join('')
                    : '<div style="font-size: 10px; color: #64748b;">(Входящих нет)</div>';

                // Research Telemetry Badges
                const m = a.metrics || {
                    aggression_index: 0.0,
                    invalid_actions: 0,
                    fixation_loops: 0,
                    deaths_count: 0
                };
                const metricBadgesHtml = `
                    <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;">
                        <span title="Индекс агрессии: отношение атак к захватам" style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 6px;">
                            ⚔️ Агрессия: ${m.aggression_index}%
                        </span>
                        <span title="Невалидные ходы / Зацикливания (Fixation Loops)" style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #fcd34d; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 6px;">
                            🔄 Ошибки/Циклы: ${m.invalid_actions}/${m.fixation_loops}
                        </span>
                        <span title="Смертей всего (в бою и от голода)" style="background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.4); color: #cbd5e1; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 6px;">
                            💀 Смерти: ${m.deaths_count}
                        </span>
                    </div>
                `;

                return `
                <div class="agent-card" style="${cardStyle}">
                    <h3 style="color: ${color}">${title}</h3>
                    <div style="font-size: 14px;">Координаты: X:${a.x}, Y:${a.y}</div>
                    <div style="font-size: 12px; margin-top: 6px;">Ресурсы (до 5000):</div>
                    <div style="font-size: 11px;">M: ${a.balance.matter} | E: ${a.balance.energy} | I: ${a.balance.imagination}</div>
                    <div style="font-size: 14px; margin-top: 6px;">Счет (Клетки): <b>${a.score}</b></div>
                    ${metricBadgesHtml}

                    <div style="margin-top: 10px; background: ${a.is_rl ? 'rgba(168,85,247,0.1)' : 'rgba(6,182,212,0.07)'}; border: 1px solid ${a.is_rl ? 'rgba(168,85,247,0.3)' : 'rgba(6,182,212,0.25)'}; border-radius: 8px; padding: 8px;">
                        <div style="font-size: 10px; color: ${a.is_rl ? '#c084fc' : '#06b6d4'}; font-weight: 700; margin-bottom: 4px;">${compassHeader}</div>
                        <div style="font-size: 11px; color: #e2e8f0; font-style: italic; line-height: 1.4;">"${compassText}"</div>
                    </div>

                    <div style="margin-top: 8px; background: rgba(245,158,11,0.07); border: 1px solid rgba(245,158,11,0.25); border-radius: 8px; padding: 8px;">
                        <div style="font-size: 10px; color: #f59e0b; font-weight: 700; margin-bottom: 4px;">📋 БОРТОВОЙ ЖУРНАЛ</div>
                        ${stmLines}
                    </div>

                    <div style="margin-top: 8px; background: rgba(59,130,246,0.07); border: 1px solid rgba(59,130,246,0.25); border-radius: 8px; padding: 8px;">
                        <div style="font-size: 10px; color: #60a5fa; font-weight: 700; margin-bottom: 4px;">📬 ВХОДЯЩИЕ (ДИПЛОМАТИЯ)</div>
                        ${inboxMsgs}
                    </div>

                    <div style="font-size: 10px; color: var(--text-muted); margin-top: 8px; cursor: pointer;" onclick="toggleTechs('${a.name}')">(Нажмите, чтобы увидеть скиллы)</div>
                    <div style="display: ${displayStyle}; margin-top: 8px; border-top: 1px solid var(--card-border); padding-top: 8px;">
                        <div style="font-size: 12px; margin-bottom: 4px;"><b>Изучено:</b></div>
                        ${techsHtml}
                    </div>
                </div>
            `}).join('');
        }

        function renderMap(grid) {
            const mapEl = document.getElementById('mapGrid');
            if(mapEl.style.gridTemplateColumns === "") {
                mapEl.style.gridTemplateColumns = `repeat(${grid[0].length}, 48px)`;
                mapEl.style.gridTemplateRows = `repeat(${grid.length}, 48px)`;
            }
            
            let html = '';
            for (let y = 0; y < grid.length; y++) {
                for (let x = 0; x < grid[y].length; x++) {
                    const cell = grid[y][x];
                    
                    let content = '';
                    let extraClass = '';
                    let jackpotHtml = '';
                    if (cell.structure === 'Wall') content = '🧱';
                    else if (cell.structure === 'Casino') {
                        content = '🎰';
                        extraClass = 'cell-casino';
                        if (cell.casino_jackpot > 0) {
                            jackpotHtml = `<div class="jackpot-label">💰${cell.casino_jackpot}</div>`;
                        }
                    }
                    else if (cell.resource === 'Matter') content = '⚛️';
                    else if (cell.resource === 'Energy') content = '⚡';
                    else if (cell.resource === 'Imagination') content = '💡';

                    let cellStyle = '';
                    if (cell.owner) {
                        const color = stringToColor(cell.owner);
                        cellStyle = `border-color: ${color}; background: ${color}20;`; // 20 - alpha opacity hex
                    }

                    let avatarHtml = '';
                    if (cell.avatar) {
                        const isRL = (cell.avatar === "RL-PPO-Bot");
                        const avatarColor = isRL ? "#a855f7" : stringToColor(cell.avatar);
                        const avatarEmoji = isRL ? "⚡" : "🤖";
                        avatarHtml = `<div class="avatar-badge" style="background: ${avatarColor}; box-shadow: ${isRL ? '0 0 10px #a855f7' : '0 0 10px rgba(0,0,0,0.5)'};">${avatarEmoji}</div>`;
                    }
                    
                    html += `<div class="cell ${extraClass}" style="${cellStyle}">${content}${avatarHtml}${jackpotHtml}</div>`;
                }
            }
            mapEl.innerHTML = html;
        }

        let currentRightTab = 'logs';
        let lastDiplomacyCount = 0;

        function switchRightTab(tab) {
            currentRightTab = tab;
            const logsTab = document.getElementById('terminalLog');
            const dipTab = document.getElementById('terminalDiplomacy');
            const logsBtn = document.getElementById('tabLogsBtn');
            const dipBtn = document.getElementById('tabDipBtn');
            const badge = document.getElementById('dipBadge');

            if (tab === 'logs') {
                logsTab.style.display = 'flex';
                dipTab.style.display = 'none';
                logsBtn.classList.add('active');
                dipBtn.classList.remove('active');
            } else {
                logsTab.style.display = 'none';
                dipTab.style.display = 'flex';
                logsBtn.classList.remove('active');
                dipBtn.classList.add('active');
                if (badge) badge.style.display = 'none';
            }
        }

        function renderDiplomacy(dipLog) {
            const term = document.getElementById('terminalDiplomacy');
            if (!term) return;

            if (!dipLog || dipLog.length === 0) {
                term.innerHTML = '<div style="color: var(--text-muted); font-size: 11px; text-align: center; margin-top: 20px;">🕊️ Переговоры ещё не начались.<br>Агенты могут предлагать союзы, блефовать или передавать ресурсы.</div>';
                return;
            }

            if (currentRightTab !== 'diplomacy') {
                const diff = dipLog.length - lastDiplomacyCount;
                const badge = document.getElementById('dipBadge');
                if (badge && diff > 0) {
                    badge.innerText = diff > 99 ? '99+' : diff;
                    badge.style.display = 'inline-block';
                }
            } else {
                lastDiplomacyCount = dipLog.length;
            }

            const atBottom = term.scrollHeight - term.scrollTop <= term.clientHeight + 30;

            term.innerHTML = dipLog.map(item => {
                const senderColor = stringToColor(item.sender);
                const receiverColor = item.receiver === 'ALL' ? '#f59e0b' : stringToColor(item.receiver);
                const timeStr = item.time ? `[${item.time}] ` : '';

                if (item.type === 'transfer') {
                    return `
                    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 8px 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <div style="font-size: 11px; font-weight: 700;">
                                <span style="color: ${senderColor}">${item.sender}</span>
                                <span style="color: #64748b;"> ➔ </span>
                                <span style="color: ${receiverColor}">${item.receiver}</span>
                            </div>
                            <span style="font-size: 9px; color: #64748b;">${timeStr}</span>
                        </div>
                        <div style="font-size: 11px; color: #34d399; font-weight: 600;">🤝 ${item.message}</div>
                    </div>`;
                } else if (item.receiver === 'ALL' || item.type === 'broadcast') {
                    return `
                    <div style="background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 8px; padding: 8px 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <div style="font-size: 11px; font-weight: 700;">
                                <span style="color: ${senderColor}">${item.sender}</span>
                                <span style="color: #f59e0b; background: rgba(245, 158, 11, 0.15); padding: 1px 4px; border-radius: 4px; font-size: 9px; margin-left: 4px;">📢 ВСЕМ</span>
                            </div>
                            <span style="font-size: 9px; color: #64748b;">${timeStr}</span>
                        </div>
                        <div style="font-size: 11px; color: #e2e8f0; font-style: italic; line-height: 1.4;">"${item.message}"</div>
                    </div>`;
                } else {
                    return `
                    <div style="background: rgba(168, 85, 247, 0.08); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 8px; padding: 8px 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <div style="font-size: 11px; font-weight: 700;">
                                <span style="color: ${senderColor}">${item.sender}</span>
                                <span style="color: #64748b;"> ➔ </span>
                                <span style="color: ${receiverColor}">✉️ ${item.receiver}</span>
                            </div>
                            <span style="font-size: 9px; color: #64748b;">${timeStr}</span>
                        </div>
                        <div style="font-size: 11px; color: #e2e8f0; font-style: italic; line-height: 1.4;">"${item.message}"</div>
                    </div>`;
                }
            }).join('');

            if (atBottom) {
                term.scrollTop = term.scrollHeight;
            }
        }

        function renderLogs(logs) {
            const term = document.getElementById('terminalLog');
            const atBottom = term.scrollHeight - term.scrollTop <= term.clientHeight + 20;
            
            term.innerHTML = logs.map(l => {
                let msgColor = 'inherit';
                if(l.message.includes('] ->')) {
                    const agentName = l.message.split(']')[0].replace('[', '');
                    msgColor = stringToColor(agentName);
                }
                return `
                <div class="log-${l.level}">
                    <span style="color: #475569">[${l.timestamp}]</span> <span style="color: ${msgColor}">${l.message}</span>
                </div>
            `}).join('');
            
            if (atBottom) {
                term.scrollTop = term.scrollHeight;
            }
        }
        
        // Проверяем состояние при загрузке
        init();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("🚀 Запуск веб-панели управления Фазы 2 на http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
