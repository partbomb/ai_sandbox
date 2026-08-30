import json
import logging
import random
import asyncio
from typing import List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types

# Настройка простого логгера для world.py
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("WorldMap")

# --- Базовые структуры карты ---

class Position(BaseModel):
    x: int
    y: int

class Cell(BaseModel):
    pos: Position
    owner_id: Optional[str] = None
    resource_type: Optional[str] = None  # 'Matter', 'Energy', 'Imagination'
    mine_level: int = 0
    mine_hp: int = 0
    structure: Optional[str] = None      # 'Wall'
    wall_hp: int = 0
    loot: dict = {}  # {'matter': x, 'energy': y, 'imagination': z}

class MapCore:
    def __init__(self, width: int = 5, height: int = 5):
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [
            [Cell(pos=Position(x=x, y=y)) for y in range(height)]
            for x in range(width)
        ]
        self.lock = asyncio.Lock()  # Блокировка для асинхронного доступа к карте

    def spawn_mines(self):
        resources = ['Matter', 'Matter', 'Matter', 'Energy', 'Energy', 'Energy', 'Imagination', 'Imagination', 'Imagination']
        cells = [cell for row in self.grid for cell in row]
        random.shuffle(cells)
        for i, res in enumerate(resources):
            cells[i].resource_type = res
            cells[i].mine_level = 1
            cells[i].mine_hp = 50

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[x][y]
        return None

    def get_map_state_json(self, vision_x: Optional[int] = None, vision_y: Optional[int] = None, radius: int = 2) -> str:
        state = []
        for y in range(self.height):
            for x in range(self.width):
                c = self.grid[x][y]
                if vision_x is not None and vision_y is not None:
                    dist = abs(c.pos.x - vision_x) + abs(c.pos.y - vision_y)
                    if dist > radius:
                        continue
                
                cell_data = {
                    "x": c.pos.x, "y": c.pos.y,
                    "owner": c.owner_id,
                    "resource": c.resource_type,
                    "level": c.mine_level,
                    "mine_hp": c.mine_hp,
                    "structure": c.structure,
                    "wall_hp": c.wall_hp
                }
                if any(v > 0 for v in c.loot.values()):
                    cell_data["loot"] = c.loot
                state.append(cell_data)
        return json.dumps(state)

    def print_map(self, avatars: List['Stage2AI']):
        print("\n" + "=" * (self.width * 3 + 2))
        for y in range(self.height):
            row_str = "|"
            for x in range(self.width):
                cell = self.grid[x][y]
                avatar_here = next((a for a in avatars if a.position.x == x and a.position.y == y), None)
                
                if avatar_here:
                    if "Alpha" in avatar_here.name: row_str += "🔴 "
                    else: row_str += "🔵 "
                elif cell.structure == 'Wall':
                    row_str += "🧱 "
                elif cell.owner_id is not None:
                    if "Alpha" in cell.owner_id: row_str += "🟥 "
                    else: row_str += "🟦 "
                elif cell.resource_type == 'Matter': row_str += "⚛️  "
                elif cell.resource_type == 'Energy': row_str += "⚡ "
                elif cell.resource_type == 'Imagination': row_str += "💡 "
                else: row_str += "⬛ "
            row_str += "|"
            print(row_str)
        print("=" * (self.width * 3 + 2) + "\n")


# --- Расширение для Агента (Единственный Аватар) ---

class Stage2AI: 
    def __init__(self, name: str, api_key: str, model: str, start_pos: Position, init_income: dict, is_human: bool = False):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.position = start_pos
        self.base_position = Position(x=start_pos.x, y=start_pos.y)
        self.score = 0
        self.is_dead = False
        self.hp = 100
        self.respawn_timer = 0
        self.balance = {"matter": 50, "energy": 50, "imagination": 50}
        self.income = init_income
        self.memory = []  # legacy, kept for compatibility
        self.unlocked_techs = []

        # --- Dual Memory System ---
        # Short-term: rolling log of last 4 actions ("Бортовой журнал")
        self.short_term_memory: list[str] = []
        # Long-term: strategic compass, agent rewrites each turn ("Стратегический компас")
        self.long_term_memory: str = "Начало. Изучить карту и захватить ближайшую шахту."

        self.is_human = is_human
        self.human_action = None
        self.human_prompt = ""
        self.human_ready = asyncio.Event()

        self.client = genai.Client(api_key=self.api_key) if self.api_key and not self.api_key.startswith("sk-") and "test" not in self.api_key.lower() and not self.is_human else None

    def generate_prompt(self, map_core: MapCore) -> str:
        surroundings = map_core.get_map_state_json()
        
        TECH_TREE = {
            "combat_lvl_1": {"cost": 150, "parent": None},
            "combat_lvl_2": {"cost": 500, "parent": "combat_lvl_1"},
            "combat_lvl_3": {"cost": 1500, "parent": "combat_lvl_2"},
            "economy_lvl_1": {"cost": 150, "parent": None},
            "economy_lvl_2": {"cost": 500, "parent": "economy_lvl_1"},
            "economy_lvl_3": {"cost": 1500, "parent": "economy_lvl_2"},
            "logistics_lvl_1": {"cost": 150, "parent": None},
            "logistics_lvl_2": {"cost": 500, "parent": "logistics_lvl_1"},
            "logistics_lvl_3": {"cost": 1500, "parent": "logistics_lvl_2"}
        }
        
        available_techs = []
        for tech, data in TECH_TREE.items():
            if tech not in self.unlocked_techs:
                if data["parent"] is None or data["parent"] in self.unlocked_techs:
                    available_techs.append({"name": tech, "cost": data["cost"]})
        
        tech_status = f'"unlocked_techs": {json.dumps(self.unlocked_techs)},\n"available_techs": {json.dumps(available_techs)}'
        
        move_cost = 2 if "logistics_lvl_1" in self.unlocked_techs else 5
        attack_dmg = 40 if "combat_lvl_1" in self.unlocked_techs else 25
        build_cost = 14 if "economy_lvl_1" in self.unlocked_techs else 20
        
        actions_str = (
            f"1. MOVE: {{\"action\": \"MOVE\", \"params\": {{\"direction\": \"N\"}}}} (N, S, E, W). Cost: {move_cost} Energy.\n"
            f"2. ATTACK: {{\"action\": \"ATTACK\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}. Cost: 5 Energy. DMG: {attack_dmg}.\n"
            f"3. BUILD: {{\"action\": \"BUILD\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}. Cost: {build_cost} Matter. Builds Wall.\n"
            f"4. CAPTURE: {{\"action\": \"CAPTURE\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}. Cost: 10 Imagination. Captures Mine.\n"
            f"5. RESEARCH: {{\"action\": \"RESEARCH\", \"params\": {{\"tech\": \"tech_name\"}}}}. Spends Imagination to unlock tech.\n"
        )
        if "economy_lvl_3" in self.unlocked_techs:
            actions_str += f"6. BUILD_MINE: {{\"action\": \"BUILD_MINE\", \"params\": {{\"target_x\": X, \"target_y\": Y, \"type\": \"Matter\"}}}} (type: Matter/Energy/Imagination). Cost: 50 Matter, 50 Energy. Creates mine on empty cell.\n"
        if "logistics_lvl_3" in self.unlocked_techs:
            actions_str += f"7. JUMP: {{\"action\": \"JUMP\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}. Cost: 50 Energy. Teleports to any cell.\n"
        actions_str += "8. PASS: {\"action\": \"PASS\"}\n"

        # --- Build memory sections ---
        # Short-term: last 4 actions (бортовой журнал)
        stm_lines = self.short_term_memory if self.short_term_memory else ["Нет записей."]
        stm_text = "\n".join(f"  {i+1}. {line}" for i, line in enumerate(stm_lines))

        prompt = (
            f"=== ПАПКА С ДЕЛОМ (твой текущий контекст) ===\n\n"
            f"[1] СТРАТЕГИЧЕСКИЙ КОМПАС (Долгосрочная цель):\n"
            f"  '{self.long_term_memory}'\n\n"
            f"[2] БОРТОВОЙ ЖУРНАЛ (Краткосрочная память, последние {len(stm_lines)} действий):\n"
            f"{stm_text}\n\n"
            f"[3] ТВОИ ГЛАЗА (Текущее состояние):\n"
            f"  Имя: {self.name} | Позиция: X:{self.position.x}, Y:{self.position.y} | HP: {self.hp}/100\n"
            f"  Баланс: Matter={self.balance['matter']}, Energy={self.balance['energy']}, Imagination={self.balance['imagination']}\n"
            f"  Карта (10x10, X:0-9, Y:0-9):\n{surroundings}\n\n"
            f"TECH STATUS:\n{tech_status}\n\n"
            f"WIN CONDITIONS:\n"
            f"  1. Singularity: 5000 of all resources.\n"
            f"  2. Monopoly: Capture 80% of all resource mines.\n"
            f"  3. Battle Royale: Kill all other agents.\n\n"
            f"RULES & MECHANICS:\n"
            f"- SKILL TREE: Research techs using Imagination.\n"
            f"- MOVE: Navigate the map. Blocked by Walls or Enemies. Loot is auto-picked up.\n"
            f"- ATTACK: Deals damage. Targets: Enemies, Walls, or Mines.\n"
            f"- BUILD: Builds a Wall on an adjacent cell.\n"
            f"- CAPTURE: Reprograms a mine. Requires cell to be clear of enemies/walls.\n"
            f"MAP BOUNDARIES: DO NOT move outside 0-9! If at Y=0 cannot move N, Y=9 cannot move S, X=0 cannot move W, X=9 cannot move E.\n\n"
            f"Available actions (return strictly JSON):\n"
            f"{actions_str}\n"
            f"=== ИНСТРУКЦИЯ ПО ОТВЕТУ ===\n"
            f"Прочитай Компас -> Журнал -> Карту. Подумай: изменилась ли ситуация?\n"
            f"Верни JSON с полями:\n"
            f"  'thought'      — твой внутренний монолог (строка)\n"
            f"  'action'       — выбранное действие\n"
            f"  'params'       — параметры действия\n"
            f"  'new_compass'  — обновлённый Компас (строка, 1-2 предложения). "
            f"Если план не изменился — повтори текущий. Если ситуация изменилась — перепиши!\n"
        )
        return prompt

    async def get_action_from_llm(self, map_core: MapCore) -> dict:
        prompt = self.generate_prompt(map_core)
        
        if getattr(self, 'is_human', False):
            self.human_prompt = prompt
            self.human_action = None
            self.human_ready.clear()
            try:
                # Даем человеку 60 секунд на ход
                await asyncio.wait_for(self.human_ready.wait(), timeout=60.0)
                if self.human_action:
                    return self.human_action
                return {"action": "PASS"}
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] Человек не успел сходить. Пропуск хода.")
                return {"action": "PASS"}

        if not self.api_key or self.api_key.startswith("sk-") or "test" in self.api_key.lower():
            await asyncio.sleep(0.5) 
            return {"action": "PASS"}

        try:
            if not self.client:
                await asyncio.sleep(0.5)
                return {"action": "PASS"}
            
            def _call_api():
                return self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            
            # Добавлен жесткий таймаут 7 секунд. Если API (Google SDK) начинает 
            # бесконечно ретраить из-за Rate Limit 15 RPM, мы прерываем ожидание,
            # чтобы агент не "завис" навсегда.
            response = await asyncio.wait_for(asyncio.to_thread(_call_api), timeout=7.0)
            return json.loads(response.text)
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] LLM Timeout (Rate Limit/Slow response). Пропускаем ход.")
            return {"action": "PASS"}
        except Exception as e:
            logger.error(f"[{self.name}] LLM Error: {e}")
            await asyncio.sleep(2) 
            return {"action": "PASS"}


# --- Валидатор физических действий ---

class ArbitorPhysical:
    def is_adjacent(self, pos1: Position, pos2: Position) -> bool:
        dx = abs(pos1.x - pos2.x)
        dy = abs(pos1.y - pos2.y)
        return (dx <= 1 and dy <= 1)

    async def execute_action(self, avatar: Stage2AI, action_data: dict, map_core: MapCore, all_agents: List[Stage2AI]) -> str:
        async with map_core.lock:
            if avatar.is_dead:
                return "Вы мертвы и не можете действовать."
                
            if not isinstance(action_data, dict):
                action_data = {}
            action = action_data.get("action", "PASS")
            params = action_data.get("params", {})
            
            if action == "RESEARCH":
                tech = params.get("tech")
                TECH_TREE = {
                    "combat_lvl_1": {"cost": 150, "parent": None}, "combat_lvl_2": {"cost": 500, "parent": "combat_lvl_1"}, "combat_lvl_3": {"cost": 1500, "parent": "combat_lvl_2"},
                    "economy_lvl_1": {"cost": 150, "parent": None}, "economy_lvl_2": {"cost": 500, "parent": "economy_lvl_1"}, "economy_lvl_3": {"cost": 1500, "parent": "economy_lvl_2"},
                    "logistics_lvl_1": {"cost": 150, "parent": None}, "logistics_lvl_2": {"cost": 500, "parent": "logistics_lvl_1"}, "logistics_lvl_3": {"cost": 1500, "parent": "logistics_lvl_2"}
                }
                if tech not in TECH_TREE:
                    return f"Технология {tech} не существует."
                if tech in avatar.unlocked_techs:
                    return f"Технология {tech} уже изучена."
                req_parent = TECH_TREE[tech]["parent"]
                if req_parent and req_parent not in avatar.unlocked_techs:
                    return f"Сначала нужно изучить {req_parent}."
                cost = TECH_TREE[tech]["cost"]
                if avatar.balance["imagination"] < cost:
                    return f"Недостаточно Воображения (нужно {cost})."
                avatar.balance["imagination"] -= cost
                avatar.unlocked_techs.append(tech)
                return f"УСПЕШНО ИЗУЧЕНО: {tech}!"

            elif action == "MOVE":
                move_cost = 2 if "logistics_lvl_1" in avatar.unlocked_techs else 5
                if avatar.balance["energy"] < move_cost:
                    return f"Недостаточно Энергии (нужно {move_cost}) для перемещения."
                
                direction = params.get("direction")
                dx, dy = 0, 0
                if direction == 'N': dy = -1
                elif direction == 'S': dy = 1
                elif direction == 'E': dx = 1
                elif direction == 'W': dx = -1
                
                new_x, new_y = avatar.position.x + dx, avatar.position.y + dy
                target_cell = map_core.get_cell(new_x, new_y)
                if target_cell and target_cell.structure != 'Wall':
                    enemy_here = next((a for a in all_agents if a.position.x == new_x and a.position.y == new_y and a.name != avatar.name and not a.is_dead), None)
                    if enemy_here:
                        return f"Движение заблокировано врагом {enemy_here.name}."
                        
                    avatar.balance["energy"] -= move_cost
                    avatar.position = Position(x=new_x, y=new_y)
                    pickup_msg = ""
                    loot_mult = 1.5 if "logistics_lvl_2" in avatar.unlocked_techs else 1.0
                    for res in ['matter', 'energy', 'imagination']:
                        if target_cell.loot.get(res, 0) > 0:
                            amt = int(target_cell.loot[res] * loot_mult)
                            avatar.balance[res] += amt
                            target_cell.loot[res] = 0
                            pickup_msg += f" Подобрано {amt} {res}."
                    return f"Переместился на {direction} ({new_x}, {new_y})." + pickup_msg
                return "Стена или край карты."

            elif action == "JUMP":
                if "logistics_lvl_3" not in avatar.unlocked_techs:
                    return "Команда JUMP недоступна (нужен logistics_lvl_3)."
                if avatar.balance["energy"] < 50:
                    return "Недостаточно Энергии (нужно 50) для прыжка."
                
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell or target_cell.structure == 'Wall':
                    return "Нельзя прыгнуть сюда (стена или край карты)."
                enemy_here = next((a for a in all_agents if a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead), None)
                if enemy_here:
                    return "Нельзя прыгнуть: клетка занята врагом."
                
                avatar.balance["energy"] -= 50
                avatar.position = Position(x=tx, y=ty)
                return f"ТЕЛЕПОРТАЦИЯ на ({tx}, {ty}) прошла успешно!"

            elif action == "ATTACK":
                if avatar.balance["energy"] < 5:
                    return "Недостаточно Энергии (Нужно 5) для атаки."
                avatar.balance["energy"] -= 5
                
                dmg = 40 if "combat_lvl_1" in avatar.unlocked_techs else 25
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Цель вне зоны досягаемости."
                    
                target_cell = map_core.get_cell(tx, ty)
                enemy = next((a for a in all_agents if a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead), None)
                
                if enemy:
                    enemy.hp -= dmg
                    if enemy.hp <= 0:
                        enemy.is_dead = True
                        enemy.respawn_timer = 5
                        for res in ['matter', 'energy', 'imagination']:
                            target_cell.loot[res] = target_cell.loot.get(res, 0) + enemy.balance[res]
                            enemy.balance[res] = 0
                        return f"УСПЕШНО АТАКОВАЛ И УБИЛ {enemy.name} на ({tx}, {ty})!"
                    return f"Нанес {dmg} урона {enemy.name}. Осталось HP: {enemy.hp}."
                elif target_cell and target_cell.structure == 'Wall':
                    target_cell.wall_hp -= dmg
                    avatar.balance["matter"] += 2
                    if target_cell.wall_hp <= 0:
                        target_cell.structure = None
                        return f"Стена разрушена! Получено 2 Материи."
                    return f"Удар по стене. Осталось HP: {target_cell.wall_hp}."
                elif target_cell and target_cell.resource_type:
                    target_cell.mine_hp -= dmg
                    avatar.balance["matter"] += 5
                    if target_cell.mine_hp <= 0:
                        target_cell.resource_type = None
                        target_cell.owner_id = None
                        if "combat_lvl_3" in avatar.unlocked_techs:
                            avatar.balance["matter"] += 50
                            avatar.balance["energy"] += 50
                            avatar.balance["imagination"] += 50
                            return "Шахта полностью разрушена! ВАМПИРИЗМ: получено по 50 всех ресурсов."
                        return "Шахта полностью разрушена! Получено 5 Материи."
                    return f"Удар по шахте. Осталось HP: {target_cell.mine_hp}."
                else:
                    return f"На ({tx}, {ty}) нет подходящей цели для атаки."
                    
            elif action == "BUILD":
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                    return "Цель вне зоны досягаемости."
                
                build_cost = 14 if "economy_lvl_1" in avatar.unlocked_techs else 20
                if avatar.balance["matter"] < build_cost:
                    return f"Недостаточно Материи (нужно {build_cost}) для постройки стены."
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell or target_cell.structure == 'Wall':
                    return "Здесь уже есть постройка или край карты."
                
                enemy_here = any(a.position.x == tx and a.position.y == ty and not a.is_dead for a in all_agents)
                if enemy_here: return "Невозможно строить: на клетке кто-то стоит."
                
                avatar.balance["matter"] -= build_cost
                target_cell.structure = 'Wall'
                target_cell.wall_hp = 250 if "combat_lvl_2" in avatar.unlocked_techs else 100
                return f"Стена успешно построена (HP: {target_cell.wall_hp})."

            elif action == "BUILD_MINE":
                if "economy_lvl_3" not in avatar.unlocked_techs:
                    return "Команда BUILD_MINE недоступна (нужен economy_lvl_3)."
                if avatar.balance["matter"] < 50 or avatar.balance["energy"] < 50:
                    return "Недостаточно ресурсов (нужно 50 Matter, 50 Energy)."
                    
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                mine_type = params.get("type", "Matter")
                if mine_type not in ["Matter", "Energy", "Imagination"]:
                    mine_type = "Matter"
                    
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Цель вне зоны досягаемости."
                
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell or target_cell.structure or target_cell.resource_type:
                    return "Клетка занята стеной, шахтой или край карты."
                    
                avatar.balance["matter"] -= 50
                avatar.balance["energy"] -= 50
                
                target_cell.resource_type = mine_type
                target_cell.mine_level = 1
                target_cell.mine_hp = 50
                target_cell.owner_id = avatar.name
                return f"Шахта ({mine_type}) успешно создана на ({tx}, {ty})!"

            elif action == "CAPTURE":
                if avatar.balance["imagination"] < 10:
                    return "Недостаточно Воображения (нужно 10) для захвата."
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Слишком далеко для захвата."
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell: return "Край карты."
                
                enemy_here = any(a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead for a in all_agents)
                if enemy_here: return "Невозможно захватить: на клетке враг!"
                if target_cell.structure == 'Wall': return "Невозможно захватить: мешает стена!"
                
                if target_cell.resource_type:
                    avatar.balance["imagination"] -= 10
                    target_cell.owner_id = avatar.name
                    return f"Шахта на ({tx}, {ty}) перепрограммирована и захвачена."
                return "Здесь нет шахты для захвата."

            return f"Действие {action} обработано."


# --- АСИНХРОННЫЙ ЦИКЛ (Real-time Simulation) ---

async def map_render_loop(map_core: MapCore, agents: List[Stage2AI]):
    """Глобальный цикл отрисовки и течения времени."""
    tick = 0
    while True:
        tick += 1
        async with map_core.lock:
            print(f"\n--- [ ГЛОБАЛЬНЫЙ ТИК {tick} ] ---")
            map_core.print_map(agents)
            
            # Подсчет очков
            for agent in agents:
                agent.score = sum(1 for row in map_core.grid for cell in row if cell.owner_id == agent.name)
            scores = " | ".join([f"{a.name}: {a.score} очков" for a in agents])
            logger.info(f"Счет -> {scores}")
            
        await asyncio.sleep(4.3) # Отрисовка каждые 4.3 секунды (~14 тиков в минуту)

async def agent_loop(agent: Stage2AI, map_core: MapCore, arbiter: ArbitorPhysical, all_agents: List[Stage2AI]):
    """Жизненный цикл отдельного агента. Работает независимо от других."""
    turn_number = 0
    while True:
        try:
            if agent.is_dead:
                await asyncio.sleep(2.0)
                continue

            turn_number += 1

            # Агент думает (ждем ответа LLM)
            action_data = await agent.get_action_from_llm(map_core)

            # Агент применяет действие к карте
            if agent.is_dead:
                continue
            result = await arbiter.execute_action(agent, action_data, map_core, all_agents)
            logger.info(f"[{agent.name}] -> {action_data.get('action')} | {result}")

            # --- Обновление двухуровневой памяти ---
            action_name = action_data.get('action', 'UNKNOWN')

            # Краткосрочная память: добавляем запись, стираем старую при 4+
            journal_entry = f"Ход {turn_number}: {action_name} -> {result}"
            agent.short_term_memory.append(journal_entry)
            if len(agent.short_term_memory) > 4:
                agent.short_term_memory.pop(0)  # удаляем самую старую запись

            # Долгосрочная память: агент обновляет Компас, если вернул new_compass
            new_compass = action_data.get('new_compass')
            if new_compass and isinstance(new_compass, str) and new_compass.strip():
                agent.long_term_memory = new_compass.strip()
                logger.info(f"[{agent.name}] 🧭 КОМПАС ОБНОВЛЁН: {agent.long_term_memory}")

            # Legacy memory (backward compat)
            agent.memory.append(f"- Used {action_name}: {result}")
            if len(agent.memory) > 10:
                agent.memory = agent.memory[-10:]

            # Настройка задержки под ~14 RPM (60 / 14 = 4.28 с)
            await asyncio.sleep(4.3)
        except Exception as e:
            logger.error(f"[{agent.name}] LOOP CRASHED: {e}")
            await asyncio.sleep(10.0)

async def main_simulation():
    logger.info("=== ЗАПУСК АСИНХРОННОЙ ФАЗЫ 2 (REAL-TIME) ===")
    
    try:
        with open("agents_config.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error("agents_config.json не найден!")
        return

    world_map = MapCore(width=7, height=7)
    world_map.spawn_mines()
    arbiter = ArbitorPhysical()

    agents = [
        Stage2AI(data["agents"][0]["name"], data["agents"][0]["api_key"], data["agents"][0]["model"], Position(x=0, y=0), data["agents"][0].get("income", {})),
        Stage2AI(data["agents"][1]["name"], data["agents"][1]["api_key"], data["agents"][1]["model"], Position(x=6, y=6), data["agents"][1].get("income", {}))
    ]

    # Запускаем отрисовку и каждого агента как отдельные независимые таски
    tasks = [
        asyncio.create_task(map_render_loop(world_map, agents)),
        asyncio.create_task(agent_loop(agents[0], world_map, arbiter, agents)),
        asyncio.create_task(agent_loop(agents[1], world_map, arbiter, agents))
    ]

    # Ждем завершения (по сути бесконечно)
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main_simulation())
    except KeyboardInterrupt:
        logger.info("Симуляция остановлена пользователем.")
