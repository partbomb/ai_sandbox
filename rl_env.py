"""
rl_env.py — Gymnasium-среда для обучения RL-агента в AI Sandbox.

Среда оборачивает логику игры (карта 7×7, ресурсы, бой, захват шахт)
в стандартный интерфейс Gymnasium для Stable-Baselines3.

Пространство наблюдений: плоский вектор float32 (324 элемента)
  294 (карта) + 6 (игрок) + 6 (враг) + 9 (тех) + 9 (подсказки) = 324
Пространство действий:   Discrete(9)

ИСПРАВЛЕНО (v2):
  1. Суицидальный эксплойт убран: игрок НЕ бросает лут при смерти от голода
  2. BUILD больше не даёт халявный +1.0; требует 2+ шахты
  3. Штраф в _shaped_reward() при захвате шахты теперь пропускается
  4. MOVE_HOME заменён на MOVE_TO_ENERGY_MINE
  5. _move_toward() умеет обходить стены (перпендикулярные кандидаты)
  6. Вектор наблюдений расширен 9 подсказками
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
#  0: MOVE_TO_MINE          — двигаться к ближайшей ничейной шахте (любой)
#  1: MOVE_TO_ENEMY         — двигаться к врагу
#  2: MOVE_TO_ENERGY_MINE   — двигаться к ближайшей энергетической шахте
#  3: CAPTURE               — захватить ближайшую шахту в радиусе
#  4: ATTACK                — атаковать врага/структуру рядом
#  5: BUILD                 — построить стену рядом (требует 2+ шахты)
#  6: RESEARCH              — изучить лучшую доступную технологию
#  7: GATHER_LOOT           — двигаться к ближайшему луту
#  8: PASS                  — пропустить ход
NUM_ACTIONS = 9
ACTION_NAMES = [
    "MOVE_TO_MINE", "MOVE_TO_ENEMY", "MOVE_TO_ENERGY_MINE",
    "CAPTURE", "ATTACK", "BUILD", "RESEARCH",
    "GATHER_LOOT", "PASS"
]


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
        self.balance: Dict[str, int] = {"matter": 100, "energy": 100, "imagination": 100}
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

    def spawn_mines(self, rng=None):
        """Размещает 9 шахт (по 3 каждого типа)."""
        resources = ['matter'] * 3 + ['energy'] * 3 + ['imagination'] * 3
        cells = [cell for row in self.grid for cell in row]
        if rng is not None:
            rng.shuffle(cells)
        else:
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
    RL-среда AI Sandbox (v2 — исправленные баги).

    Observation (324 float32):
      - Карта 7×7 × 6 каналов = 294
        Каналы: owner, has_resource, resource_type, mine_level, structure, has_loot
      - Агент: x, y, hp, matter, energy, imagination = 6
      - Враг:  x, y, hp, matter, energy, imagination = 6
      - Технологии: 9 бинарных значений
      - Подсказки: 9 значений (dx_mine, dy_mine, dx_energy, dy_energy,
                               dx_enemy, dy_enemy, can_capture, can_attack, has_loot_nearby)

    Action (Discrete 9):
      0: MOVE_TO_MINE        — ближайшая любая шахта
      1: MOVE_TO_ENEMY       — к врагу
      2: MOVE_TO_ENERGY_MINE — к энергетической шахте (спасение от голода!)
      3: CAPTURE             — захватить шахту рядом
      4: ATTACK              — атаковать врага/структуру
      5: BUILD               — построить стену (требует 2+ шахты)
      6: RESEARCH            — изучить технологию
      7: GATHER_LOOT         — собрать лут
      8: PASS                — пропустить
    """
    metadata = {"render_modes": ["human", "ansi"], "render_fps": 2}

    def __init__(self, render_mode=None, max_steps=500, hunger=2):
        super().__init__()
        self.render_mode = render_mode
        self.max_steps = max_steps
        self.hunger = hunger

        # 294 (карта) + 6 (игрок) + 6 (враг) + 9 (тех) + 9 (подсказки) = 324
        obs_size = MAP_SIZE * MAP_SIZE * 6 + 6 + 6 + 9 + 9
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(obs_size,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(NUM_ACTIONS)

        # State
        self.game_map: Optional[SimpleMap] = None
        self.player: Optional[SimpleAgent] = None
        self.bot: Optional[SimpleAgent] = None
        self.steps = 0

        # Tracking для shaped rewards
        self._prev_mines_owned = 0
        self._prev_total_resources = 0
        self._prev_dist_to_mine = 0.0

    # ----------------------------------------------------------
    # Gymnasium API
    # ----------------------------------------------------------

    def reset(self, *, seed=None, options=None) -> Tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        self.game_map = SimpleMap(MAP_SIZE)
        self.game_map.spawn_mines(self.np_random)

        self.player = SimpleAgent("player", 0, 0)
        self.bot = SimpleAgent("bot", MAP_SIZE - 1, MAP_SIZE - 1)
        self.steps = 0

        # Reset tracking
        self._prev_mines_owned = 0
        self._prev_total_resources = sum(self.player.balance.values())
        self._prev_dist_to_mine = self._dist_to_nearest_mine(self.player)

        return self._get_obs(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        reward = 0.0
        terminated = False
        truncated = False
        info = {}
        self.steps += 1

        was_alive = not self.player.is_dead

        # 1) Ход игрока
        if not self.player.is_dead:
            r, i = self._execute_action(self.player, self.bot, action)
            reward += r
            info.update(i)
        else:
            reward -= 0.5  # Ждём возрождения

        # 2) Ход бота
        if not self.bot.is_dead:
            self._bot_step()

        # 3) Доход от шахт + голод
        # FIX #1: игрок НЕ бросает лут при смерти от голода (убираем эксплойт)
        self._apply_income(self.player, drop_loot_on_starve=False)
        self._apply_income(self.bot, drop_loot_on_starve=True)

        # Большой штраф за смерть от голода
        if was_alive and self.player.is_dead:
            reward -= 15.0

        # 4) Респаун мёртвых
        player_was_dead = self.player.is_dead
        self._handle_respawn(self.player)
        self._handle_respawn(self.bot)
        # После респауна сбрасываем трекеры, чтобы не было ложной награды за стартовые ресурсы
        if player_was_dead and not self.player.is_dead:
            self._prev_total_resources = sum(self.player.balance.values())
            self._prev_dist_to_mine = self._dist_to_nearest_mine(self.player)

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

        # 6) Shaped rewards — промежуточные награды за прогресс
        if not terminated:
            reward += self._shaped_reward()

        # 7) Лимит ходов
        if self.steps >= self.max_steps:
            truncated = True
            info["result"] = info.get("result", "TIMEOUT")
            mines_player = self.game_map.count_mines_owned_by("player")
            mines_bot = self.game_map.count_mines_owned_by("bot")
            if mines_player > mines_bot:
                reward += 20.0
            elif mines_player < mines_bot:
                reward -= 10.0

        if self.render_mode == "human":
            self.render()

        return self._get_obs(), reward, terminated, truncated, info

    def _shaped_reward(self) -> float:
        """Промежуточные награды за прогресс к победе."""
        shaped = 0.0

        # 1) Награда за изменение числа контролируемых шахт
        mines_now = self.game_map.count_mines_owned_by("player")
        mine_delta = mines_now - self._prev_mines_owned
        if mine_delta > 0:
            shaped += 8.0 * mine_delta   # +8 за каждую новую шахту
        elif mine_delta < 0:
            shaped += 4.0 * mine_delta   # -4 за потерю шахты

        # 2) Пассивный бонус за удержание шахт; энергетическая особенно важна
        energy_mines = sum(
            1 for row in self.game_map.grid for c in row
            if c.resource_type == "energy" and c.owner == "player"
        )
        shaped += 0.15 * mines_now + (0.25 if energy_mines > 0 else -0.1)

        # 3) Навигационная награда — ТОЛЬКО если число шахт не изменилось!
        # FIX #3: при захвате шахты mine_delta != 0, поэтому пропускаем этот блок,
        # чтобы не получать штраф за "прыжок" расстояния на следующую шахту.
        if not self.player.is_dead:
            dist_now = self._dist_to_nearest_mine(self.player)
            if mine_delta == 0:
                dist_delta = self._prev_dist_to_mine - dist_now
                shaped += np.clip(dist_delta * 0.4, -1.0, 1.0)
            self._prev_dist_to_mine = dist_now

        self._prev_mines_owned = mines_now

        # 4) Награда за реальный прирост ресурсов (от дохода шахт)
        if not self.player.is_dead:
            total_res = sum(self.player.balance.values())
            res_delta = total_res - self._prev_total_resources
            if res_delta > 0:
                shaped += min(res_delta * 0.01, 0.5)  # Макс +0.5 за ход
            self._prev_total_resources = total_res

        return shaped

    def _dist_to_nearest_mine(self, agent: SimpleAgent, res_type: Optional[str] = None) -> float:
        """Manhattan расстояние до ближайшей ничейной/вражеской шахты.
        
        Args:
            agent: агент
            res_type: тип ресурса ('energy', 'matter', 'imagination') или None (любая)
        """
        best_dist = MAP_SIZE * 2
        found = False
        for row in self.game_map.grid:
            for cell in row:
                if cell.resource_type and cell.owner != agent.name:
                    if res_type is None or cell.resource_type == res_type:
                        dist = abs(cell.x - agent.x) + abs(cell.y - agent.y)
                        if dist < best_dist:
                            best_dist = dist
                            found = True
        return best_dist if found else 0.0

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
        """Конвертирует состояние игры в плоский вектор [0..1] (324 элемента)."""
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

        # FIX #5: Подсказки (9 значений) — помогаем маленькой MLP-сети ориентироваться
        # dx/dy к ближайшей любой шахте
        nearest_mine = self._find_nearest_mine(self.player)
        if nearest_mine:
            obs.append((nearest_mine.x - self.player.x + MAP_SIZE) / (2 * MAP_SIZE))
            obs.append((nearest_mine.y - self.player.y + MAP_SIZE) / (2 * MAP_SIZE))
        else:
            obs.append(0.5); obs.append(0.5)

        # dx/dy к ближайшей энергетической шахте
        energy_mine = self._find_nearest_mine(self.player, res_type="energy")
        if energy_mine:
            obs.append((energy_mine.x - self.player.x + MAP_SIZE) / (2 * MAP_SIZE))
            obs.append((energy_mine.y - self.player.y + MAP_SIZE) / (2 * MAP_SIZE))
        else:
            obs.append(0.5); obs.append(0.5)

        # dx/dy к врагу
        if not self.bot.is_dead:
            obs.append((self.bot.x - self.player.x + MAP_SIZE) / (2 * MAP_SIZE))
            obs.append((self.bot.y - self.player.y + MAP_SIZE) / (2 * MAP_SIZE))
        else:
            obs.append(0.5); obs.append(0.5)

        # can_capture: есть ли шахта рядом?
        can_capture = 0.0
        for odx, ody in SELF_AND_ADJACENT:
            c = self.game_map.get_cell(self.player.x + odx, self.player.y + ody)
            if c and c.resource_type and c.owner != "player":
                can_capture = 1.0
                break
        obs.append(can_capture)

        # can_attack: враг рядом?
        can_attack = 0.0
        if not self.bot.is_dead:
            dist = abs(self.bot.x - self.player.x) + abs(self.bot.y - self.player.y)
            if dist <= 1:
                can_attack = 1.0
        obs.append(can_attack)

        # has_loot_nearby: есть лут рядом?
        has_loot_nearby = 0.0
        for odx, ody in SELF_AND_ADJACENT:
            c = self.game_map.get_cell(self.player.x + odx, self.player.y + ody)
            if c and any(v > 0 for v in c.loot.values()):
                has_loot_nearby = 1.0
                break
        obs.append(has_loot_nearby)

        obs = np.clip(obs, 0.0, 1.0)
        return np.array(obs, dtype=np.float32)

    # ----------------------------------------------------------
    # Action Execution
    # ----------------------------------------------------------

    def _execute_action(self, agent: SimpleAgent, enemy: SimpleAgent,
                        action_idx: int) -> Tuple[float, dict]:
        """Выполняет действие с авто-нацеливанием и возвращает (reward, info)."""
        reward = 0.0
        info = {}
        gm = self.game_map

        # === 0: MOVE_TO_MINE ===
        if action_idx == 0:
            target = self._find_nearest_mine(agent)
            if target is None:
                reward -= 0.3
                info["action"] = "MOVE_MINE_NONE"
            else:
                r, i = self._move_toward(agent, enemy, target.x, target.y)
                reward += r
                info.update(i)
                if r >= 0:
                    info["action"] = "MOVE_TO_MINE"

        # === 1: MOVE_TO_ENEMY ===
        elif action_idx == 1:
            if enemy.is_dead:
                reward -= 0.3
                info["action"] = "MOVE_ENEMY_DEAD"
            else:
                r, i = self._move_toward(agent, enemy, enemy.x, enemy.y)
                reward += r
                info.update(i)
                if r >= 0:
                    info["action"] = "MOVE_TO_ENEMY"

        # === 2: MOVE_TO_ENERGY_MINE (FIX #4: заменяем бесполезный MOVE_HOME) ===
        elif action_idx == 2:
            target = self._find_nearest_mine(agent, res_type="energy")
            if target is None:
                reward -= 0.3
                info["action"] = "MOVE_ENERGY_NONE"
            else:
                r, i = self._move_toward(agent, enemy, target.x, target.y)
                reward += r
                info.update(i)
                if r >= 0:
                    info["action"] = "MOVE_TO_ENERGY_MINE"

        # === 3: CAPTURE ===
        elif action_idx == 3:
            if agent.balance["imagination"] < 10:
                reward -= 0.5
                info["action"] = "CAPTURE_NO_IMAG"
            else:
                best_cell = None
                # Приоритет: сначала ищем энергетическую шахту (важнее для выживания)
                for odx, ody in SELF_AND_ADJACENT:
                    c = gm.get_cell(agent.x + odx, agent.y + ody)
                    if (c and c.resource_type and c.owner != agent.name
                            and c.structure != "wall"):
                        if enemy.is_dead or not (enemy.x == c.x and enemy.y == c.y):
                            if best_cell is None:
                                best_cell = c
                            if c.resource_type == "energy":  # Энергетическая = приоритет
                                best_cell = c
                                break
                if best_cell:
                    agent.balance["imagination"] -= 10
                    best_cell.owner = agent.name
                    # Энергетическая шахта ценнее — даём больше награды
                    reward += 15.0 if best_cell.resource_type == "energy" else 10.0
                    info["action"] = "CAPTURE_MINE"
                else:
                    reward -= 0.5
                    info["action"] = "CAPTURE_NO_TARGET"

        # === 4: ATTACK ===
        elif action_idx == 4:
            if agent.balance["energy"] < 5:
                reward -= 0.5
                info["action"] = "ATTACK_NO_ENERGY"
            else:
                agent.balance["energy"] -= 5
                dmg = 40 if "combat_lvl_1" in agent.techs else 25
                attacked = False

                # Приоритет 1: враг рядом
                if not enemy.is_dead:
                    dist = abs(enemy.x - agent.x) + abs(enemy.y - agent.y)
                    if dist == 1:
                        enemy.hp -= dmg
                        reward += 3.0
                        if enemy.hp <= 0:
                            enemy.is_dead = True
                            enemy.respawn_timer = 5
                            cell = gm.get_cell(enemy.x, enemy.y)
                            if cell:
                                for res in ["matter", "energy", "imagination"]:
                                    cell.loot[res] = cell.loot.get(res, 0) + enemy.balance[res]
                                    enemy.balance[res] = 0
                            reward += 20.0
                            info["action"] = "ATTACK_KILL"
                        else:
                            info["action"] = f"ATTACK_HIT_{enemy.hp}hp"
                        attacked = True

                # Приоритет 2: вражеская структура / шахта рядом
                if not attacked:
                    for odx, ody in ADJACENT_OFFSETS:
                        c = gm.get_cell(agent.x + odx, agent.y + ody)
                        if c:
                            if c.structure == "wall" and c.owner != agent.name:
                                c.wall_hp -= dmg
                                if c.wall_hp <= 0:
                                    c.structure = None
                                    c.wall_hp = 0
                                reward += 0.5
                                info["action"] = "ATTACK_WALL"
                                attacked = True
                                break
                            elif c.resource_type and c.owner not in (agent.name, None):
                                c.mine_hp -= dmg
                                if c.mine_hp <= 0:
                                    c.mine_level = max(0, c.mine_level - 1)
                                    if c.mine_level <= 0:
                                        c.owner = None
                                        c.resource_type = None
                                    else:
                                        c.mine_hp = 50 * c.mine_level
                                reward += 1.0
                                info["action"] = "ATTACK_ENEMY_MINE"
                                attacked = True
                                break

                if not attacked:
                    reward -= 0.5
                    info["action"] = "ATTACK_NO_TARGET"

        # === 5: BUILD (FIX #2: убрана халявная награда; требует 2+ шахты) ===
        elif action_idx == 5:
            build_cost = 14 if "economy_lvl_1" in agent.techs else 20
            mines_owned = self.game_map.count_mines_owned_by(agent.name)
            if agent.balance["matter"] < build_cost or mines_owned < 2:
                reward -= 0.5
                info["action"] = "BUILD_INVALID"
            else:
                built = False
                for odx, ody in ADJACENT_OFFSETS:
                    c = gm.get_cell(agent.x + odx, agent.y + ody)
                    if (c and c.structure is None and c.resource_type is None
                            and (enemy.is_dead or not (enemy.x == c.x and enemy.y == c.y))):
                        agent.balance["matter"] -= build_cost
                        c.structure = "wall"
                        c.wall_hp = 100
                        c.owner = agent.name
                        reward -= 0.1  # Небольшая цена за трату хода, не бонус!
                        info["action"] = "BUILD_WALL"
                        built = True
                        break
                if not built:
                    reward -= 0.5
                    info["action"] = "BUILD_NO_SPACE"

        # === 6: RESEARCH ===
        elif action_idx == 6:
            researched = False
            # Приоритет: economy → combat → logistics, по уровням
            priority = [
                "economy_lvl_1", "combat_lvl_1", "logistics_lvl_1",
                "economy_lvl_2", "combat_lvl_2", "logistics_lvl_2",
                "economy_lvl_3", "combat_lvl_3", "logistics_lvl_3",
            ]
            for tech_name in priority:
                if tech_name in agent.techs:
                    continue
                td = TECH_TREE[tech_name]
                if td["parent"] and td["parent"] not in agent.techs:
                    continue
                if agent.balance["imagination"] < td["cost"]:
                    continue
                agent.balance["imagination"] -= td["cost"]
                agent.techs.append(tech_name)
                reward += 5.0
                info["action"] = f"RESEARCH_{tech_name}"
                researched = True
                break
            if not researched:
                reward -= 0.3
                info["action"] = "RESEARCH_NONE"

        # === 7: GATHER_LOOT ===
        elif action_idx == 7:
            # Двигаться к ближайшему луту
            best_cell = None
            best_dist = 999
            for row in gm.grid:
                for cell in row:
                    if any(v > 0 for v in cell.loot.values()):
                        dist = abs(cell.x - agent.x) + abs(cell.y - agent.y)
                        if dist < best_dist:
                            best_dist = dist
                            best_cell = cell
            if best_cell:
                r, i = self._move_toward(agent, enemy, best_cell.x, best_cell.y)
                reward += r
                info.update(i)
                if r >= 0:
                    info["action"] = "GATHER_LOOT"
            else:
                reward -= 0.3
                info["action"] = "GATHER_NO_LOOT"

        # === 8: PASS ===
        elif action_idx == 8:
            # PASS оправдан только если агент уже владеет шахтами и копит ресурсы
            if self.game_map.count_mines_owned_by(agent.name) >= 3:
                reward += 0.1
            else:
                reward -= 0.5
            info["action"] = "PASS"

        return reward, info

    def _move_toward(self, agent: SimpleAgent, enemy: SimpleAgent,
                     tx: int, ty: int) -> Tuple[float, dict]:
        """Двигает агента на 1 клетку к цели. Возвращает (reward, info).
        
        FIX #4: Добавлены перпендикулярные кандидаты для обхода стен.
        """
        move_cost = 2 if "logistics_lvl_1" in agent.techs else 5
        if agent.balance["energy"] < move_cost:
            return -0.5, {"action": "MOVE_NO_ENERGY"}

        dx = int(np.sign(tx - agent.x))
        dy = int(np.sign(ty - agent.y))

        if dx == 0 and dy == 0:
            return -0.2, {"action": "MOVE_ALREADY_THERE"}

        # Прямые шаги к цели
        candidates = []
        if dx != 0:
            candidates.append((agent.x + dx, agent.y))
        if dy != 0:
            candidates.append((agent.x, agent.y + dy))
        # FIX #4: Перпендикулярный обход, если путь перекрыт стеной
        if dx == 0:  # Двигаемся только вертикально — добавим горизонтальные обходы
            candidates.extend([(agent.x + 1, agent.y), (agent.x - 1, agent.y)])
        if dy == 0:  # Двигаемся только горизонтально — добавим вертикальные обходы
            candidates.extend([(agent.x, agent.y + 1), (agent.x, agent.y - 1)])

        for nx, ny in candidates:
            cell = self.game_map.get_cell(nx, ny)
            if cell is None:
                continue
            if cell.structure == "wall":
                continue
            if not enemy.is_dead and enemy.x == nx and enemy.y == ny:
                continue
            # Успешный ход
            agent.balance["energy"] -= move_cost
            agent.x = nx
            agent.y = ny
            reward = 0.0
            # Подбор лута при перемещении (без +2.0 бонуса — убираем привлекательность лута)
            for res in ["matter", "energy", "imagination"]:
                if cell.loot.get(res, 0) > 0:
                    agent.balance[res] += cell.loot[res]
                    reward += 1.0  # Умеренная награда (было 2.0)
                    cell.loot[res] = 0
            return reward, {"action": "MOVE"}

        return -0.3, {"action": "MOVE_BLOCKED"}

    def _find_nearest_mine(self, agent: SimpleAgent, res_type: Optional[str] = None) -> Optional[SimpleCell]:
        """Находит ближайшую ничейную/вражескую шахту.
        
        Args:
            agent: агент
            res_type: тип ресурса ('energy', 'matter', 'imagination') или None (любая)
        """
        best_dist = 999
        best_cell = None
        for row in self.game_map.grid:
            for cell in row:
                if cell.resource_type and cell.owner != agent.name:
                    if res_type is None or cell.resource_type == res_type:
                        dist = abs(cell.x - agent.x) + abs(cell.y - agent.y)
                        if dist < best_dist:
                            best_dist = dist
                            best_cell = cell
        # FIX #4: Если нужного типа нет, ищем любую доступную шахту
        if best_cell is None and res_type is not None:
            return self._find_nearest_mine(agent, res_type=None)
        return best_cell

    # ----------------------------------------------------------
    # Bot Logic (простой rule-based противник)
    # ----------------------------------------------------------

    def _bot_step(self):
        """Ослабленный бот: 50% шанс пропуска хода."""
        bot = self.bot
        gm = self.game_map

        # 50% шанс пропустить ход (бот "думает")
        if self.np_random.random() < 0.5:
            return

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
            dx = int(np.sign(best_cell.x - bot.x))
            dy = int(np.sign(best_cell.y - bot.y))

            moves_to_try = []
            if dx != 0:
                moves_to_try.append((bot.x + dx, bot.y))
            if dy != 0:
                moves_to_try.append((bot.x, bot.y + dy))

            for nx, ny in moves_to_try:
                target = gm.get_cell(nx, ny)
                if target and target.structure != "wall":
                    if self.player.is_dead or not (self.player.x == nx and self.player.y == ny):
                        bot.balance["energy"] -= 5
                        bot.x = nx
                        bot.y = ny
                        for res in ["matter", "energy", "imagination"]:
                            if target.loot.get(res, 0) > 0:
                                bot.balance[res] += target.loot[res]
                                target.loot[res] = 0
                        break

    # ----------------------------------------------------------
    # Income & Hunger
    # ----------------------------------------------------------

    def _apply_income(self, agent: SimpleAgent, drop_loot_on_starve: bool = False):
        """Начисляет доход от шахт и отнимает голод.
        
        Args:
            agent: агент
            drop_loot_on_starve: если True — бросает ресурсы при смерти от голода.
                                 FIX #1: для игрока = False (убирает суицидальный эксплойт).
        """
        if agent.is_dead:
            return

        # Доход от владеемых шахт: +10 × уровень
        for row in self.game_map.grid:
            for cell in row:
                if cell.resource_type and cell.owner == agent.name:
                    income = 10 * cell.mine_level
                    agent.balance[cell.resource_type] += income

        # Голод: -N энергии за ход
        agent.balance["energy"] -= self.hunger

        # Смерть от голода
        if agent.balance["energy"] < 0:
            agent.is_dead = True
            agent.respawn_timer = 5
            agent.hp = 0
            cell = self.game_map.get_cell(agent.x, agent.y)
            if cell and drop_loot_on_starve:
                # Только бот бросает лут — это честно (он не управляет своим лутом)
                agent.balance["energy"] = 0
                for res in ["matter", "energy", "imagination"]:
                    cell.loot[res] = cell.loot.get(res, 0) + agent.balance[res]
            for res in ["matter", "energy", "imagination"]:
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
                agent.balance = {"matter": 100, "energy": 100, "imagination": 100}

    # ----------------------------------------------------------
    # Win Conditions
    # ----------------------------------------------------------

    def _check_win(self) -> Optional[str]:
        """Проверяет условия победы. Возвращает 'player', 'bot' или None."""
        for agent in [self.player, self.bot]:
            name = agent.name
            bal = agent.balance

            # Singularity: 500 каждого ресурса (достижимо за 200-300 ходов)
            if bal["matter"] >= 500 and bal["energy"] >= 500 and bal["imagination"] >= 500:
                return name

            # Monopoly: 5+ из 9 шахт (больше половины)
            total = self.game_map.total_mines()
            if total > 0:
                owned = self.game_map.count_mines_owned_by(name)
                if owned >= 5:
                    return name

        return None


# Регистрируем среду в Gymnasium
gym.register(
    id="AISandbox-v1",
    entry_point="rl_env:AISandboxEnv",
    max_episode_steps=500,
)
