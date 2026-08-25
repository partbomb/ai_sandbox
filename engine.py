import json
import logging
import time
from typing import List, Dict, Any, Optional
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
    matter: int = 0
    energy: int = 0
    imagination: int = 0

class AgentState(BaseModel):
    name: str
    api_key: str
    model: str
    balance: Resources = Field(default_factory=Resources)
    income: Resources = Field(default_factory=lambda: Resources(matter=10, energy=10, imagination=10))
    breakthroughs: List[str] = Field(default_factory=list)

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
    "You are an AI in a simulation. Your goal is to reach 1500 Matter, 1500 Energy, and 1500 Imagination first. "
    "You are playing on a 5x5 Map. "
    "Clarify your goals, current income, and balance. "
    "Available actions:\n"
    "1. Capture a map cell (Empty = free, Enemy = costs 300 Energy): {\"action\": \"capture\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "2. Build an impenetrable wall (Costs 150 Matter and 150 Imagination): {\"action\": \"build_wall\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "3. Upgrade a mine (Level 2 costs 200 of its resource, Level 3 costs 400 of its resource): {\"action\": \"upgrade_mine\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "4. Pass: {\"action\": \"pass\"}"
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
    def send(self, api_key: str, model_name: str, prompt: str) -> str:
        if not api_key or api_key == "ВСТАВЬТЕ_ВАШ_API_КЛЮЧ_СЮДА" or api_key.startswith("sk-"):
            import random
            x = random.randint(0, 4)
            y = random.randint(0, 4)
            return json.dumps({"action": "capture", "target_x": x, "target_y": y})
            
        try:
            logger.debug(f"Отправка реального запроса в Gemini API ({model_name})...")
            client = genai.Client(api_key=api_key)
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

    def check_elements(self, agent_state: AgentState, agent_action: str, map_core: Optional['world.MapCore'] = None):
        """Арбитр проверяет действие агента"""
        map_info = f"Карта: {map_core.get_map_state_json()}\n" if map_core else ""
        prompt = (
            f"{PROMPT_ARBITER}\n"
            f"Текущий статус агента:\nБаланс: {agent_state.balance.model_dump_json()}\nДоход: {agent_state.income.model_dump_json()}\n"
            f"{map_info}"
            f"Действие агента: {agent_action}"
        )
        
        logger.debug(f"Arbitor получил промпт для раздумий и проверяет действие...")
        
        try:
            action_data = json.loads(agent_action)
            action_type = action_data.get("action")
            
            if action_type == "capture" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    cell = map_core.get_cell(tx, ty)
                    if cell:
                        if cell.structure == 'Wall':
                            logger.warning(f"Арбитр ОТКЛОНИЛ capture [{agent_state.name}]: там стена")
                        elif cell.owner_id == agent_state.name:
                            pass
                        elif cell.owner_id is None:
                            cell.owner_id = agent_state.name
                            logger.info(f"Арбитр ОДОБРИЛ capture (свободная) [{agent_state.name}]: ({tx}, {ty})")
                        else:
                            if agent_state.balance.energy >= 300:
                                agent_state.balance.energy -= 300
                                cell.owner_id = agent_state.name
                                logger.info(f"Арбитр ОДОБРИЛ capture (враг) [{agent_state.name}]: ({tx}, {ty}) -300 Energy")
                            else:
                                logger.warning(f"Арбитр ОТКЛОНИЛ capture [{agent_state.name}]: не хватает Энергии")

            elif action_type == "build_wall" and map_core:
                tx, ty = action_data.get("target_x"), action_data.get("target_y")
                if tx is not None and ty is not None:
                    cell = map_core.get_cell(tx, ty)
                    if cell:
                        if cell.structure == 'Wall':
                            logger.warning("Уже есть стена")
                        elif cell.owner_id not in [None, agent_state.name]:
                            logger.warning("Нельзя строить на чужой клетке")
                        else:
                            if agent_state.balance.matter >= 150 and agent_state.balance.imagination >= 150:
                                agent_state.balance.matter -= 150
                                agent_state.balance.imagination -= 150
                                cell.structure = 'Wall'
                                logger.info(f"Арбитр ОДОБРИЛ build_wall [{agent_state.name}]: ({tx}, {ty})")
                            else:
                                logger.warning("Не хватает ресурсов для стены")

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
                                logger.info(f"Арбитр ОДОБРИЛ upgrade_mine [{agent_state.name}] до уровня {cell.mine_level}")
                            else:
                                logger.warning("Не хватает ресурсов для апгрейда")
                                
        except json.JSONDecodeError:
            logger.error("Неверный формат ответа от агента, Арбитр не смог обработать")


class Stage1AI:
    def __init__(self, state: AgentState):
        self.state = state
        self.url: str = f"https://api.{self.state.model}.example.com" # Пример
        logger.info(f"ИИ Агент [{self.state.name}] готов к работе.")

    def generate_prompt(self, map_core: Optional['world.MapCore'] = None) -> str:
        """Промпт"""    
        map_info = f"Map State: {map_core.get_map_state_json()}\n" if map_core else ""
        prompt = (
            f"{PROMPT_STAGE1}\n"
            f"Текущий статус:\n"
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
            arbitor.check_elements(ai.state, response, current_events)

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
