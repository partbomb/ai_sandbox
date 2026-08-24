import json
import logging
import time
import random
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
    structure: Optional[str] = None      # 'Wall'

class MapCore:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [
            [Cell(pos=Position(x=x, y=y)) for y in range(height)]
            for x in range(width)
        ]

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[x][y]
        return None

    def spawn_resources(self, amount: int = 8):
        resources = ['Matter', 'Energy', 'Imagination']
        spawned = 0
        while spawned < amount:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            cell = self.grid[x][y]
            if cell.resource_type is None and cell.structure is None:
                cell.resource_type = random.choice(resources)
                spawned += 1

    def print_map(self, avatars: List['Stage2AI']):
        """Красивый вывод карты в консоль"""
        print("\n" + "=" * (self.width * 3 + 2))
        for y in range(self.height):
            row_str = "|"
            for x in range(self.width):
                cell = self.grid[x][y]
                
                # Проверяем, есть ли на клетке аватар
                avatar_here = next((a for a in avatars if a.position.x == x and a.position.y == y), None)
                
                if avatar_here:
                    # Если тут агент 1, то 🔴, если агент 2, то 🔵
                    if "Alpha" in avatar_here.name: row_str += "🔴 "
                    else: row_str += "🔵 "
                elif cell.structure == 'Wall':
                    row_str += "🧱 "
                elif cell.owner_id is not None:
                    # Захваченная клетка
                    if "Alpha" in cell.owner_id: row_str += "🟥 "
                    else: row_str += "🟦 "
                elif cell.resource_type == 'Matter':
                    row_str += "⚛️  "
                elif cell.resource_type == 'Energy':
                    row_str += "⚡ "
                elif cell.resource_type == 'Imagination':
                    row_str += "💡 "
                else:
                    row_str += "⬛ "
            row_str += "|"
            print(row_str)
        print("=" * (self.width * 3 + 2) + "\n")


# --- Расширение для Агента (Единственный Аватар) ---

class Stage2AI: 
    def __init__(self, name: str, api_key: str, model: str, start_pos: Position):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.position = start_pos
        self.score = 0  # Очки за владение территориями

    def get_surroundings(self, map_core: MapCore) -> List[dict]:
        """Возвращает информацию о соседних клетках для промпта."""
        surroundings = []
        for dx, dy, dir_name in [(0,-1,'N'), (0,1,'S'), (-1,0,'W'), (1,0,'E')]:
            nx, ny = self.position.x + dx, self.position.y + dy
            cell = map_core.get_cell(nx, ny)
            if cell:
                surroundings.append({
                    "direction": dir_name,
                    "x": nx, "y": ny,
                    "owner": cell.owner_id,
                    "resource": cell.resource_type,
                    "structure": cell.structure
                })
        return surroundings

    def generate_prompt(self, map_core: MapCore) -> str:
        surroundings = self.get_surroundings(map_core)
        prompt = (
            f"You are AI Agent '{self.name}' on a 2D grid map.\n"
            f"Your current position is X:{self.position.x}, Y:{self.position.y}.\n"
            f"Your goal is to CAPTURE cells with resources to gain points, or BUILD Walls to block enemies.\n"
            f"Surrounding cells (adjacent):\n"
            f"{json.dumps(surroundings, indent=2)}\n\n"
            f"Available actions (return strictly JSON):\n"
            f"1. MOVE: {{\"action\": \"MOVE\", \"params\": {{\"direction\": \"N\"}}}} (N, S, E, W)\n"
            f"2. CAPTURE: {{\"action\": \"CAPTURE\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}} (only unowned adjacent cells)\n"
            f"3. STEAL: {{\"action\": \"STEAL\", \"params\": {{\"target_x\": X, \"target_y\": Y}}}} (10% chance to steal enemy cell)\n"
            f"4. BUILD: {{\"action\": \"BUILD\", \"params\": {{\"structure_type\": \"Wall\", \"target_x\": X, \"target_y\": Y}}}}"
        )
        return prompt

    def get_action_from_llm(self, map_core: MapCore) -> dict:
        prompt = self.generate_prompt(map_core)
        
        # Заглушка, если нет ключа
        if not self.api_key or self.api_key.startswith("sk-") or "AQ" in self.api_key:
            # Имитируем простое ИИ поведение (рандомное осмысленное действие)
            surr = self.get_surroundings(map_core)
            # 1. Попробуем захватить если есть ничья с ресурсом
            for s in surr:
                if s["owner"] is None and s["resource"] is not None:
                    return {"action": "CAPTURE", "params": {"target_x": s["x"], "target_y": s["y"]}}
            
            # 2. Иначе просто идем в рандомном направлении где нет стен
            valid_moves = [s["direction"] for s in surr if s["structure"] != 'Wall']
            if valid_moves:
                return {"action": "MOVE", "params": {"direction": random.choice(valid_moves)}}
            
            return {"action": "PASS"}

        # Реальный вызов (пока можно закомментировать, чтобы не тратить токены при тестах)
        try:
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return {"action": "PASS"}


# --- Валидатор физических действий ---

class ArbitorPhysical:
    def is_adjacent(self, pos1: Position, pos2: Position) -> bool:
        dx = abs(pos1.x - pos2.x)
        dy = abs(pos1.y - pos2.y)
        return (dx == 1 and dy == 0) or (dx == 0 and dy == 1)

    def execute_action(self, avatar: Stage2AI, action_data: dict, map_core: MapCore) -> str:
        action = action_data.get("action")
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
                return f"Успешно переместился на {direction} ({new_x}, {new_y})"
            return "Ошибка: Невозможно переместиться (стена или край карты)."

        elif action == "CAPTURE":
            tx, ty = params.get("target_x"), params.get("target_y")
            target_cell = map_core.get_cell(tx, ty)
            if target_cell and self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                if target_cell.owner_id is None:
                    target_cell.owner_id = avatar.name
                    return f"Захватил клетку ({tx}, {ty})"
            return "Ошибка: Клетка занята или слишком далеко."

        elif action == "STEAL":
            tx, ty = params.get("target_x"), params.get("target_y")
            target_cell = map_core.get_cell(tx, ty)
            if target_cell and self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                if target_cell.owner_id is not None and target_cell.owner_id != avatar.name:
                    if random.random() < 0.10: # 10% шанс
                        target_cell.owner_id = avatar.name
                        return f"УСПЕШНО УКРАЛ клетку ({tx}, {ty})!"
                    else:
                        return f"ПРОВАЛ кражи клетки ({tx}, {ty})."
            return "Ошибка: Нельзя украсть эту клетку."

        elif action == "BUILD":
            tx, ty = params.get("target_x"), params.get("target_y")
            target_cell = map_core.get_cell(tx, ty)
            if target_cell and self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                if target_cell.structure is None and target_cell.owner_id is None:
                    target_cell.structure = 'Wall'
                    return f"Построил стену на ({tx}, {ty})"
            return "Ошибка: Невозможно построить стену здесь."
            
        return "Неизвестное действие или PASS."


# --- Главный цикл (Standalone Test) ---

def run_physical_simulation():
    logger.info("=== ЗАПУСК ФАЗЫ 2 (КАРТА) ===")
    
    # 1. Загрузка конфигурации
    with open("agents_config.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if len(data["agents"]) < 2:
        logger.error("Нужно минимум 2 агента в agents_config.json")
        return

    # 2. Инициализация карты 8x8
    world_map = MapCore(width=8, height=8)
    world_map.spawn_resources(10)
    arbiter = ArbitorPhysical()

    # 3. Создаем аватаров по углам карты
    agents = [
        Stage2AI(data["agents"][0]["name"], data["agents"][0]["api_key"], data["agents"][0]["model"], Position(x=0, y=0)),
        Stage2AI(data["agents"][1]["name"], data["agents"][1]["api_key"], data["agents"][1]["model"], Position(x=7, y=7))
    ]

    # 4. Игровой цикл
    for tick in range(1, 11): # 10 ходов для теста
        print(f"\n--- [ ХОД {tick} ] ---")
        world_map.print_map(agents)

        for agent in agents:
            # Получаем решение ИИ
            action = agent.get_action_from_llm(world_map)
            # Выполняем через арбитра
            result = arbiter.execute_action(agent, action, world_map)
            logger.info(f"[{agent.name}] Намерение: {action['action']} -> Результат: {result}")
            
            # Подсчет очков: каждая захваченная клетка = 1 очко
            agent.score = sum(1 for row in world_map.grid for cell in row if cell.owner_id == agent.name)
        
        # Печать очков
        scores = " | ".join([f"{a.name}: {a.score} очков" for a in agents])
        logger.info(f"Текущий счет -> {scores}")
        time.sleep(1.5)

    print("\n--- КОНЕЦ СИМУЛЯЦИИ ---")
    world_map.print_map(agents)
    logger.info("Победитель: " + max(agents, key=lambda a: a.score).name)

if __name__ == "__main__":
    run_physical_simulation()
