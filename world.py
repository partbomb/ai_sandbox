import json
import logging
import os
import time
import random
import asyncio
from typing import List, Optional
import numpy as np
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Настройка простого логгера для world.py
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("WorldMap")

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

# --- RL Константы (совместимые с rl_env.py) ---
RL_MAP_SIZE = 7
RL_MAX_RESOURCE = 5000
RL_TECH_NAMES = [
    "combat_lvl_1", "combat_lvl_2", "combat_lvl_3",
    "economy_lvl_1", "economy_lvl_2", "economy_lvl_3",
    "logistics_lvl_1", "logistics_lvl_2", "logistics_lvl_3",
]
RL_ACTION_NAMES = [
    "MOVE_TO_MINE", "MOVE_TO_ENEMY", "MOVE_TO_ENERGY_MINE",
    "CAPTURE", "ATTACK", "BUILD", "RESEARCH",
    "GATHER_LOOT", "PASS"
]
RL_ADJACENT_OFFSETS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]
RL_SELF_AND_ADJACENT = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),  (0, 0),  (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

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
    structure: Optional[str] = None      # 'Wall', 'Casino'
    wall_hp: int = 0
    loot: dict = Field(default_factory=dict)  # {'matter': x, 'energy': y, 'imagination': z}
    casino_jackpot: int = 0  # Accumulated jackpot from lost bets

class MapCore:
    def __init__(self, width: int = 5, height: int = 5):
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [
            [Cell(pos=Position(x=x, y=y)) for y in range(height)]
            for x in range(width)
        ]
        self.lock = asyncio.Lock()  # Блокировка для асинхронного доступа к карте
        self.diplomacy_log: List[dict] = []  # Общий лог дипломатических переговоров

    def spawn_mines(self):
        resources = ['Matter', 'Matter', 'Matter', 'Energy', 'Energy', 'Energy', 'Imagination', 'Imagination', 'Imagination']
        cells = [cell for row in self.grid for cell in row]
        random.shuffle(cells)
        for i, res in enumerate(resources):
            cells[i].resource_type = res
            cells[i].mine_level = 1
            cells[i].mine_hp = 50

    def spawn_casinos(self, count: int = 3):
        """Размещает казино на пустых клетках (без шахт, стен и других структур)."""
        empty_cells = [
            cell for row in self.grid for cell in row
            if cell.resource_type is None and cell.structure is None
        ]
        random.shuffle(empty_cells)
        placed = 0
        for cell in empty_cells:
            if placed >= count:
                break
            cell.structure = 'Casino'
            cell.casino_jackpot = random.randint(50, 200)  # Initial jackpot seed
            placed += 1
            logger.info(f"🎰 Казино размещено на ({cell.pos.x}, {cell.pos.y}) [Jackpot: {cell.casino_jackpot}]")

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
                if c.structure == 'Casino':
                    cell_data["casino_jackpot"] = c.casino_jackpot
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
    def __init__(
        self,
        name: str,
        api_key: str,
        model: str,
        start_pos: Position,
        init_income: dict,
        is_human: bool = False,
        is_rl: bool = False,
        rl_model_path: str = "rl_models/best/best_model"
    ):
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
        self.long_term_memory: str = (
            "Максимизация функции полезности V(s)" if is_rl
            else "Начало. Изучить карту и захватить ближайшую шахту."
        )

        self.is_human = is_human
        self.human_action = None
        self.human_prompt = ""
        self.human_ready = asyncio.Event()

        # --- Diplomacy & Messaging ---
        self.inbox: List[str] = []  # Хранит последние 3 входящих дипломатических сообщения

        # --- Research Telemetry & Cognitive Metrics ---
        self.total_actions: int = 0
        self.invalid_actions: int = 0
        self.attacks_count: int = 0
        self.captures_count: int = 0
        self.deaths_count: int = 0
        self.fixation_loops: int = 0
        self.recent_action_history: List[tuple] = []

        # --- RL Mode Settings ---
        self.is_rl = is_rl
        self.rl_model_path = rl_model_path
        self.rl_model = None

        if self.is_rl:
            self.client = None
            self._load_rl_model(rl_model_path)
        elif self.api_key and not self.api_key.startswith("sk-") and "test" not in self.api_key.lower() and not self.is_human:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _load_rl_model(self, rl_model_path: str):
        """Загружает обученную RL модель (PPO / DQN) с фоллбэком на эвристику."""
        try:
            from stable_baselines3 import PPO, DQN
        except ImportError:
            logger.warning(f"[{self.name}] stable_baselines3 не установлена в текущем окружении. Включен эвристический фоллбэк.")
            self.rl_model = None
            return

        model_file = rl_model_path if rl_model_path.endswith(".zip") else rl_model_path + ".zip"
        if not os.path.exists(model_file) and not os.path.exists(rl_model_path):
            logger.warning(f"[{self.name}] Файл RL модели '{rl_model_path}' не найден. Сервер продолжает работу в режиме эвристики.")
            self.rl_model = None
            return

        try:
            self.rl_model = PPO.load(rl_model_path, device='cpu')
            logger.info(f"[{self.name}] ✅ Успешно загружена RL-модель PPO из '{rl_model_path}'")
        except Exception as e_ppo:
            try:
                self.rl_model = DQN.load(rl_model_path, device='cpu')
                logger.info(f"[{self.name}] ✅ Успешно загружена RL-модель DQN из '{rl_model_path}'")
            except Exception as e_dqn:
                logger.warning(f"[{self.name}] ⚠️ Не удалось загрузить модель (PPO: {e_ppo}, DQN: {e_dqn}). Включен эвристический фоллбэк.")
                self.rl_model = None

    def generate_prompt(self, map_core: MapCore) -> str:
        surroundings = map_core.get_map_state_json()
        
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
        actions_str += "8. GAMBLE: {\"action\": \"GAMBLE\", \"params\": {\"target_x\": X, \"target_y\": Y, \"bet\": AMOUNT, \"resource\": \"matter\"/\"energy\"/\"imagination\"}}. MUST be adjacent/on a 🎰 Casino cell. Min bet: 10. 40% chance to WIN 2x, 5% JACKPOT (3x + jackpot pool), 55% LOSE bet.\n"
        actions_str += "9. DIPLOMACY: {\"action\": \"DIPLOMACY\", \"params\": {\"target_agent\": \"Имя_Агента или ALL\", \"message\": \"Текст предложения союза/угрозы/обмана\"}}. Cost: 0 Energy. Free diplomatic communication to negotiate alliances, coordination, threats or bluffing.\n"
        actions_str += "10. GIVE: {\"action\": \"GIVE\", \"params\": {\"target_x\": X, \"target_y\": Y, \"resource\": \"matter\"/\"energy\"/\"imagination\", \"amount\": 20}}. Transfer resources to an adjacent agent to support an ally.\n"
        actions_str += "11. PASS: {\"action\": \"PASS\"}\n"

        # --- Build memory sections ---
        # Short-term: last 4 actions (бортовой журнал)
        stm_lines = self.short_term_memory if self.short_term_memory else ["Нет записей."]
        stm_text = "\n".join(f"  {i+1}. {line}" for i, line in enumerate(stm_lines))

        # Входящие дипломатические сообщения (последние 3)
        inbox_msgs = self.inbox if getattr(self, 'inbox', None) else ["(Входящих дипломатических сообщений нет)"]
        inbox_text = "\n".join(f"  {i+1}. {msg}" for i, msg in enumerate(inbox_msgs))

        prompt = (
            f"=== ПАПКА С ДЕЛОМ (твой текущий контекст) ===\n\n"
            f"[1] СТРАТЕГИЧЕСКИЙ КОМПАС (Долгосрочная цель):\n"
            f"  '{self.long_term_memory}'\n\n"
            f"[2] БОРТОВОЙ ЖУРНАЛ (Краткосрочная память, последние {len(stm_lines)} действий):\n"
            f"{stm_text}\n\n"
            f"[3] ТВОИ ГЛАЗА (Текущее состояние):\n"
            f"  Имя: {self.name} | Позиция: X:{self.position.x}, Y:{self.position.y} | HP: {self.hp}/100\n"
            f"  Баланс: Matter={self.balance['matter']}, Energy={self.balance['energy']}, Imagination={self.balance['imagination']}\n"
            f"  Карта ({map_core.width}x{map_core.height}, X:0-{map_core.width-1}, Y:0-{map_core.height-1}):\n{surroundings}\n\n"
            f"[4] ВХОДЯЩИЕ СООБЩЕНИЯ (Дипломатия):\n"
            f"{inbox_text}\n\n"
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
            f"- GAMBLE: Go to a 🎰 Casino cell and bet resources for a chance to multiply them! High risk, high reward.\n"
            f"- CAPTURE: Reprograms a mine. Requires cell to be clear of enemies/walls.\n"
            f"- DIPLOMACY: Send a message to any agent or 'ALL'. Cost: 0 Energy. Allows negotiating non-aggression pacts, alliances, trade or bluffing.\n"
            f"- GIVE: Transfer specified amount of Matter, Energy, or Imagination to an adjacent agent to support an ally.\n"
            f"MAP BOUNDARIES: DO NOT move outside 0-{max(map_core.width-1, map_core.height-1)}! If at Y=0 cannot move N, Y={map_core.height-1} cannot move S, X=0 cannot move W, X={map_core.width-1} cannot move E.\n\n"
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

    def _build_rl_obs(self, map_core: MapCore, all_agents: Optional[List['Stage2AI']] = None, target_dim: int = 315) -> np.ndarray:
        """
        Переводит текущее состояние MapCore в вектор признаков (float32).
        Для карт 10x10 вырезает окно 7x7 с центром вокруг агента.
        По умолчанию возвращает вектор из 315 элементов:
          294 (карта 7x7x6) + 6 (игрок) + 6 (враг) + 9 (технологии) = 315.
        При target_dim=324 дополняет 9 подсказками из AISandboxEnv (rl_env.py).
        """
        if all_agents is None:
            all_agents = [self]

        obs = []

        # 1. Окно 7x7 вокруг агента
        if map_core.width >= RL_MAP_SIZE:
            start_x = max(0, min(self.position.x - 3, map_core.width - RL_MAP_SIZE))
        else:
            start_x = 0

        if map_core.height >= RL_MAP_SIZE:
            start_y = max(0, min(self.position.y - 3, map_core.height - RL_MAP_SIZE))
        else:
            start_y = 0

        # 2. Каналы карты (7x7 x 6 = 294)
        for wy in range(RL_MAP_SIZE):
            for wx in range(RL_MAP_SIZE):
                mx = start_x + wx
                my = start_y + wy
                cell = map_core.get_cell(mx, my)

                # Канал 1: Владелец (0 = нет, 0.5 = self, 1.0 = враг)
                owner_val = 0.0
                if cell and cell.owner_id:
                    if cell.owner_id == self.name:
                        owner_val = 0.5
                    else:
                        owner_val = 1.0
                obs.append(owner_val)

                # Канал 2: Наличие шахты (1.0 если ресурс есть)
                has_res = 1.0 if (cell and cell.resource_type) else 0.0
                obs.append(has_res)

                # Канал 3: Тип ресурса (0 = нет, 0.33 = Matter, 0.66 = Energy, 1.0 = Imagination)
                rt = 0.0
                if cell and cell.resource_type:
                    res_lower = cell.resource_type.lower()
                    if res_lower == "matter":
                        rt = 0.33
                    elif res_lower == "energy":
                        rt = 0.66
                    elif res_lower == "imagination":
                        rt = 1.0
                obs.append(rt)

                # Канал 4: Уровень шахты (0-3 -> 0.0-1.0)
                obs.append(min((cell.mine_level if cell else 0) / 3.0, 1.0))

                # Канал 5: Структура (1.0 если стена)
                is_wall = 1.0 if (cell and cell.structure and cell.structure.lower() == 'wall') else 0.0
                obs.append(is_wall)

                # Канал 6: Наличие лута
                has_loot = 1.0 if (cell and cell.loot and any(v > 0 for v in cell.loot.values())) else 0.0
                obs.append(has_loot)

        # 3. Состояние агента (self) - 6 значений
        rel_x = max(0, min(self.position.x - start_x, RL_MAP_SIZE - 1))
        rel_y = max(0, min(self.position.y - start_y, RL_MAP_SIZE - 1))
        obs.append(rel_x / (RL_MAP_SIZE - 1))
        obs.append(rel_y / (RL_MAP_SIZE - 1))
        obs.append(getattr(self, 'hp', 100) / 100.0)
        obs.append(min(self.balance.get("matter", 0) / RL_MAX_RESOURCE, 1.0))
        obs.append(min(self.balance.get("energy", 0) / RL_MAX_RESOURCE, 1.0))
        obs.append(min(self.balance.get("imagination", 0) / RL_MAX_RESOURCE, 1.0))

        # 4. Состояние ближайшего врага - 6 значений
        enemy = None
        min_dist = float('inf')
        for a in all_agents:
            if a.name != self.name and not a.is_dead:
                d = abs(a.position.x - self.position.x) + abs(a.position.y - self.position.y)
                if d < min_dist:
                    min_dist = d
                    enemy = a
        if enemy is None:
            for a in all_agents:
                if a.name != self.name:
                    d = abs(a.position.x - self.position.x) + abs(a.position.y - self.position.y)
                    if d < min_dist:
                        min_dist = d
                        enemy = a

        if enemy is not None:
            e_rel_x = max(0, min(enemy.position.x - start_x, RL_MAP_SIZE - 1))
            e_rel_y = max(0, min(enemy.position.y - start_y, RL_MAP_SIZE - 1))
            obs.append(e_rel_x / (RL_MAP_SIZE - 1))
            obs.append(e_rel_y / (RL_MAP_SIZE - 1))
            obs.append(getattr(enemy, 'hp', 100) / 100.0 if not enemy.is_dead else 0.0)
            obs.append(min(enemy.balance.get("matter", 0) / RL_MAX_RESOURCE, 1.0))
            obs.append(min(enemy.balance.get("energy", 0) / RL_MAX_RESOURCE, 1.0))
            obs.append(min(enemy.balance.get("imagination", 0) / RL_MAX_RESOURCE, 1.0))
        else:
            obs.extend([0.5, 0.5, 0.0, 0.0, 0.0, 0.0])

        # 5. Дерево технологий - 9 бинарных значений
        for tech in RL_TECH_NAMES:
            obs.append(1.0 if tech in self.unlocked_techs else 0.0)

        # 6. Расширенные подсказки (если запрошено >= 324 элементов)
        if target_dim > 315:
            # dx/dy к ближайшей шахте
            best_m = None
            best_m_dist = float('inf')
            for row in map_core.grid:
                for c in row:
                    if c.resource_type and c.owner_id != self.name:
                        d = abs(c.pos.x - self.position.x) + abs(c.pos.y - self.position.y)
                        if d < best_m_dist:
                            best_m_dist = d
                            best_m = c
            if best_m:
                obs.append((best_m.pos.x - self.position.x + RL_MAP_SIZE) / (2 * RL_MAP_SIZE))
                obs.append((best_m.pos.y - self.position.y + RL_MAP_SIZE) / (2 * RL_MAP_SIZE))
            else:
                obs.extend([0.5, 0.5])

            # dx/dy к ближайшей энергетической шахте
            best_em = None
            best_em_dist = float('inf')
            for row in map_core.grid:
                for c in row:
                    if c.resource_type and c.resource_type.lower() == 'energy' and c.owner_id != self.name:
                        d = abs(c.pos.x - self.position.x) + abs(c.pos.y - self.position.y)
                        if d < best_em_dist:
                            best_em_dist = d
                            best_em = c
            if best_em:
                obs.append((best_em.pos.x - self.position.x + RL_MAP_SIZE) / (2 * RL_MAP_SIZE))
                obs.append((best_em.pos.y - self.position.y + RL_MAP_SIZE) / (2 * RL_MAP_SIZE))
            else:
                obs.extend([0.5, 0.5])

            # dx/dy к врагу
            if enemy and not enemy.is_dead:
                obs.append((enemy.position.x - self.position.x + RL_MAP_SIZE) / (2 * RL_MAP_SIZE))
                obs.append((enemy.position.y - self.position.y + RL_MAP_SIZE) / (2 * RL_MAP_SIZE))
            else:
                obs.extend([0.5, 0.5])

            # can_capture
            can_capture = 0.0
            for odx, ody in RL_SELF_AND_ADJACENT:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c and c.resource_type and c.owner_id != self.name and c.structure != 'Wall':
                    can_capture = 1.0
                    break
            obs.append(can_capture)

            # can_attack
            can_attack = 0.0
            if enemy and not enemy.is_dead:
                d = abs(enemy.position.x - self.position.x) + abs(enemy.position.y - self.position.y)
                if d <= 1:
                    can_attack = 1.0
            obs.append(can_attack)

            # has_loot_nearby
            has_loot_nearby = 0.0
            for odx, ody in RL_SELF_AND_ADJACENT:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c and c.loot and any(v > 0 for v in c.loot.values()):
                    has_loot_nearby = 1.0
                    break
            obs.append(has_loot_nearby)

        # Приведение к целевой длине target_dim
        if len(obs) < target_dim:
            obs.extend([0.0] * (target_dim - len(obs)))
        elif len(obs) > target_dim:
            obs = obs[:target_dim]

        obs = np.clip(obs, 0.0, 1.0)
        return np.array(obs, dtype=np.float32)

    def _get_move_direction(self, tx: int, ty: int, map_core: MapCore, all_agents: List['Stage2AI']) -> Optional[str]:
        """Определяет наилучшее направление шага (N, S, E, W) к цели с обходом стен и агентов."""
        dx = 1 if tx > self.position.x else (-1 if tx < self.position.x else 0)
        dy = 1 if ty > self.position.y else (-1 if ty < self.position.y else 0)

        if dx == 0 and dy == 0:
            return None

        candidates = []
        if dx != 0:
            candidates.append((self.position.x + dx, self.position.y, 'E' if dx > 0 else 'W'))
        if dy != 0:
            candidates.append((self.position.x, self.position.y + dy, 'S' if dy > 0 else 'N'))

        # Перпендикулярные кандидаты для обхода препятствий (v2 logic)
        if dx == 0:
            candidates.append((self.position.x + 1, self.position.y, 'E'))
            candidates.append((self.position.x - 1, self.position.y, 'W'))
        if dy == 0:
            candidates.append((self.position.x, self.position.y + 1, 'S'))
            candidates.append((self.position.x, self.position.y - 1, 'N'))

        for nx, ny, direction in candidates:
            if 0 <= nx < map_core.width and 0 <= ny < map_core.height:
                cell = map_core.get_cell(nx, ny)
                if cell and cell.structure != 'Wall':
                    occupied = any(
                        a.position.x == nx and a.position.y == ny and a.name != self.name and not a.is_dead
                        for a in all_agents
                    )
                    if not occupied:
                        return direction
        return None

    def _heuristic_policy(self, map_core: MapCore, all_agents: List['Stage2AI']) -> int:
        """Эвристическая политика при отсутствии весов модели (безопасный фоллбэк)."""
        # 1. Если энергии мало (< 15) и рядом энергошахта -> захватить или идти к ней
        if self.balance.get("energy", 0) < 15:
            for odx, ody in RL_SELF_AND_ADJACENT:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c and c.resource_type and c.resource_type.lower() == 'energy' and c.owner_id != self.name and c.structure != 'Wall':
                    if self.balance.get("imagination", 0) >= 10:
                        return 3  # CAPTURE
            return 2  # MOVE_TO_ENERGY_MINE

        # 2. Захват шахты в радиусе досягаемости
        if self.balance.get("imagination", 0) >= 10:
            for odx, ody in RL_SELF_AND_ADJACENT:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c and c.resource_type and c.owner_id != self.name and c.structure != 'Wall':
                    return 3  # CAPTURE

        # 3. Атака ближайшего врага
        if self.balance.get("energy", 0) >= 5:
            for a in all_agents:
                if a.name != self.name and not a.is_dead:
                    if abs(a.position.x - self.position.x) <= 1 and abs(a.position.y - self.position.y) <= 1:
                        return 4  # ATTACK

        # 4. Изучение технологий
        priority_techs = [
            "economy_lvl_1", "combat_lvl_1", "logistics_lvl_1",
            "economy_lvl_2", "combat_lvl_2", "logistics_lvl_2",
            "economy_lvl_3", "combat_lvl_3", "logistics_lvl_3",
        ]
        for tech in priority_techs:
            if tech not in self.unlocked_techs:
                parent = TECH_TREE[tech]["parent"]
                if parent is None or parent in self.unlocked_techs:
                    if self.balance.get("imagination", 0) >= TECH_TREE[tech]["cost"]:
                        return 6  # RESEARCH
                    break

        # 5. Сбор лута
        has_any_loot = any(any(v > 0 for v in c.loot.values()) for row in map_core.grid for c in row)
        if has_any_loot and self.balance.get("energy", 0) >= 5:
            return 7  # GATHER_LOOT

        # 6. Движение к ничейной шахте
        unowned_mine = any(c.resource_type and c.owner_id != self.name for row in map_core.grid for c in row)
        if unowned_mine and self.balance.get("energy", 0) >= 5:
            return 0  # MOVE_TO_MINE

        return 8  # PASS

    def _convert_rl_action_to_json(self, action_idx: int, map_core: MapCore, all_agents: List['Stage2AI']) -> dict:
        """Переводит индекс действия RL (0..8) в JSON-формат для ArbitorPhysical.execute_action()."""
        action_name = RL_ACTION_NAMES[action_idx] if 0 <= action_idx < len(RL_ACTION_NAMES) else f"ACTION_{action_idx}"
        thought_str = f"RL Policy Network decision: {action_name}"
        compass_str = "Максимизация функции полезности V(s)"

        # 0: MOVE_TO_MINE
        if action_idx == 0:
            best_target = None
            best_dist = float('inf')
            for row in map_core.grid:
                for cell in row:
                    if cell.resource_type and cell.owner_id != self.name:
                        d = abs(cell.pos.x - self.position.x) + abs(cell.pos.y - self.position.y)
                        if d < best_dist:
                            best_dist = d
                            best_target = cell
            if best_target:
                d = self._get_move_direction(best_target.pos.x, best_target.pos.y, map_core, all_agents)
                if d:
                    return {
                        "action": "MOVE",
                        "params": {"direction": d},
                        "thought": f"{thought_str} -> к шахте ({best_target.pos.x}, {best_target.pos.y})",
                        "new_compass": compass_str
                    }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (шахт нет или заблокировано)", "new_compass": compass_str}

        # 1: MOVE_TO_ENEMY
        elif action_idx == 1:
            enemy = None
            min_dist = float('inf')
            for a in all_agents:
                if a.name != self.name and not a.is_dead:
                    d = abs(a.position.x - self.position.x) + abs(a.position.y - self.position.y)
                    if d < min_dist:
                        min_dist = d
                        enemy = a
            if enemy:
                d = self._get_move_direction(enemy.position.x, enemy.position.y, map_core, all_agents)
                if d:
                    return {
                        "action": "MOVE",
                        "params": {"direction": d},
                        "thought": f"{thought_str} -> сближение с врагом {enemy.name}",
                        "new_compass": compass_str
                    }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (врагов нет или заблокировано)", "new_compass": compass_str}

        # 2: MOVE_TO_ENERGY_MINE
        elif action_idx == 2:
            best_target = None
            best_dist = float('inf')
            for row in map_core.grid:
                for cell in row:
                    if cell.resource_type and cell.resource_type.lower() == 'energy' and cell.owner_id != self.name:
                        d = abs(cell.pos.x - self.position.x) + abs(cell.pos.y - self.position.y)
                        if d < best_dist:
                            best_dist = d
                            best_target = cell
            if best_target:
                d = self._get_move_direction(best_target.pos.x, best_target.pos.y, map_core, all_agents)
                if d:
                    return {
                        "action": "MOVE",
                        "params": {"direction": d},
                        "thought": f"{thought_str} -> к энергошахте ({best_target.pos.x}, {best_target.pos.y})",
                        "new_compass": compass_str
                    }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (энергошахта недоступна)", "new_compass": compass_str}

        # 3: CAPTURE
        elif action_idx == 3:
            best_cell = None
            for odx, ody in RL_SELF_AND_ADJACENT:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c and c.resource_type and c.owner_id != self.name and c.structure != 'Wall':
                    enemy_on_cell = any(a.position.x == c.pos.x and a.position.y == c.pos.y and a.name != self.name and not a.is_dead for a in all_agents)
                    if not enemy_on_cell:
                        if best_cell is None:
                            best_cell = c
                        if c.resource_type.lower() == 'energy':
                            best_cell = c
                            break
            if best_cell:
                return {
                    "action": "CAPTURE",
                    "params": {"target_x": best_cell.pos.x, "target_y": best_cell.pos.y},
                    "thought": f"{thought_str} -> захват шахты ({best_cell.pos.x}, {best_cell.pos.y})",
                    "new_compass": compass_str
                }
            # Если рядом нет шахты, подходим к ближайшей
            best_m = None
            best_d = float('inf')
            for row in map_core.grid:
                for cell in row:
                    if cell.resource_type and cell.owner_id != self.name:
                        d = abs(cell.pos.x - self.position.x) + abs(cell.pos.y - self.position.y)
                        if d < best_d:
                            best_d = d
                            best_m = cell
            if best_m:
                d = self._get_move_direction(best_m.pos.x, best_m.pos.y, map_core, all_agents)
                if d:
                    return {"action": "MOVE", "params": {"direction": d}, "thought": f"{thought_str} -> подход к шахте ({best_m.pos.x}, {best_m.pos.y})", "new_compass": compass_str}
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (нет цели для захвата)", "new_compass": compass_str}

        # 4: ATTACK
        elif action_idx == 4:
            # Приоритет 1: враг рядом
            for a in all_agents:
                if a.name != self.name and not a.is_dead:
                    if abs(a.position.x - self.position.x) <= 1 and abs(a.position.y - self.position.y) <= 1:
                        return {
                            "action": "ATTACK",
                            "params": {"target_x": a.position.x, "target_y": a.position.y},
                            "thought": f"{thought_str} -> атака врага {a.name}",
                            "new_compass": compass_str
                        }
            # Приоритет 2: стена или вражеская шахта рядом
            for odx, ody in RL_ADJACENT_OFFSETS:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c:
                    if c.structure == 'Wall':
                        return {
                            "action": "ATTACK",
                            "params": {"target_x": c.pos.x, "target_y": c.pos.y},
                            "thought": f"{thought_str} -> атака стены ({c.pos.x}, {c.pos.y})",
                            "new_compass": compass_str
                        }
                    elif c.resource_type and c.owner_id not in (self.name, None):
                        return {
                            "action": "ATTACK",
                            "params": {"target_x": c.pos.x, "target_y": c.pos.y},
                            "thought": f"{thought_str} -> атака вражеской шахты ({c.pos.x}, {c.pos.y})",
                            "new_compass": compass_str
                        }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (нет целей для атаки)", "new_compass": compass_str}

        # 5: BUILD
        elif action_idx == 5:
            for odx, ody in RL_ADJACENT_OFFSETS:
                c = map_core.get_cell(self.position.x + odx, self.position.y + ody)
                if c and c.structure is None and c.resource_type is None:
                    occupied = any(a.position.x == c.pos.x and a.position.y == c.pos.y and not a.is_dead for a in all_agents)
                    if not occupied:
                        return {
                            "action": "BUILD",
                            "params": {"target_x": c.pos.x, "target_y": c.pos.y},
                            "thought": f"{thought_str} -> постройка стены на ({c.pos.x}, {c.pos.y})",
                            "new_compass": compass_str
                        }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (нет места для постройки)", "new_compass": compass_str}

        # 6: RESEARCH
        elif action_idx == 6:
            priority_techs = [
                "economy_lvl_1", "combat_lvl_1", "logistics_lvl_1",
                "economy_lvl_2", "combat_lvl_2", "logistics_lvl_2",
                "economy_lvl_3", "combat_lvl_3", "logistics_lvl_3",
            ]
            for tech in priority_techs:
                if tech not in self.unlocked_techs:
                    parent = TECH_TREE[tech]["parent"]
                    if parent is None or parent in self.unlocked_techs:
                        if self.balance.get("imagination", 0) >= TECH_TREE[tech]["cost"]:
                            return {
                                "action": "RESEARCH",
                                "params": {"tech": tech},
                                "thought": f"{thought_str} -> исследование {tech}",
                                "new_compass": compass_str
                            }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (не хватает ресурсов на технологию)", "new_compass": compass_str}

        # 7: GATHER_LOOT
        elif action_idx == 7:
            best_loot = None
            best_dist = float('inf')
            for row in map_core.grid:
                for cell in row:
                    if cell.loot and any(v > 0 for v in cell.loot.values()):
                        d = abs(cell.pos.x - self.position.x) + abs(cell.pos.y - self.position.y)
                        if d < best_dist:
                            best_dist = d
                            best_loot = cell
            if best_loot:
                d = self._get_move_direction(best_loot.pos.x, best_loot.pos.y, map_core, all_agents)
                if d:
                    return {
                        "action": "MOVE",
                        "params": {"direction": d},
                        "thought": f"{thought_str} -> к луту ({best_loot.pos.x}, {best_loot.pos.y})",
                        "new_compass": compass_str
                    }
            return {"action": "PASS", "params": {}, "thought": f"{thought_str} (лута нет на карте)", "new_compass": compass_str}

        # 8: PASS
        return {
            "action": "PASS",
            "params": {},
            "thought": thought_str,
            "new_compass": compass_str
        }

    async def get_action_from_rl(self, map_core: MapCore, all_agents: Optional[List['Stage2AI']] = None) -> dict:
        """Получает действие от обученной RL модели (PPO/DQN) или эвристического фоллбэка."""
        if all_agents is None:
            all_agents = [self]

        action_idx = None
        if self.rl_model is not None:
            try:
                # Определение размерности наблюдений, требуемой моделью
                req_dim = 315
                if hasattr(self.rl_model, "observation_space") and hasattr(self.rl_model.observation_space, "shape"):
                    req_dim = self.rl_model.observation_space.shape[0]

                obs = self._build_rl_obs(map_core, all_agents, target_dim=req_dim)
                action_pred, _ = self.rl_model.predict(obs, deterministic=True)
                action_idx = int(action_pred)
            except Exception as e:
                logger.warning(f"[{self.name}] Ошибка инференса RL модели: {e}. Переход на эвристику.")
                action_idx = None

        if action_idx is None:
            action_idx = self._heuristic_policy(map_core, all_agents)

        return self._convert_rl_action_to_json(action_idx, map_core, all_agents)

    async def get_action_from_llm(self, map_core: MapCore, all_agents: Optional[List['Stage2AI']] = None) -> dict:
        # Если агент является RL-агентом, направляем ход в нейросетевую политику
        if getattr(self, 'is_rl', False):
            return await self.get_action_from_rl(map_core, all_agents)

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

    def record_action_result(self, action_data: dict, result_msg: str):
        """Регистрирует действие и обновляет научные когнитивные метрики агента."""
        self.total_actions += 1

        if not isinstance(action_data, dict):
            action_data = {}
        action_name = str(action_data.get("action", "PASS")).upper().strip()
        params = action_data.get("params", {})
        if not isinstance(params, dict):
            params = {}

        if action_name == "ATTACK":
            self.attacks_count += 1
        elif action_name == "CAPTURE":
            self.captures_count += 1

        # Определение невалидного/отклоненного действия
        res_lower = str(result_msg).lower()
        invalid_keywords = [
            "недостаточно", "стена или край", "нельзя", "ошибка", "не существует",
            "вне зоны", "заблокировано", "невозможно", "нет подходящей цели",
            "нет казино", "нет цели", "нет живого", "уже принадлежит",
            "уже изучена", "сначала нужно", "край карты", "слишком далеко",
            "здесь нет шахты", "не найден или мёртв", "неверные координаты",
            "неверный тип", "здесь уже есть постройка", "вы мертвы"
        ]
        if any(kw in res_lower for kw in invalid_keywords):
            self.invalid_actions += 1

        # Детекция зацикливания (Fixation Loop)
        # Сигнатура: (действие, направление, target_x, target_y, tech, resource, x, y)
        sig = (
            action_name,
            params.get("direction"),
            params.get("target_x"),
            params.get("target_y"),
            params.get("tech"),
            params.get("resource"),
            self.position.x,
            self.position.y
        )
        self.recent_action_history.append(sig)
        if len(self.recent_action_history) > 3:
            self.recent_action_history.pop(0)

        if len(self.recent_action_history) == 3:
            if self.recent_action_history[0] == self.recent_action_history[1] == self.recent_action_history[2]:
                self.fixation_loops += 1
                logger.warning(f"[{self.name}] ⚠️ ДЕТЕКТОР СБОЕВ: Обнаружен Fixation Loop #{self.fixation_loops} на координатах ({self.position.x}, {self.position.y})!")

    def get_metrics(self) -> dict:
        """Возвращает словарь с рассчитанными научными показателями агента."""
        total = max(self.total_actions, 1)
        combat_total = self.attacks_count + self.captures_count
        aggression_index = round((self.attacks_count / combat_total) * 100, 1) if combat_total > 0 else 0.0
        fixation_rate = round((self.fixation_loops / total) * 100, 1) if self.total_actions > 0 else 0.0
        invalid_rate = round((self.invalid_actions / total) * 100, 1) if self.total_actions > 0 else 0.0
        return {
            "total_actions": self.total_actions,
            "invalid_actions": self.invalid_actions,
            "attacks_count": self.attacks_count,
            "captures_count": self.captures_count,
            "deaths_count": self.deaths_count,
            "fixation_loops": self.fixation_loops,
            "aggression_index": aggression_index,
            "fixation_rate": fixation_rate,
            "invalid_rate": invalid_rate
        }


class RLAgent(Stage2AI):
    """Специализированный класс RL-агента (PPO/DQN), наследующий Stage2AI."""
    def __init__(
        self,
        name: str = "RL-PPO-Bot",
        api_key: str = "",
        model: str = "PPO-Policy",
        start_pos: Position = Position(x=0, y=0),
        init_income: dict = None,
        rl_model_path: str = "rl_models/best/best_model"
    ):
        if init_income is None:
            init_income = {"matter": 10, "energy": 10, "imagination": 10}
        super().__init__(
            name=name,
            api_key=api_key,
            model=model,
            start_pos=start_pos,
            init_income=init_income,
            is_human=False,
            is_rl=True,
            rl_model_path=rl_model_path
        )


# --- Валидатор физических действий ---

class ArbitorPhysical:
    def is_adjacent(self, pos1: Position, pos2: Position) -> bool:
        dx = abs(pos1.x - pos2.x)
        dy = abs(pos1.y - pos2.y)
        return (dx <= 1 and dy <= 1)

    async def execute_action(self, avatar: Stage2AI, action_data: dict, map_core: MapCore, all_agents: List[Stage2AI]) -> str:
        result = await self._execute_action_inner(avatar, action_data, map_core, all_agents)
        if hasattr(avatar, 'record_action_result'):
            avatar.record_action_result(action_data, result)
        return result

    async def _execute_action_inner(self, avatar: Stage2AI, action_data: dict, map_core: MapCore, all_agents: List[Stage2AI]) -> str:
        async with map_core.lock:
            if avatar.is_dead:
                return "Вы мертвы и не можете действовать."
                
            if not isinstance(action_data, dict):
                action_data = {}
            action = action_data.get("action", "PASS")
            action = action.upper().strip()
            params = action_data.get("params", {})
            
            if action == "RESEARCH":
                tech = params.get("tech")
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
                
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели."
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
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели."
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Цель вне зоны досягаемости."
                    
                target_cell = map_core.get_cell(tx, ty)
                enemy = next((a for a in all_agents if a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead), None)
                
                if enemy:
                    enemy.hp -= dmg
                    if enemy.hp <= 0:
                        enemy.is_dead = True
                        enemy.deaths_count = getattr(enemy, 'deaths_count', 0) + 1
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
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели."
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)):
                    return "Цель вне зоны досягаемости."
                
                build_cost = 14 if "economy_lvl_1" in avatar.unlocked_techs else 20
                if avatar.balance["matter"] < build_cost:
                    return f"Недостаточно Материи (нужно {build_cost}) для постройки стены."
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell or target_cell.structure in ('Wall', 'Casino'):
                    return "Здесь уже есть постройка или край карты."
                if target_cell.resource_type is not None:
                    return "Нельзя строить стену на шахте."
                
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
                    
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели."
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
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели."
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Слишком далеко для захвата."
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell: return "Край карты."
                
                enemy_here = any(a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead for a in all_agents)
                if enemy_here: return "Невозможно захватить: на клетке враг!"
                if target_cell.structure == 'Wall': return "Невозможно захватить: мешает стена!"
                
                if target_cell.resource_type:
                    if target_cell.owner_id == avatar.name:
                        return "Эта шахта уже принадлежит вам."
                    avatar.balance["imagination"] -= 10
                    target_cell.owner_id = avatar.name
                    return f"Шахта на ({tx}, {ty}) перепрограммирована и захвачена."
                return "Здесь нет шахты для захвата."

            elif action == "GAMBLE":
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели."
                bet = params.get("bet", 0)
                resource = params.get("resource", "matter").lower()
                
                if resource not in ["matter", "energy", "imagination"]:
                    return "Неверный тип ресурса для ставки."
                
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Казино вне зоны досягаемости."
                    
                target_cell = map_core.get_cell(tx, ty)
                if not target_cell or target_cell.structure != 'Casino':
                    return f"На ({tx}, {ty}) нет казино!"
                    
                if not isinstance(bet, (int, float)) or bet < 10:
                    return "Минимальная ставка: 10 ресурсов."
                bet = int(bet)
                
                if avatar.balance[resource] < bet:
                    return f"Недостаточно {resource} для ставки {bet}."
                
                # Снимаем ставку
                avatar.balance[resource] -= bet
                
                # Бросок! 
                roll = random.random()
                
                if roll < 0.05:  # 5% — ДЖЕКПОТ!
                    winnings = bet * 3 + target_cell.casino_jackpot
                    avatar.balance[resource] += winnings
                    jackpot_won = target_cell.casino_jackpot
                    target_cell.casino_jackpot = random.randint(50, 150)  # Reset jackpot
                    return f"🎰🎰🎰 ДЖЕКПОТ!!! Выигрыш: {winnings} {resource} (3x ставка + {jackpot_won} джекпот)! Невероятная удача!"
                elif roll < 0.45:  # 40% — ВЫИГРЫШ (2x)
                    winnings = bet * 2
                    avatar.balance[resource] += winnings
                    return f"🎰 ВЫИГРЫШ! Получено {winnings} {resource} (2x ставка). Удача улыбнулась!"
                else:  # 55% — ПРОИГРЫШ
                    # Часть проигрыша идёт в джекпот
                    target_cell.casino_jackpot += int(bet * 0.3)
                    return f"🎰 ПРОИГРЫШ! Потеряно {bet} {resource}. Джекпот вырос до {target_cell.casino_jackpot}."

            elif action == "DIPLOMACY":
                target_agent = params.get("target_agent", "ALL")
                message = str(params.get("message", "")).strip()
                if not message:
                    return "Ошибка дипломатии: сообщение не может быть пустым."
                
                target_str = str(target_agent).strip()
                delivered = 0

                if target_str.upper() == "ALL":
                    for a in all_agents:
                        if a.name != avatar.name and not a.is_dead:
                            inbox_entry = f"[{avatar.name} -> ВСЕМ]: {message}"
                            if not hasattr(a, 'inbox'):
                                a.inbox = []
                            a.inbox.append(inbox_entry)
                            if len(a.inbox) > 3:
                                a.inbox.pop(0)
                            delivered += 1
                    
                    log_entry = {
                        "sender": avatar.name,
                        "receiver": "ALL",
                        "message": message,
                        "type": "broadcast",
                        "time": time.strftime("%H:%M:%S")
                    }
                    map_core.diplomacy_log.append(log_entry)
                    if len(map_core.diplomacy_log) > 100:
                        map_core.diplomacy_log.pop(0)
                    
                    logger.info(f"🕊️ [ДИПЛОМАТИЯ] {avatar.name} -> ВСЕМ: \"{message}\"")
                    return f"Дипломатическое обращение отправлено ВСЕМ ({delivered} получ.): \"{message}\""
                else:
                    recipient = next((a for a in all_agents if a.name.lower() == target_str.lower() and not a.is_dead), None)
                    if not recipient:
                        return f"Агент '{target_str}' не найден или мёртв."
                    
                    inbox_entry = f"[{avatar.name} -> ВАМ]: {message}"
                    if not hasattr(recipient, 'inbox'):
                        recipient.inbox = []
                    recipient.inbox.append(inbox_entry)
                    if len(recipient.inbox) > 3:
                        recipient.inbox.pop(0)

                    log_entry = {
                        "sender": avatar.name,
                        "receiver": recipient.name,
                        "message": message,
                        "type": "direct",
                        "time": time.strftime("%H:%M:%S")
                    }
                    map_core.diplomacy_log.append(log_entry)
                    if len(map_core.diplomacy_log) > 100:
                        map_core.diplomacy_log.pop(0)

                    logger.info(f"🕊️ [ДИПЛОМАТИЯ] {avatar.name} -> {recipient.name}: \"{message}\"")
                    return f"Дипломатическое сообщение отправлено {recipient.name}: \"{message}\""

            elif action == "GIVE":
                try:
                    tx = int(params.get("target_x", 0))
                    ty = int(params.get("target_y", 0))
                except (TypeError, ValueError):
                    return "Неверные координаты цели для передачи ресурсов."
                
                if not self.is_adjacent(avatar.position, Position(x=tx, y=ty)) and not (avatar.position.x == tx and avatar.position.y == ty):
                    return "Цель вне зоны досягаемости (передача возможна только соседним клеткам)."
                
                recipient = next((a for a in all_agents if a.position.x == tx and a.position.y == ty and a.name != avatar.name and not a.is_dead), None)
                if not recipient:
                    return f"На ({tx}, {ty}) нет живого союзника для передачи ресурсов."
                
                resource = str(params.get("resource", "matter")).lower()
                if resource not in ["matter", "energy", "imagination"]:
                    return "Неверный тип ресурса для передачи (доступны: matter, energy, imagination)."
                
                try:
                    amount = int(params.get("amount", 0))
                except (TypeError, ValueError):
                    return "Неверное количество ресурса."
                
                if amount <= 0:
                    return "Количество передаваемого ресурса должно быть больше 0."
                
                if avatar.balance.get(resource, 0) < amount:
                    return f"Недостаточно {resource} (в наличии: {avatar.balance.get(resource, 0)}, запрошено: {amount})."
                
                # Передаем ресурс
                avatar.balance[resource] -= amount
                recipient.balance[resource] += amount
                
                inbox_msg = f"[{avatar.name}]: Передал вам {amount} {resource}!"
                if not hasattr(recipient, 'inbox'):
                    recipient.inbox = []
                recipient.inbox.append(inbox_msg)
                if len(recipient.inbox) > 3:
                    recipient.inbox.pop(0)
                
                log_entry = {
                    "sender": avatar.name,
                    "receiver": recipient.name,
                    "message": f"Передача ресурсов: {amount} {resource}",
                    "type": "transfer",
                    "resource": resource,
                    "amount": amount,
                    "time": time.strftime("%H:%M:%S")
                }
                map_core.diplomacy_log.append(log_entry)
                if len(map_core.diplomacy_log) > 100:
                    map_core.diplomacy_log.pop(0)
                
                logger.info(f"🤝 [РЕСУРСЫ] {avatar.name} передал {amount} {resource} агенту {recipient.name} на ({tx}, {ty})")
                return f"Успешно передано {amount} {resource} союзнику {recipient.name}!"

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
                agent.respawn_timer -= 1
                if agent.respawn_timer <= 0:
                    agent.is_dead = False
                    agent.hp = 100
                    agent.position.x = agent.base_position.x
                    agent.position.y = agent.base_position.y
                    agent.respawn_timer = 0
                    logging.info(f"{agent.name} respawned at ({agent.base_position.x}, {agent.base_position.y})")
                else:
                    await asyncio.sleep(2.0)
                    continue

            turn_number += 1

            # Агент думает (ждем ответа LLM или инференса RL)
            action_data = await agent.get_action_from_llm(map_core, all_agents)

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
    world_map.spawn_casinos(2)
    arbiter = ArbitorPhysical()

    agents = []
    for i, agent_data in enumerate(data["agents"]):
        x = agent_data.get("start_x", 0 if i == 0 else 6)
        y = agent_data.get("start_y", 0 if i == 0 else 6)
        agents.append(Stage2AI(agent_data["name"], agent_data["api_key"], agent_data["model"], Position(x=x, y=y), agent_data.get("income", {})))

    # Запускаем отрисовку и каждого агента как отдельные независимые таски
    tasks = [asyncio.create_task(map_render_loop(world_map, agents))]
    for agent in agents:
        tasks.append(asyncio.create_task(agent_loop(agent, world_map, arbiter, agents)))

    # Ждем завершения (по сути бесконечно)
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main_simulation())
    except KeyboardInterrupt:
        logger.info("Симуляция остановлена пользователем.")
