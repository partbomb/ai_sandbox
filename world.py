from pydantic import BaseModel
from typing import List, Optional

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
        pass

    def get_cell(self, x: int, y: int) -> Cell:
        """Возвращает данные конкретной клетки."""
        pass

    def spawn_resources(self):
        """Случайным образом раскидывает ресурсы по свободным клеткам карты."""
        pass

# --- Расширение для Агента (Единственный Аватар) ---

class Stage2AI_Avatar: 
    """
    Физическое воплощение агента на карте (единственный юнит).
    """
    def __init__(self, agent_id: str, start_pos: Position):
        pass

    def action_move(self, direction: str) -> dict:
        """
        Формирует намерение MOVE.
        Направления: 'N' (Север), 'S' (Юг), 'W' (Запад), 'E' (Восток).
        """
        pass

    def action_capture(self, target_pos: Position) -> dict:
        """
        Формирует намерение CAPTURE.
        Захватывать можно любую ничью (owner_id == None) клетку.
        """
        pass

    def action_build(self, structure_type: str, target_pos: Position) -> dict:
        """
        Формирует намерение BUILD.
        Пока доступна только постройка 'Wall' (Стена).
        """
        pass

# --- Валидатор физических действий ---

class ArbitorPhysical:
    """Отвечает за проверку физических действий на карте."""

    def validate_move(self, avatar: Stage2AI_Avatar, new_pos: Position, map_core: MapCore) -> bool:
        """
        Проверяет, можно ли сделать шаг на new_pos:
        1. Внутри границ карты?
        2. Нет ли там стены ('Wall')?
        """
        pass

    def validate_capture(self, avatar: Stage2AI_Avatar, target_pos: Position, map_core: MapCore) -> bool:
        """
        Проверяет, можно ли захватить клетку:
        1. Клетка ничья (owner_id is None)?
        2. Клетка находится рядом с аватаром?
        """
        pass

    def validate_build(self, avatar: Stage2AI_Avatar, structure_type: str, target_pos: Position, map_core: MapCore) -> bool:
        """
        Проверяет, можно ли построить стену:
        1. Это тип здания 'Wall'?
        2. Клетка пустая (нет других зданий)?
        """
        pass
