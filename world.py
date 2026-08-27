import json
import logging
import random
import asyncio
import time
from typing import List, Optional, Dict
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
        self.score = 0
        self.is_dead = False
        self.balance = {"matter": 50, "energy": 50, "imagination": 50}
        self.income = init_income

    def generate_prompt(self, map_core: MapCore) -> str:
        surroundings = map_core.get_map_state_json(self.position.x, self.position.y, radius=1)
        prompt = (
            f"You are AI Agent '{self.name}' on a 2D grid map.\n"
            f"Your position: X:{self.position.x}, Y:{self.position.y}.\n"
            f"Your balance: Matter={self.balance['matter']}, Energy={self.balance['energy']}, Imagination={self.balance['imagination']}.\n"
            f"WARNING (Hunger): Every tick you lose 5 Energy! If Energy reaches 0, you DIE! Capture Energy mines (⚡) immediately!\n"
            f"WIN CONDITIONS:\n"
            f"1. Singularity: 5000 of all resources.\n"
            f"2. Monopoly: Capture 80% of all resource mines.\n"
            f"3. Battle Royale: ATTACK and kill all other agents.\n"
            f"Surrounding cells (radius 1):\n{surroundings}\n\n"
            f"Available actions (return strictly JSON):\n"
            f"1. MOVE: {{\"action\": \"MOVE\", \"params\": {{\"direction\": \"N\"}}}} (N, S, E, W)\n"
            f"2. CAPTURE: {{\"action\": \"CAPTURE\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}\n"
            f"3. ATTACK: {{\"action\": \"ATTACK\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}}\n"
            f"4. STEAL: {{\"action\": \"STEAL\"}} (10% chance to steal +50 all resources, 90% chance to lose -50)\n"
            f"5. PASS: {{\"action\": \"PASS\"}}"
        )
        return prompt

    async def get_action_from_llm(self, map_core: MapCore) -> dict:
        prompt = self.generate_prompt(map_core)
        
        # Если API-ключ - заглушка, возвращаем рандомное действие мгновенно
        if not self.api_key or self.api_key.startswith("sk-") or "test" in self.api_key.lower():
            await asyncio.sleep(0.5) # Имитация задержки сети
            moves = ["N", "S", "E", "W"]
            action = random.choice(["MOVE", "MOVE", "CAPTURE"])
            if action == "MOVE":
                return {"action": "MOVE", "params": {"direction": random.choice(moves)}}
            else:
                return {"action": "CAPTURE", "params": {"target_x": self.position.x, "target_y": self.position.y}}

        try:
            # Асинхронный вызов API (через to_thread, так как SDK синхронный)
            client = genai.Client(api_key=self.api_key)
            def _call_api():
                return client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            response = await asyncio.to_thread(_call_api)
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"[{self.name}] LLM Error: {e}")
            await asyncio.sleep(2) # Пауза при ошибке
            return {"action": "PASS"}


# --- Валидатор физических действий ---

class ArbitorPhysical:
    def is_adjacent(self, pos1: Position, pos2: Position) -> bool:
        dx = abs(pos1.x - pos2.x)
        dy = abs(pos1.y - pos2.y)
        return (dx <= 1 and dy <= 1)

    async def execute_action(self, avatar: Stage2AI, action_data: dict, map_core: MapCore, all_agents: List[Stage2AI]) -> str:
        # Используем lock, так как меняем общее состояние карты
        async with map_core.lock:
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
                    avatar.position = Position(x=new_x, y=new_y)
                    return f"Переместился на {direction} ({new_x}, {new_y})"
                return "Стена или край карты."

            elif action == "CAPTURE":
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                target_cell = map_core.get_cell(tx, ty)
                if target_cell and self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                    if target_cell.owner_id is None or target_cell.owner_id == avatar.name:
                        target_cell.owner_id = avatar.name
                        return f"Захватил ({tx}, {ty})"
                return "Нельзя захватить."

            elif action == "STEAL":
                if random.random() <= 0.10:
                    avatar.balance["matter"] += 50
                    avatar.balance["energy"] += 50
                    avatar.balance["imagination"] += 50
                    return "УСПЕХ! Украл +50 всех ресурсов."
                else:
                    avatar.balance["matter"] = max(0, avatar.balance["matter"] - 50)
                    avatar.balance["energy"] = max(0, avatar.balance["energy"] - 50)
                    avatar.balance["imagination"] = max(0, avatar.balance["imagination"] - 50)
                    return "ПРОВАЛ кражи! Штраф -50 всех ресурсов."
            
            elif action == "ATTACK":
                tx, ty = params.get("target_x", -1), params.get("target_y", -1)
                if self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                    # Ищем агента на этой клетке
                    enemy = next((a for a in all_agents if a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead), None)
                    if enemy:
                        enemy.is_dead = True
                        return f"УСПЕШНО АТАКОВАЛ И УБИЛ {enemy.name} на ({tx}, {ty})!"
                    else:
                        return f"На ({tx}, {ty}) нет врагов для атаки."
                return "Цель вне радиуса атаки."

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
        if agent.is_dead:
            await asyncio.sleep(2.0)
            continue
            
        # Агент думает (ждем ответа LLM)
        action_data = await agent.get_action_from_llm(map_core)
        
        # Агент применяет действие к карте
        result = await arbiter.execute_action(agent, action_data, map_core, all_agents)
        logger.info(f"[{agent.name}] -> {action_data.get('action')} | {result}")
        
        # Ускоряем время ожидания для быстрого отклика
        await asyncio.sleep(2.5) 

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
