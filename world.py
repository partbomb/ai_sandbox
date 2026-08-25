import json
import logging
import random
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger("WorldMap")

class Position(BaseModel):
    x: int
    y: int

class Cell(BaseModel):
    pos: Position
    owner_id: Optional[str] = None
    resource_type: Optional[str] = None  # 'Matter', 'Energy', 'Imagination'
    mine_level: int = 0
    structure: Optional[str] = None      # 'Wall'

class MapCore:
    def __init__(self, width: int = 5, height: int = 5):
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [
            [Cell(pos=Position(x=x, y=y)) for y in range(height)]
            for x in range(width)
        ]

    def spawn_mines(self):
        # 3 mines for each resource (9 total)
        resources = ['Matter', 'Matter', 'Matter', 'Energy', 'Energy', 'Energy', 'Imagination', 'Imagination', 'Imagination']
        cells = [cell for row in self.grid for cell in row]
        random.shuffle(cells)
        for i, res in enumerate(resources):
            cells[i].resource_type = res
            cells[i].mine_level = 1

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[x][y]
        return None

    def get_map_state_json(self) -> str:
        state = []
        for y in range(self.height):
            for x in range(self.width):
                c = self.grid[x][y]
                # To save context length, only send interesting cells or all cells? 5x5 is small enough.
                state.append({
                    "x": c.pos.x, "y": c.pos.y,
                    "owner": c.owner_id,
                    "resource": c.resource_type,
                    "level": c.mine_level,
                    "structure": c.structure
                })
        return json.dumps(state)

    def calculate_passive_income(self, agent_name: str) -> dict:
        income = {"matter": 0, "energy": 0, "imagination": 0}
        for row in self.grid:
            for cell in row:
                if cell.owner_id == agent_name and cell.mine_level > 0:
                    val = cell.mine_level * 100
                    if cell.resource_type == 'Matter': income["matter"] += val
                    elif cell.resource_type == 'Energy': income["energy"] += val
                    elif cell.resource_type == 'Imagination': income["imagination"] += val
        return income

