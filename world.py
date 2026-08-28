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
    def __init__(self, name: str, api_key: str, model: str, start_pos: Position, init_income: dict):
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
        self.memory = []

        self.client = genai.Client(api_key=self.api_key) if self.api_key and not self.api_key.startswith("sk-") and "test" not in self.api_key.lower() else None

    def generate_prompt(self, map_core: MapCore) -> str:
        surroundings = map_core.get_map_state_json(self.position.x, self.position.y, radius=2)
        prompt = (
            f"You are AI Agent '{self.name}' on a 10x10 map (X:0-9, Y:0-9).\n"
            f"Your position: X:{self.position.x}, Y:{self.position.y}. HP: {self.hp}/100.\n"
            f"Your balance: Matter={self.balance['matter']}, Energy={self.balance['energy']}, Imagination={self.balance['imagination']}.\n"
            f"MEMORY LOG (Last actions and results):\n"
            f"{chr(10).join(self.memory) if self.memory else 'No memories yet.'}\n\n"
            f"WIN CONDITIONS:\n"
            f"1. Singularity: 5000 of all resources.\n"
            f"2. Monopoly: Capture 80% of all resource mines.\n"
            f"3. Battle Royale: Kill all other agents.\n"
            f"RULES & MECHANICS:\n"
            f"- MOVE: Navigate the map. Blocked by Walls or Enemies. Loot is auto-picked up.\n"
            f"- ATTACK (Cost: 5 Energy): Deals 25 damage. Targets: Enemies, Walls, or Mines. Drops Matter when breaking walls/mines.\n"
            f"- BUILD (Cost: 20 Matter): Builds a Wall on an adjacent cell to block movement.\n"
            f"- CAPTURE (Cost: 10 Imagination): Reprograms a mine to give you passive income. Requires cell to be clear of enemies/walls.\n"
            f"MAP BOUNDARIES: DO NOT move outside 0-9! If you are at Y=0, you CANNOT move N. If Y=9, you CANNOT move S. If X=0, you CANNOT move W. If X=9, you CANNOT move E.\n"
            f"Surrounding cells (radius 2):\n{surroundings}\n\n"
            f"Available actions (return strictly JSON):\n"
            f"1. MOVE: {{\"action\": \"MOVE\", \"params\": {{\"direction\": \"N\"}}}} (N, S, E, W)\n"
            f"2. ATTACK: {{\"action\": \"ATTACK\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}\n"
            f"3. BUILD: {{\"action\": \"BUILD\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}\n"
            f"4. CAPTURE: {{\"action\": \"CAPTURE\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}\n"
            f"5. PASS: {{\"action\": \"PASS\"}}\n"
            f"THINK BEFORE YOU ACT. Add a 'thought' field in your JSON explaining your strategy.\n"
        )
        return prompt

    async def get_action_from_llm(self, map_core: MapCore) -> dict:
        prompt = self.generate_prompt(map_core)
        
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
            
            if action == "MOVE":
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
                        
                    avatar.position = Position(x=new_x, y=new_y)
                    pickup_msg = ""
                    for res in ['matter', 'energy', 'imagination']:
                        if target_cell.loot.get(res, 0) > 0:
                            amt = target_cell.loot[res]
                            avatar.balance[res] += amt
                            target_cell.loot[res] = 0
                            pickup_msg += f" Подобрано {amt} {res}."
                    return f"Переместился на {direction} ({new_x}, {new_y})." + pickup_msg
                return "Стена или край карты."

            elif action == "ATTACK":
                if avatar.balance["energy"] < 5:
                    return "Недостаточно Энергии (Нужно 5) для атаки."
                avatar.balance["energy"] -= 5
                
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Цель вне зоны досягаемости."
                    
                target_cell = map_core.get_cell(tx, ty)
                enemy = next((a for a in all_agents if a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead), None)
                
                if enemy:
                    enemy.hp -= 25
                    if enemy.hp <= 0:
                        enemy.is_dead = True
                        enemy.respawn_timer = 5
                        for res in ['matter', 'energy', 'imagination']:
                            target_cell.loot[res] = target_cell.loot.get(res, 0) + enemy.balance[res]
                            enemy.balance[res] = 0
                        return f"УСПЕШНО АТАКОВАЛ И УБИЛ {enemy.name} на ({tx}, {ty})!"
                    return f"Нанес 25 урона {enemy.name}. Осталось HP: {enemy.hp}."
                elif target_cell and target_cell.structure == 'Wall':
                    target_cell.wall_hp -= 25
                    avatar.balance["matter"] += 2
                    if target_cell.wall_hp <= 0:
                        target_cell.structure = None
                        return "Стена разрушена! Получено 2 Материи."
                    return f"Удар по стене. Осталось HP: {target_cell.wall_hp}."
                elif target_cell and target_cell.resource_type:
                    target_cell.mine_hp -= 25
                    avatar.balance["matter"] += 5
                    if target_cell.mine_hp <= 0:
                        target_cell.resource_type = None
                        target_cell.owner_id = None
                        return "Шахта полностью разрушена! Получено 5 Материи."
                    return f"Удар по шахте. Осталось HP: {target_cell.mine_hp}."
                else:
                    return f"На ({tx}, {ty}) нет подходящей цели для атаки."
                    
            elif action == "BUILD":
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                    return "Цель вне зоны досягаемости."
                if avatar.balance["matter"] < 20:
                    return "Недостаточно Материи (нужно 20) для постройки стены."
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell or target_cell.structure == 'Wall':
                    return "Здесь уже есть постройка или край карты."
                
                enemy_here = any(a.position.x == tx and a.position.y == ty and not a.is_dead for a in all_agents)
                if enemy_here: return "Невозможно строить: на клетке кто-то стоит."
                
                avatar.balance["matter"] -= 20
                target_cell.structure = 'Wall'
                target_cell.wall_hp = 100
                return "Стена успешно построена."

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
            
        await asyncio.sleep(2.0) # Отрисовка каждые 2 секунды

async def agent_loop(agent: Stage2AI, map_core: MapCore, arbiter: ArbitorPhysical, all_agents: List[Stage2AI]):
    """Жизненный цикл отдельного агента. Работает независимо от других."""
    while True:
        try:
            if agent.is_dead:
                await asyncio.sleep(2.0)
                continue
                
            # Агент думает (ждем ответа LLM)
            action_data = await agent.get_action_from_llm(map_core)
            
            # Агент применяет действие к карте
            if agent.is_dead:
                continue
            result = await arbiter.execute_action(agent, action_data, map_core, all_agents)
            logger.info(f"[{agent.name}] -> {action_data.get('action')} | {result}")
            
            # Сохраняем результат в память ИИ
            action_name = action_data.get('action', 'UNKNOWN')
            agent.memory.append(f"- Used {action_name}: {result}")
            if len(agent.memory) > 10:
                agent.memory = agent.memory[-10:]
            
            # Ускоряем время ожидания для быстрого отклика
            await asyncio.sleep(2.5) 
        except Exception as e:
            logger.error(f"[{agent.name}] LOOP CRASHED: {e}")
            await asyncio.sleep(2.0)

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
