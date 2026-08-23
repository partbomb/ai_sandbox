import random
from pydantic import BaseModel
from typing import List, Optional, Dict

# --- Базовые структуры карты ---

class Position(BaseModel):
    """Координаты на 2D карте."""
    x: int
    y: int

class Cell(BaseModel):
    """
    Клетка на карте.
    """
    pos: Position
    owner_id: Optional[str] = None
    resource_type: Optional[str] = None  # Например: 'Matter', 'Energy', 'Imagination'
    structure: Optional[str] = None      # Например: 'Wall'

class MapCore:
    """Движок карты (Матрица)."""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # Создаем двумерный массив клеток
        self.grid: List[List[Cell]] = [
            [Cell(pos=Position(x=x, y=y)) for y in range(height)]
            for x in range(width)
        ]

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        """Возвращает данные конкретной клетки или None, если координаты вне карты."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[x][y]
        return None

    def spawn_resources(self):
        """Случайным образом раскидывает ресурсы по свободным клеткам карты."""
        resources = ['Matter', 'Energy', 'Imagination']
        # Простой спавн: 5 случайных ресурсов на карте
        for _ in range(5):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            cell = self.grid[x][y]
            if cell.resource_type is None and cell.structure is None:
                cell.resource_type = random.choice(resources)


# --- Расширение для Агента (Единственный Аватар) ---

class Stage2AI_Avatar: 
    """
    Физическое воплощение агента на карте (единственный юнит).
    """
    def __init__(self, agent_id: str, start_pos: Position):
        self.agent_id = agent_id
        self.position = start_pos

    def action_move(self, direction: str) -> dict:
        """Формирует намерение MOVE."""
        return {"action": "MOVE", "params": {"direction": direction}}

    def action_capture(self, target_pos: Position) -> dict:
        """Формирует намерение CAPTURE."""
        return {"action": "CAPTURE", "params": {"target_x": target_pos.x, "target_y": target_pos.y}}

    def action_build(self, structure_type: str, target_pos: Position) -> dict:
        """Формирует намерение BUILD."""
        return {"action": "BUILD", "params": {"structure_type": structure_type, "target_x": target_pos.x, "target_y": target_pos.y}}

    def action_steal(self, target_pos: Position) -> dict:
        """Формирует намерение STEAL (украсть чужую клетку)."""
        return {"action": "STEAL", "params": {"target_x": target_pos.x, "target_y": target_pos.y}}


# --- Валидатор физических действий ---

class ArbitorPhysical:
    """Отвечает за проверку и выполнение физических действий на карте."""

    def is_adjacent(self, pos1: Position, pos2: Position) -> bool:
        """Проверка, находятся ли клетки рядом (по вертикали или горизонтали)."""
        dx = abs(pos1.x - pos2.x)
        dy = abs(pos1.y - pos2.y)
        return (dx == 1 and dy == 0) or (dx == 0 and dy == 1)

    def process_move(self, avatar: Stage2AI_Avatar, direction: str, map_core: MapCore) -> bool:
        """Проверка и выполнение шага."""
        dx, dy = 0, 0
        if direction == 'N': dy = -1
        elif direction == 'S': dy = 1
        elif direction == 'E': dx = 1
        elif direction == 'W': dx = -1
        else: return False

        new_x = avatar.position.x + dx
        new_y = avatar.position.y + dy
        target_cell = map_core.get_cell(new_x, new_y)

        if target_cell and target_cell.structure != 'Wall':
            avatar.position = Position(x=new_x, y=new_y)
            return True
        return False

    def process_capture(self, avatar: Stage2AI_Avatar, target_pos: Position, map_core: MapCore) -> bool:
        """Проверка и выполнение захвата (только для ничьих клеток)."""
        target_cell = map_core.get_cell(target_pos.x, target_pos.y)
        if not target_cell: return False
        
        if self.is_adjacent(avatar.position, target_pos) and target_cell.owner_id is None:
            target_cell.owner_id = avatar.agent_id
            return True
        return False
        
    def process_steal(self, avatar: Stage2AI_Avatar, target_pos: Position, map_core: MapCore) -> bool:
        """
        Попытка украсть чужую клетку.
        Успех с вероятностью 10%.
        """
        target_cell = map_core.get_cell(target_pos.x, target_pos.y)
        if not target_cell: return False
        
        # Можно воровать только если клетка чужая и находится рядом
        if self.is_adjacent(avatar.position, target_pos) and target_cell.owner_id is not None and target_cell.owner_id != avatar.agent_id:
            # Вероятность успеха 10%
            if random.random() < 0.10:
                target_cell.owner_id = avatar.agent_id
                return True
        return False

    def process_build(self, avatar: Stage2AI_Avatar, structure_type: str, target_pos: Position, map_core: MapCore) -> bool:
        """Проверка и постройка стены."""
        target_cell = map_core.get_cell(target_pos.x, target_pos.y)
        if not target_cell: return False

        if structure_type == 'Wall' and self.is_adjacent(avatar.position, target_pos) and target_cell.structure is None:
            target_cell.structure = 'Wall'
            return True
        return False
