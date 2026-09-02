"""
rl_env.py — Gymnasium-среда для обучения RL-агента в AI Sandbox.

Среда оборачивает логику игры (карта 7×7, ресурсы, бой, захват шахт)
в стандартный интерфейс Gymnasium для Stable-Baselines3.

Пространство наблюдений: плоский вектор float32 (315 элементов)
Пространство действий:   Discrete(39)
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import random
from typing import Optional, Tuple, Dict, Any, List


# ============================================================
# Константы
# ============================================================

MAP_SIZE = 7
MAX_RESOURCE = 5000  # порог нормализации (= условие победы Singularity)

# Смещения для 8 смежных клеток
ADJACENT_OFFSETS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

# 9 клеток: 8 смежных + текущая позиция (для захвата)
SELF_AND_ADJACENT = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),  (0, 0),  (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

# Дерево технологий
TECH_NAMES = [
    "combat_lvl_1", "combat_lvl_2", "combat_lvl_3",
    "economy_lvl_1", "economy_lvl_2", "economy_lvl_3",
    "logistics_lvl_1", "logistics_lvl_2", "logistics_lvl_3",
]

TECH_TREE = {
    "combat_lvl_1":    {"cost": 150, "parent": None},
    "combat_lvl_2":    {"cost": 500, "parent": "combat_lvl_1"},
    "combat_lvl_3":    {"cost": 1500, "parent": "combat_lvl_2"},
    "economy_lvl_1":   {"cost": 150, "parent": None},
    "economy_lvl_2":   {"cost": 500, "parent": "economy_lvl_1"},
    "economy_lvl_3":   {"cost": 1500, "parent": "economy_lvl_2"},
    "logistics_lvl_1": {"cost": 150, "parent": None},
    "logistics_lvl_2": {"cost": 500, "parent": "logistics_lvl_1"},
    "logistics_lvl_3": {"cost": 1500, "parent": "logistics_lvl_2"},
}

# Маппинг: action_index → тип действия
#  0-3:   MOVE (N, S, E, W)
#  4-11:  ATTACK (8 смежных)
# 12-20:  CAPTURE (9: смежные + текущая)
# 21-28:  BUILD (8 смежных)
# 29-37:  RESEARCH (9 технологий)
# 38:     PASS
NUM_ACTIONS = 39


# ============================================================
# Внутренние структуры (упрощённая версия world.py)
# ============================================================

class SimpleCell:
    """Одна клетка карты."""
    __slots__ = ['x', 'y', 'owner', 'resource_type', 'mine_level',
                 'mine_hp', 'structure', 'wall_hp', 'loot']

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.owner: Optional[str] = None
        self.resource_type: Optional[str] = None  # 'matter', 'energy', 'imagination'
        self.mine_level: int = 0
        self.mine_hp: int = 0
        self.structure: Optional[str] = None      # 'wall'
        self.wall_hp: int = 0
        self.loot: Dict[str, int] = {"matter": 0, "energy": 0, "imagination": 0}

    def copy(self) -> 'SimpleCell':
        c = SimpleCell(self.x, self.y)
        c.owner = self.owner
        c.resource_type = self.resource_type
        c.mine_level = self.mine_level
        c.mine_hp = self.mine_hp
        c.structure = self.structure
        c.wall_hp = self.wall_hp
        c.loot = dict(self.loot)
        return c


class SimpleAgent:
    """Состояние агента."""
    def __init__(self, name: str, x: int, y: int):
        self.name = name
        self.x = x
        self.y = y
        self.hp = 100
        self.is_dead = False
        self.respawn_timer = 0
        self.home_x = x
        self.home_y = y
        self.balance: Dict[str, int] = {"matter": 50, "energy": 50, "imagination": 50}
        self.techs: List[str] = []


class SimpleMap:
    """Игровая карта."""
    def __init__(self, size: int = MAP_SIZE):
        self.size = size
        self.grid: List[List[SimpleCell]] = [
            [SimpleCell(x, y) for y in range(size)] for x in range(size)
        ]

    def get_cell(self, x: int, y: int) -> Optional[SimpleCell]:
        if 0 <= x < self.size and 0 <= y < self.size:
            return self.grid[x][y]
        return None

    def spawn_mines(self):
        """Размещает 9 шахт (по 3 каждого типа)."""
        resources = ['matter'] * 3 + ['energy'] * 3 + ['imagination'] * 3
        cells = [cell for row in self.grid for cell in row]
        random.shuffle(cells)
        for i, res in enumerate(resources):
            cells[i].resource_type = res
            cells[i].mine_level = 1
            cells[i].mine_hp = 50

    def count_mines_owned_by(self, owner: str) -> int:
        return sum(1 for row in self.grid for c in row
                   if c.resource_type and c.owner == owner)

    def total_mines(self) -> int:
        return sum(1 for row in self.grid for c in row if c.resource_type)


# ============================================================
# Gymnasium Environment
# ============================================================

class AISandboxEnv(gym.Env):
    """
    RL-среда AI Sandbox.

    Observation (315 float32):
      - Карта 7×7 × 6 каналов = 294
        Каналы: owner, has_resource, resource_type, mine_level, structure, has_loot
      - Агент: x, y, hp, matter, energy, imagination = 6
      - Враг:  x, y, hp, matter, energy, imagination = 6
      - Технологии: 9 бинарных значений

    Action (Discrete 39):
      0-3:   MOVE N/S/E/W
      4-11:  ATTACK (8 смежных)
      12-20: CAPTURE (9 вокруг)
      21-28: BUILD (8 смежных)
      29-37: RESEARCH (9 технологий)
      38:    PASS
    """
    metadata = {"render_modes": ["human", "ansi"], "render_fps": 2}

    def __init__(self, render_mode=None, max_steps=500, hunger=3):
        super().__init__()
        self.render_mode = render_mode
        self.max_steps = max_steps
        self.hunger = hunger

        obs_size = MAP_SIZE * MAP_SIZE * 6 + 6 + 6 + 9  # = 315
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(obs_size,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(NUM_ACTIONS)

        # State
        self.game_map: Optional[SimpleMap] = None
        self.player: Optional[SimpleAgent] = None
        self.bot: Optional[SimpleAgent] = None
        self.steps = 0

    # ----------------------------------------------------------
    # Gymnasium API
    # ----------------------------------------------------------

    def reset(self, *, seed=None, options=None) -> Tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        self.game_map = SimpleMap(MAP_SIZE)
        self.game_map.spawn_mines()

        self.player = SimpleAgent("player", 0, 0)
        self.bot = SimpleAgent("bot", MAP_SIZE - 1, MAP_SIZE - 1)
        self.steps = 0

        return self._get_obs(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        reward = 0.0
        terminated = False
        truncated = False
        info = {}
        self.steps += 1

        # 1) Ход игрока
        if not self.player.is_dead:
            r, i = self._execute_action(self.player, self.bot, action)
            reward += r
            info.update(i)

        # 2) Ход бота
        if not self.bot.is_dead:
            self._bot_step()

        # 3) Доход от шахт + голод
        self._apply_income(self.player)
        self._apply_income(self.bot)

        # 4) Респаун мёртвых
        self._handle_respawn(self.player)
        self._handle_respawn(self.bot)

        # 5) Проверка победы
        win = self._check_win()
        if win == "player":
            reward += 100.0
            terminated = True
            info["result"] = "WIN"
        elif win == "bot":
            reward -= 50.0
            terminated = True
            info["result"] = "LOSE"

        # 6) Штраф за время
        reward -= 0.01

        # 7) Лимит ходов
        if self.steps >= self.max_steps:
            truncated = True
            info["result"] = info.get("result", "TIMEOUT")

        if self.render_mode == "human":
            self.render()

        return self._get_obs(), reward, terminated, truncated, info

    def render(self):
        """ASCII-визуализация карты."""
        if not self.game_map:
            return
        symbols = {None: "·", "matter": "M", "energy": "E", "imagination": "I"}
        lines = [f"\n=== Step {self.steps} ==="]
        lines.append(f"Player HP:{self.player.hp} M:{self.player.balance['matter']} "
                      f"E:{self.player.balance['energy']} I:{self.player.balance['imagination']}")
        lines.append(f"Bot    HP:{self.bot.hp} M:{self.bot.balance['matter']} "
                      f"E:{self.bot.balance['energy']} I:{self.bot.balance['imagination']}")
        lines.append("  " + " ".join(str(i) for i in range(self.game_map.size)))

        for y in range(self.game_map.size):
            row = f"{y} "
            for x in range(self.game_map.size):
                cell = self.game_map.grid[x][y]
                if self.player.x == x and self.player.y == y and not self.player.is_dead:
                    row += "P "
                elif self.bot.x == x and self.bot.y == y and not self.bot.is_dead:
                    row += "B "
                elif cell.structure == "wall":
                    row += "# "
                elif cell.resource_type:
                    ch = cell.resource_type[0].upper()
                    if cell.owner == "player":
                        ch = ch.lower()  # owned by player = lowercase
                    elif cell.owner == "bot":
                        ch = f"\033[91m{ch}\033[0m"  # red for bot
                    row += ch + " "
                else:
                    row += ". "
            lines.append(row)

        print("\n".join(lines))

    # ----------------------------------------------------------
    # Observation
    # ----------------------------------------------------------

    def _get_obs(self) -> np.ndarray:
        """Конвертирует состояние игры в плоский вектор [0..1]."""
        obs = []

        # Map channels: 7×7 × 6 = 294
        for y in range(MAP_SIZE):
            for x in range(MAP_SIZE):
                cell = self.game_map.grid[x][y]
                # 1. Owner: 0=none, 0.5=player, 1.0=bot
                owner_val = 0.0
                if cell.owner == "player":
                    owner_val = 0.5
                elif cell.owner == "bot":
                    owner_val = 1.0
                obs.append(owner_val)

                # 2. Has resource mine
                obs.append(1.0 if cell.resource_type else 0.0)

                # 3. Resource type: 0=none, 0.33=matter, 0.66=energy, 1.0=imagination
                rt = 0.0
                if cell.resource_type == "matter": rt = 0.33
                elif cell.resource_type == "energy": rt = 0.66
                elif cell.resource_type == "imagination": rt = 1.0
                obs.append(rt)

                # 4. Mine level (0-3 → 0-1)
                obs.append(min(cell.mine_level / 3.0, 1.0))

                # 5. Structure: 0=none, 1.0=wall
                obs.append(1.0 if cell.structure == "wall" else 0.0)

                # 6. Has loot
                has_loot = 1.0 if any(v > 0 for v in cell.loot.values()) else 0.0
                obs.append(has_loot)

        # Agent state (6 values)
        obs.append(self.player.x / (MAP_SIZE - 1))
        obs.append(self.player.y / (MAP_SIZE - 1))
        obs.append(self.player.hp / 100.0)
        obs.append(min(self.player.balance["matter"] / MAX_RESOURCE, 1.0))
        obs.append(min(self.player.balance["energy"] / MAX_RESOURCE, 1.0))
        obs.append(min(self.player.balance["imagination"] / MAX_RESOURCE, 1.0))

        # Enemy state (6 values)
        obs.append(self.bot.x / (MAP_SIZE - 1))
        obs.append(self.bot.y / (MAP_SIZE - 1))
        obs.append(self.bot.hp / 100.0 if not self.bot.is_dead else 0.0)
        obs.append(min(self.bot.balance["matter"] / MAX_RESOURCE, 1.0))
        obs.append(min(self.bot.balance["energy"] / MAX_RESOURCE, 1.0))
        obs.append(min(self.bot.balance["imagination"] / MAX_RESOURCE, 1.0))

        # Tech tree (9 binary)
        for tech in TECH_NAMES:
            obs.append(1.0 if tech in self.player.techs else 0.0)

        return np.array(obs, dtype=np.float32)

    # ----------------------------------------------------------
    # Action Execution
    # ----------------------------------------------------------

    def _execute_action(self, agent: SimpleAgent, enemy: SimpleAgent,
                        action_idx: int) -> Tuple[float, dict]:
        """Выполняет действие и возвращает (reward, info)."""
        reward = 0.0
        info = {}

        # === MOVE (0-3) ===
        if 0 <= action_idx <= 3:
            directions = [(0, -1), (0, 1), (1, 0), (-1, 0)]  # N, S, E, W
            dx, dy = directions[action_idx]
            move_cost = 2 if "logistics_lvl_1" in agent.techs else 5
            if agent.balance["energy"] < move_cost:
                reward -= 0.5  # штраф за невалидное действие
                info["action"] = "MOVE_FAIL_energy"
                return reward, info

            nx, ny = agent.x + dx, agent.y + dy
            cell = self.game_map.get_cell(nx, ny)
            if cell is None:
                reward -= 0.5
                info["action"] = "MOVE_FAIL_bounds"
                return reward, info
            if cell.structure == "wall":
                reward -= 0.5
                info["action"] = "MOVE_FAIL_wall"
                return reward, info
            if not enemy.is_dead and enemy.x == nx and enemy.y == ny:
                reward -= 0.5
                info["action"] = "MOVE_FAIL_enemy"
                return reward, info

            agent.balance["energy"] -= move_cost
            agent.x = nx
            agent.y = ny

            # Подбор лута
            for res in ["matter", "energy", "imagination"]:
                if cell.loot.get(res, 0) > 0:
                    agent.balance[res] += cell.loot[res]
                    reward += 2.0
                    cell.loot[res] = 0

            info["action"] = f"MOVE_{['N','S','E','W'][action_idx]}"

        # === ATTACK (4-11) ===
        elif 4 <= action_idx <= 11:
            offset_idx = action_idx - 4
            odx, ody = ADJACENT_OFFSETS[offset_idx]
            tx, ty = agent.x + odx, agent.y + ody

            if agent.balance["energy"] < 5:
                reward -= 0.5
                info["action"] = "ATTACK_FAIL_energy"
                return reward, info

            agent.balance["energy"] -= 5
            cell = self.game_map.get_cell(tx, ty)

            if cell is None:
                reward -= 0.5
                info["action"] = "ATTACK_FAIL_bounds"
                return reward, info

            dmg = 40 if "combat_lvl_1" in agent.techs else 25

            # Атака врага
            if not enemy.is_dead and enemy.x == tx and enemy.y == ty:
                enemy.hp -= dmg
                reward += 3.0
                if enemy.hp <= 0:
                    enemy.is_dead = True
                    enemy.respawn_timer = 5
                    for res in ["matter", "energy", "imagination"]:
                        cell.loot[res] = cell.loot.get(res, 0) + enemy.balance[res]
                        enemy.balance[res] = 0
                    reward += 20.0
                    info["action"] = "ATTACK_KILL"
                else:
                    info["action"] = f"ATTACK_HIT_{enemy.hp}hp"
            # Атака стены
            elif cell.structure == "wall":
                cell.wall_hp -= dmg
                if cell.wall_hp <= 0:
                    cell.structure = None
                    cell.wall_hp = 0
                reward += 0.5
                info["action"] = "ATTACK_WALL"
            # Атака шахты
            elif cell.resource_type and cell.owner != agent.name:
                cell.mine_hp -= dmg
                if cell.mine_hp <= 0:
                    cell.mine_level = max(0, cell.mine_level - 1)
                    if cell.mine_level <= 0:
                        cell.owner = None
                        cell.resource_type = None
                    else:
                        cell.mine_hp = 50 * cell.mine_level
                reward += 1.0
                info["action"] = "ATTACK_MINE"
            else:
                reward -= 0.3
                info["action"] = "ATTACK_EMPTY"

        # === CAPTURE (12-20) ===
        elif 12 <= action_idx <= 20:
            offset_idx = action_idx - 12
            odx, ody = SELF_AND_ADJACENT[offset_idx]
            tx, ty = agent.x + odx, agent.y + ody

            if agent.balance["imagination"] < 10:
                reward -= 0.5
                info["action"] = "CAPTURE_FAIL_imag"
                return reward, info

            cell = self.game_map.get_cell(tx, ty)
            if cell is None:
                reward -= 0.5
                info["action"] = "CAPTURE_FAIL_bounds"
                return reward, info

            if not enemy.is_dead and enemy.x == tx and enemy.y == ty:
                reward -= 0.5
                info["action"] = "CAPTURE_FAIL_enemy"
                return reward, info

            if cell.structure == "wall":
                reward -= 0.5
                info["action"] = "CAPTURE_FAIL_wall"
                return reward, info

            if cell.resource_type:
                agent.balance["imagination"] -= 10
                old_owner = cell.owner
                cell.owner = agent.name
                if old_owner != agent.name:
                    reward += 8.0  # Захват новой шахты — большая награда
                else:
                    reward -= 0.3  # Уже наша
                info["action"] = "CAPTURE_MINE"
            else:
                reward -= 0.3
                info["action"] = "CAPTURE_FAIL_no_mine"

        # === BUILD (21-28) ===
        elif 21 <= action_idx <= 28:
            offset_idx = action_idx - 21
            odx, ody = ADJACENT_OFFSETS[offset_idx]
            tx, ty = agent.x + odx, agent.y + ody

            build_cost = 14 if "economy_lvl_1" in agent.techs else 20
            if agent.balance["matter"] < build_cost:
                reward -= 0.5
                info["action"] = "BUILD_FAIL_matter"
                return reward, info

            cell = self.game_map.get_cell(tx, ty)
            if cell is None or cell.structure:
                reward -= 0.5
                info["action"] = "BUILD_FAIL"
                return reward, info

            if not enemy.is_dead and enemy.x == tx and enemy.y == ty:
                reward -= 0.5
                info["action"] = "BUILD_FAIL_enemy"
                return reward, info

            agent.balance["matter"] -= build_cost
            cell.structure = "wall"
            cell.wall_hp = 100
            cell.owner = agent.name
            reward += 1.0
            info["action"] = "BUILD_WALL"

        # === RESEARCH (29-37) ===
        elif 29 <= action_idx <= 37:
            tech_idx = action_idx - 29
            tech_name = TECH_NAMES[tech_idx]
            tech_data = TECH_TREE[tech_name]

            if tech_name in agent.techs:
                reward -= 0.5
                info["action"] = "RESEARCH_FAIL_done"
                return reward, info

            if tech_data["parent"] and tech_data["parent"] not in agent.techs:
                reward -= 0.5
                info["action"] = "RESEARCH_FAIL_parent"
                return reward, info

            if agent.balance["imagination"] < tech_data["cost"]:
                reward -= 0.5
                info["action"] = "RESEARCH_FAIL_cost"
                return reward, info

            agent.balance["imagination"] -= tech_data["cost"]
            agent.techs.append(tech_name)
            reward += 5.0
            info["action"] = f"RESEARCH_{tech_name}"

        # === PASS (38) ===
        elif action_idx == 38:
            reward -= 0.05  # маленький штраф за бездействие
            info["action"] = "PASS"

        return reward, info

    # ----------------------------------------------------------
    # Bot Logic (простой rule-based противник)
    # ----------------------------------------------------------

    def _bot_step(self):
        """Простой бот: идёт к ближайшей ничейной шахте и захватывает."""
        bot = self.bot
        gm = self.game_map

        # 1) Если рядом есть ничейная шахта — захватить
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cell = gm.get_cell(bot.x + dx, bot.y + dy)
                if (cell and cell.resource_type and cell.owner != bot.name
                        and bot.balance["imagination"] >= 10):
                    if not (not self.player.is_dead and
                            self.player.x == cell.x and self.player.y == cell.y):
                        bot.balance["imagination"] -= 10
                        cell.owner = bot.name
                        return

        # 2) Иначе — двигаться к ближайшей ничейной шахте
        best_dist = 999
        best_cell = None
        for row in gm.grid:
            for cell in row:
                if cell.resource_type and cell.owner != bot.name:
                    dist = abs(cell.x - bot.x) + abs(cell.y - bot.y)
                    if dist < best_dist:
                        best_dist = dist
                        best_cell = cell

        if best_cell and bot.balance["energy"] >= 5:
            dx = np.sign(best_cell.x - bot.x)
            dy = np.sign(best_cell.y - bot.y)
            # Двигаемся по одной оси
            nx, ny = bot.x + int(dx), bot.y + int(dy) if dx == 0 else bot.y
            if dx != 0:
                nx, ny = bot.x + int(dx), bot.y
            else:
                nx, ny = bot.x, bot.y + int(dy)

            target = gm.get_cell(nx, ny)
            if target and target.structure != "wall":
                if self.player.is_dead or not (self.player.x == nx and self.player.y == ny):
                    bot.balance["energy"] -= 5
                    bot.x = nx
                    bot.y = ny
                    # Подбор лута
                    for res in ["matter", "energy", "imagination"]:
                        if target.loot.get(res, 0) > 0:
                            bot.balance[res] += target.loot[res]
                            target.loot[res] = 0

    # ----------------------------------------------------------
    # Income & Hunger
    # ----------------------------------------------------------

    def _apply_income(self, agent: SimpleAgent):
        """Начисляет доход от шахт и отнимает голод."""
        if agent.is_dead:
            return

        # Доход от владеемых шахт: +5 × уровень
        for row in self.game_map.grid:
            for cell in row:
                if cell.resource_type and cell.owner == agent.name:
                    income = 5 * cell.mine_level
                    agent.balance[cell.resource_type] += income

        # Голод: -N энергии за ход
        agent.balance["energy"] -= self.hunger

        # Смерть от голода
        if agent.balance["energy"] < 0:
            agent.is_dead = True
            agent.respawn_timer = 5
            agent.hp = 0
            # Сброс лута на текущую клетку
            cell = self.game_map.get_cell(agent.x, agent.y)
            if cell:
                for res in ["matter", "energy", "imagination"]:
                    cell.loot[res] = cell.loot.get(res, 0) + agent.balance[res]
                    agent.balance[res] = 0

    # ----------------------------------------------------------
    # Respawn
    # ----------------------------------------------------------

    def _handle_respawn(self, agent: SimpleAgent):
        """Обрабатывает таймер возрождения."""
        if agent.is_dead:
            agent.respawn_timer -= 1
            if agent.respawn_timer <= 0:
                agent.is_dead = False
                agent.hp = 100
                agent.x = agent.home_x
                agent.y = agent.home_y
                agent.balance = {"matter": 50, "energy": 50, "imagination": 50}

    # ----------------------------------------------------------
    # Win Conditions
    # ----------------------------------------------------------

    def _check_win(self) -> Optional[str]:
        """Проверяет условия победы. Возвращает 'player', 'bot' или None."""
        for agent in [self.player, self.bot]:
            name = agent.name
            bal = agent.balance

            # Singularity: 5000 каждого ресурса
            if bal["matter"] >= 5000 and bal["energy"] >= 5000 and bal["imagination"] >= 5000:
                return name

            # Monopoly: 80%+ шахт
            total = self.game_map.total_mines()
            if total > 0:
                owned = self.game_map.count_mines_owned_by(name)
                if owned / total >= 0.8:
                    return name

        return None


# Регистрируем среду в Gymnasium
gym.register(
    id="AISandbox-v1",
    entry_point="rl_env:AISandboxEnv",
    max_episode_steps=500,
)
