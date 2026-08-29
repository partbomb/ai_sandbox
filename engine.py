import json
import logging
import time
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
import world

# Логирование
logger = logging.getLogger("GameEngine")
logger.setLevel(logging.DEBUG) # Уровень

# Вывод
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# Модели
class Resources(BaseModel):
    matter: int = 500
    energy: int = 500
    imagination: int = 500

class AgentState(BaseModel):
    name: str
    api_key: str
    model: str
    balance: Resources = Field(default_factory=Resources)
    income: Resources = Field(default_factory=lambda: Resources(matter=10, energy=10, imagination=10))
    breakthroughs: List[str] = Field(default_factory=list)
    x: int = 0
    y: int = 0
    hp: int = 100
    is_dead: bool = False
    respawn_timer: int = 0
    home_x: int = 0
    home_y: int = 0

class GameEvent(BaseModel):
    name: str
    cost: Resources
    reward_income: Resources = Field(default_factory=Resources)
    reward_balance: Resources = Field(default_factory=Resources)


EVENTS = [
    GameEvent(name="Quantum Anomaly", cost=Resources(energy=10), reward_income=Resources(matter=15, imagination=15)),
    GameEvent(name="Data Leak", cost=Resources(matter=10), reward_income=Resources(energy=20)),
    GameEvent(name="Neural Overclock", cost=Resources(imagination=15), reward_income=Resources(matter=20, energy=15)),
    GameEvent(name="Resource Surge", cost=Resources(energy=15), reward_balance=Resources(matter=50, imagination=50)),
    GameEvent(name="AI Breakthrough", cost=Resources(matter=20, energy=20), reward_income=Resources(matter=15, energy=15, imagination=15))
]

PROMPT_STAGE1 = (
    "You are an AI in a simulation. Your ULTIMATE GOAL is to reach Technological Singularity! "
    "To win, you must build the 'Server Core', which requires 5000 Matter, 5000 Energy, and 5000 Imagination.\n"
    "WARNING (HUNGER): You automatically lose 15 Energy every turn just to survive! If your Energy drops below 0, you DIE and drop all resources!\n"
    "You are on a 5x5 Map (coordinates X: 0-4, Y: 0-4) and you can see the entire map. "
    "You must return ONLY a single JSON object. Put your reasoning in 'thoughts'.\n"
    "Available actions (CHOOSE ONLY ONE):\n"
    "1. Move (Costs 10 Energy. You can ONLY move to an adjacent cell or stay, distance <= 1): {\"thoughts\": \"...\", \"action\": \"move\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "2. Attack (Costs 20 Energy, deals 25 DMG to Wall, Mine, or Enemy on an adjacent cell): {\"thoughts\": \"...\", \"action\": \"attack\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "3. Capture a cell (Empty = free, Neutral Mine = 300 Imagination. MUST be on the cell or adjacent, and MUST have 0 enemy structures/avatars on it): {\"thoughts\": \"...\", \"action\": \"capture\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "4. Build Wall (Costs 150 Matter, 150 Imagination, gives 100 HP wall. MUST be adjacent): {\"thoughts\": \"...\", \"action\": \"build_wall\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "5. Repair Wall (Costs 50 Matter, gives +50 HP. MUST be adjacent): {\"thoughts\": \"...\", \"action\": \"repair_wall\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "6. Upgrade a mine (Level 2 costs 200, Level 3 costs 400. MUST be adjacent): {\"thoughts\": \"...\", \"action\": \"upgrade_mine\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "7. Pass (Wait for passive income): {\"thoughts\": \"...\", \"action\": \"pass\"}\n"
    "8. Build Core (Costs 5000 M, 5000 E, 5000 I. WINS THE GAME): {\"thoughts\": \"...\", \"action\": \"build_core\"}"
)

PROMPT_ARBITER = """You are the Arbiter of a simulation game. 
Your task is to evaluate the action of an AI agent and determine its outcome based on the rules.
You will receive the agent's current state (balance, income) and the map state.
Actions:
- capture: Empty cells are free. Enemy cells cost 300 Energy. Validates coordinates.
- build_wall: Costs 150 Matter and 150 Imagination. Makes cell impenetrable.
- upgrade_mine: Upgrading to Lvl 2 costs 200 resource, Lvl 3 costs 400 resource. Increases income.
- pass: No action.
Return JSON strictly in this format:
{
    "approved": true/false,
    "reason": "Explanation",
    "balance_change": {"matter": x, "energy": y, "imagination": z},
    "income_change": {"matter": x, "energy": y, "imagination": z}
}"""

# Ядро

class APIBridge:
    def __init__(self):
        self.clients = {}

    def send(self, api_key: str, model_name: str, prompt: str) -> str:
        if not api_key or api_key == "ВСТАВЬТЕ_ВАШ_API_КЛЮЧ_СЮДА" or api_key.startswith("sk-"):
            import random
            x = random.randint(0, 4)
            y = random.randint(0, 4)
            return json.dumps({"action": "capture", "target_x": x, "target_y": y})
            
        try:
            logger.debug(f"Отправка реального запроса в Gemini API ({model_name})...")
            if api_key not in self.clients:
                self.clients[api_key] = genai.Client(api_key=api_key)
            client = self.clients[api_key]
            
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"Ошибка вызова API: {e}")
            return json.dumps({"action": "pass"})

api_bridge = APIBridge()


class ArbitorAI:
    def __init__(self):
        self.stage: int = 1
        logger.info("Arbitor_AI инициализирован. Следит за правилами.")

    def evaluate_breakthrough(self, agent_state: AgentState, target_agent: 'Stage1AI') -> str:
        """Проверка"""
        logger.debug(f"Arbitor_AI проверяет breakthrough для агента {agent_state.name}...")
        # Заглушка
        return "Breakthrough approved: +5 Matter income, cost: 50 Energy."

    def get_random_events(self, count: int = 5) -> List[GameEvent]:
        """Возвращает выборку из нескольких событий"""
        import random
        return random.sample(EVENTS, min(count, len(EVENTS)))

    def check_elements(self, agent_state: AgentState, agent_action: str, map_core: Optional['world.MapCore'] = None, all_agents: Optional[List[AgentState]] = None) -> tuple[bool, str]:
        """Арбитр проверяет действие агента"""
        if agent_state.is_dead:
            return False, f"[{agent_state.name}] Мертв. Пропуск хода."

        # (Промпт арбитра был удален, так как арбитр работает на жесткой логике Python)
        
        logger.debug(f"Arbitor получил промпт для раздумий и проверяет действие...")
        
        try:
            cleaned_action = agent_action.strip()
            if cleaned_action.startswith('```json'): cleaned_action = cleaned_action[7:]
            elif cleaned_action.startswith('```'): cleaned_action = cleaned_action[3:]
            if cleaned_action.endswith('```'): cleaned_action = cleaned_action[:-3]
            cleaned_action = cleaned_action.strip()
            
            action_data = json.loads(cleaned_action)
            action_type = action_data.get("action")
            
            # Если Gemini обернул ответ в {"action": {"action": "capture", ...}}
            if isinstance(action_type, dict):
                action_data = action_type
                action_type = action_data.get("action")
                
            if action_type == "move" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    # check 1 step
                    if abs(agent_state.x - tx) <= 1 and abs(agent_state.y - ty) <= 1:
                        cell = map_core.get_cell(tx, ty)
                        if cell and cell.structure == 'Wall':
                            return False, f"[{agent_state.name}] ОТКЛОНЕНО move: путь преграждает стена"
                        elif all_agents and any(a.name != agent_state.name and a.x == tx and a.y == ty and not a.is_dead for a in all_agents):
                            return False, f"[{agent_state.name}] ОТКЛОНЕНО move: путь преграждает аватар"
                        else:
                            if agent_state.balance.energy >= 10:
                                agent_state.balance.energy -= 10
                                agent_state.x = tx
                                agent_state.y = ty
                                msg = f"[{agent_state.name}] ИДЕТ на ({tx}, {ty})"
                                # collect loot?
                                if cell and cell.loot and any(v > 0 for v in cell.loot.values()):
                                    agent_state.balance.matter += cell.loot.get('matter', 0)
                                    agent_state.balance.energy += cell.loot.get('energy', 0)
                                    agent_state.balance.imagination += cell.loot.get('imagination', 0)
                                    cell.loot = {}
                                    msg += " и собирает лут!"
                                return True, msg
                            else:
                                return False, f"[{agent_state.name}] ОТКЛОНЕНО move: мало энергии"
                    else:
                        return False, f"[{agent_state.name}] ОТКЛОНЕНО move: только на соседнюю клетку"

            elif action_type == "attack" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    if abs(agent_state.x - tx) <= 1 and abs(agent_state.y - ty) <= 1:
                        if agent_state.balance.energy >= 20:
                            agent_state.balance.energy -= 20
                            cell = map_core.get_cell(tx, ty)
                            target_hit = False
                            
                            # Hit wall
                            if cell and cell.structure == 'Wall':
                                cell.wall_hp -= 25
                                logger.info(f"[{agent_state.name}] бьет Стену на ({tx},{ty}). Осталось HP: {cell.wall_hp}")
                                if cell.wall_hp <= 0:
                                    cell.structure = None
                                    cell.wall_hp = 0
                                    agent_state.balance.matter += 20 # scrap
                                target_hit = True
                            
                            # Hit avatar
                            elif all_agents:
                                target_agent = next((a for a in all_agents if a.x == tx and a.y == ty and not a.is_dead), None)
                                if target_agent:
                                    target_agent.hp -= 25
                                    logger.info(f"[{agent_state.name}] бьет Аватара {target_agent.name}! HP: {target_agent.hp}")
                                    if target_agent.hp <= 0:
                                        target_agent.is_dead = True
                                        target_agent.respawn_timer = 5
                                        # Drop loot
                                        if cell:
                                            cell.loot['matter'] = cell.loot.get('matter', 0) + target_agent.balance.matter
                                            cell.loot['energy'] = cell.loot.get('energy', 0) + target_agent.balance.energy
                                            cell.loot['imagination'] = cell.loot.get('imagination', 0) + target_agent.balance.imagination
                                        target_agent.balance.matter = 0
                                        target_agent.balance.energy = 0
                                        target_agent.balance.imagination = 0
                                        logger.info(f"Аватар {target_agent.name} УБИТ!")
                                    target_hit = True
                            
                            # Hit mine
                            if not target_hit and cell and cell.mine_level > 0:
                                cell.mine_hp -= 25
                                logger.info(f"[{agent_state.name}] бьет Шахту на ({tx},{ty}). Осталось HP: {cell.mine_hp}")
                                if cell.mine_hp <= 0:
                                    cell.mine_level -= 1
                                    agent_state.balance.matter += 30 # scrap
                                    if cell.mine_level <= 0:
                                        cell.owner_id = None
                                        cell.mine_hp = 0
                                    else:
                                        cell.mine_hp = 50 * cell.mine_level
                            return True, f"[{agent_state.name}] АТАКУЕТ ({tx},{ty})"
                        else:
                            return False, f"[{agent_state.name}] ОТКЛОНЕНО attack: мало энергии"
                    else:
                        return False, f"[{agent_state.name}] ОТКЛОНЕНО attack: слишком далеко"

            elif action_type == "capture" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    # Must be next to it or on it
                    if abs(agent_state.x - tx) <= 1 and abs(agent_state.y - ty) <= 1:
                        cell = map_core.get_cell(tx, ty)
                        if cell:
                            if cell.structure == 'Wall' and cell.owner_id != agent_state.name:
                                return False, f"[{agent_state.name}] ОТКЛОНЕНО capture: мешает стена"
                            elif all_agents and any(a.name != agent_state.name and a.x == tx and a.y == ty and not a.is_dead for a in all_agents):
                                return False, f"[{agent_state.name}] ОТКЛОНЕНО capture: мешает враг"
                            else:
                                is_mine = (cell.mine_level > 0)
                                cost = 300 if is_mine else 0
                                if agent_state.balance.imagination >= cost:
                                    if cost > 0: agent_state.balance.imagination -= cost
                                    cell.owner_id = agent_state.name
                                    return True, f"[{agent_state.name}] ЗАХВАТИЛ клетку ({tx}, {ty})"
                                else:
                                    return False, f"[{agent_state.name}] ОТКЛОНЕНО capture: нужно {cost} Imagination"
                    else:
                        return False, f"[{agent_state.name}] ОТКЛОНЕНО capture: слишком далеко"

            elif action_type == "build_wall" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    cell = map_core.get_cell(tx, ty)
                    if cell:
                        if cell.structure == 'Wall':
                            return False, f"[{agent_state.name}] ОТКЛОНЕНО build_wall: уже есть стена"
                        elif all_agents and any(a.name != agent_state.name and a.x == tx and a.y == ty and not a.is_dead for a in all_agents):
                            return False, f"[{agent_state.name}] ОТКЛОНЕНО build_wall: враг на клетке"
                        else:
                            if agent_state.balance.matter >= 150 and agent_state.balance.imagination >= 150:
                                agent_state.balance.matter -= 150
                                agent_state.balance.imagination -= 150
                                cell.structure = 'Wall'
                                cell.wall_hp = 100
                                cell.owner_id = agent_state.name
                                return True, f"[{agent_state.name}] ПОСТРОИЛ СТЕНУ на ({tx}, {ty})"
                            else:
                                return False, f"[{agent_state.name}] ОТКЛОНЕНО build_wall: не хватает ресурсов"
                    return False, f"[{agent_state.name}] ОТКЛОНЕНО build_wall: вне карты"

            elif action_type == "repair_wall" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    cell = map_core.get_cell(tx, ty)
                    if cell and cell.structure == 'Wall' and cell.owner_id == agent_state.name:
                        if agent_state.balance.matter >= 50:
                            agent_state.balance.matter -= 50
                            cell.wall_hp += 50
                            if cell.wall_hp > 100: cell.wall_hp = 100
                            return True, f"[{agent_state.name}] ПОЧИНИЛ СТЕНУ на ({tx}, {ty})"
                        else:
                            return False, f"[{agent_state.name}] ОТКЛОНЕНО repair_wall: нет Материи"
                    return False, f"[{agent_state.name}] ОТКЛОНЕНО repair_wall: нет стены"

            elif action_type == "upgrade_mine" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    cell = map_core.get_cell(tx, ty)
                    if cell and cell.owner_id == agent_state.name and cell.mine_level > 0:
                        res_type = cell.resource_type.lower()
                        cost = 0
                        if cell.mine_level == 1: cost = 200
                        elif cell.mine_level == 2: cost = 400
                        
                        if cost > 0:
                            res_val = getattr(agent_state.balance, res_type)
                            if res_val >= cost:
                                setattr(agent_state.balance, res_type, res_val - cost)
                                cell.mine_level += 1
                                cell.mine_hp = cell.mine_level * 50
                                return True, f"[{agent_state.name}] УЛУЧШИЛ ШАХТУ на ({tx}, {ty}) до уровня {cell.mine_level}"
                            else:
                                return False, f"[{agent_state.name}] ОТКЛОНЕНО upgrade: не хватает ресурсов"
                        return False, f"[{agent_state.name}] ОТКЛОНЕНО upgrade: максимальный уровень"
                    return False, f"[{agent_state.name}] ОТКЛОНЕНО upgrade: не ваша шахта"
            elif action_type == "build_core":
                if agent_state.balance.matter >= 5000 and agent_state.balance.energy >= 5000 and agent_state.balance.imagination >= 5000:
                    agent_state.balance.matter -= 5000
                    agent_state.balance.energy -= 5000
                    agent_state.balance.imagination -= 5000
                    return True, f"[{agent_state.name}] ПОСТРОИЛ СЕРВЕРНОЕ ЯДРО!"
                else:
                    return False, f"[{agent_state.name}] ОТКЛОНЕНО build_core: нужно по 5000 каждого ресурса"
            elif action_type == "pass":
                return True, f"[{agent_state.name}] пропустил ход"
                                
        except json.JSONDecodeError:
            return False, f"[{agent_state.name}] ОШИБКА: неверный JSON"
        except Exception as e:
            return False, f"[{agent_state.name}] ОШИБКА: {str(e)}"
            
        return False, f"[{agent_state.name}] ОТКЛОНЕНО: Неизвестное действие ({agent_action})"


class Stage1AI:
    def __init__(self, state: AgentState):
        self.state = state
        self.url: str = f"https://api.{self.state.model}.example.com" # Пример
        logger.info(f"ИИ Агент [{self.state.name}] готов к работе.")

    def generate_prompt(self, map_core: Optional['world.MapCore'] = None) -> str:
        """Промпт"""    
        map_info = f"Map State: {map_core.get_map_state_json()}\n" if hasattr(map_core, 'get_map_state_json') else ""
        prompt = (
            f"{PROMPT_STAGE1}\n"
            f"Текущий статус:\n"
            f"My Position: X={self.state.x}, Y={self.state.y}, HP={self.state.hp}\n"
            f"Баланс: {self.state.balance.model_dump_json()}\n"
            f"Доход: {self.state.income.model_dump_json()}\n"
            f"{map_info}"
        )
        return prompt

    def trade(self):
        # Обмен
        pass


# Конфиг
def load_agents(filepath: str) -> List[AgentState]:
    """Загрузка"""
    logger.info(f"Загрузка конфигурации ИИ из файла: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    agents = []
    for agent_data in data.get("agents", []):
        # Валидация
        agent = AgentState(**agent_data)
        agents.append(agent)
        logger.debug(f"Загружен ИИ: {agent.name} (Модель: {agent.model})")
    
    return agents


# Цикл
def run_simulation():
    logger.info("=== ЗАПУСК СИМУЛЯЦИИ ===")
    
    try:
        agents_data = load_agents("agents_config.json")
    except FileNotFoundError:
        logger.error("Файл agents_config.json не найден! Остановка.")
        return

    arbitor = ArbitorAI()
    agents = [Stage1AI(state) for state in agents_data]

    time_tick = 0
    game_over = False

    while not game_over:
        time_tick += 1
        logger.info(f"\n--- [ ХОД {time_tick} ] ---")
        
        current_events = arbitor.get_random_events(5)

        for ai in agents:
            if ai.state.is_dead:
                ai.state.respawn_timer -= 1
                if ai.state.respawn_timer <= 0:
                    ai.state.is_dead = False
                    ai.state.hp = 100
                    ai.state.x = ai.state.home_x
                    ai.state.y = ai.state.home_y
                    logger.info(f"Агент {ai.state.name} ВОЗРОДИЛСЯ на базе ({ai.state.x}, {ai.state.y})")
                continue

            # Доход от начального инкома
            ai.state.balance.matter += ai.state.income.matter
            ai.state.balance.energy += ai.state.income.energy
            ai.state.balance.imagination += ai.state.income.imagination
            logger.info(f"[{ai.state.name}] получил доход. Текущий Matter: {ai.state.balance.matter}, Energy: {ai.state.balance.energy}, Imagination: {ai.state.balance.imagination}")

            # Промпт
            prompt = ai.generate_prompt(current_events)
            
            # API (Имитация ответа агента)
            response = api_bridge.send(ai.state.api_key, ai.state.model, prompt)

            # Арбитр проверяет ответ агента
            arbitor.check_elements(ai.state, response, map_core=current_events, all_agents=[a.state for a in agents])

            # Победа: нужно собрать по 1500 каждого ресурса
            if (ai.state.balance.matter >= 1500 and 
                ai.state.balance.energy >= 1500 and 
                ai.state.balance.imagination >= 1500):
                logger.info(f"🏆 АГЕНТ {ai.state.name} СОБРАЛ ВСЕ РЕСУРСЫ (1500+) И ПОБЕДИЛ! 🏆")
                game_over = True
                break

        # Ограничитель
        if time_tick >= 200:
            logger.warning("Тестовый лимит ходов достигнут. Остановка симуляции.")
            break
            
        time.sleep(0.5)

if __name__ == "__main__":
    run_simulation()
