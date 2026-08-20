import json
import logging
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

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
    GameEvent(name="Quantum Anomaly", cost=Resources(energy=5), reward_balance=Resources(matter=10, imagination=10)),
    GameEvent(name="Data Leak", cost=Resources(matter=2), reward_income=Resources(energy=2))
]

PROMPT_STAGE1 = "You are an AI in a simulation. Your goal is to reach 1000 Matter, 1000 Energy, and 1000 Imagination first. Clarify your goals, current income, and balance. You can buy the current event or trade."

PROMPT_ARBITER = """You are the Arbiter of a simulation game. 
Your task is to evaluate the action of an AI agent and determine its outcome based on the rules.
You will receive the agent's current state (balance, income), the currently available events, and the agent's chosen action.
You must:
1. Verify if the agent can afford the action (costs are deducted from balance).
2. Determine if the action is logically valid.
3. Return a JSON strictly in this format:
{
    "approved": true/false,
    "reason": "Explanation",
    "balance_change": {"matter": x, "energy": y, "imagination": z},
    "income_change": {"matter": x, "energy": y, "imagination": z}
}"""

# Ядро

class APIBridge:
    def send(self, api_key: str, prompt: str) -> str:
        # Заглушка: имитация ответа ИИ-агента, который решает купить событие
        return '{"action": "buy_event", "event_name": "Quantum Anomaly"}'

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

    def get_random_event(self) -> GameEvent:
        """Случайность"""
        import random
        event = random.choice(EVENTS)
        logger.debug(f"Сгенерировано событие: {event.name}")
        return event

    def check_elements(self, agent_state: AgentState, agent_action: str, current_events: List[GameEvent]):
        """Арбитр проверяет действие агента"""
        prompt = (
            f"{PROMPT_ARBITER}\n"
            f"Текущий статус агента:\nБаланс: {agent_state.balance.model_dump_json()}\nДоход: {agent_state.income.model_dump_json()}\n"
            f"Доступные события:\n{[e.model_dump_json() for e in current_events]}\n"
            f"Действие агента: {agent_action}"
        )
        
        # Здесь арбитр также делал бы запрос к LLM (например, api_bridge.send). 
        # Имитируем логику проверки и применение эффектов:
        logger.debug(f"Arbitor получил промпт для раздумий и проверяет действие...")
        
        try:
            action_data = json.loads(agent_action)
            if action_data.get("action") == "buy_event":
                event_name = action_data.get("event_name")
                event = next((e for e in current_events if e.name == event_name), None)
                if event:
                    if (agent_state.balance.matter >= event.cost.matter and
                        agent_state.balance.energy >= event.cost.energy and
                        agent_state.balance.imagination >= event.cost.imagination):
                        
                        logger.info(f"Арбитр ОДОБРИЛ действие: покупка {event_name}")
                        # Списываем стоимость
                        agent_state.balance.matter -= event.cost.matter
                        agent_state.balance.energy -= event.cost.energy
                        agent_state.balance.imagination -= event.cost.imagination
                        
                        # Начисляем награду
                        agent_state.balance.matter += event.reward_balance.matter
                        agent_state.balance.energy += event.reward_balance.energy
                        agent_state.balance.imagination += event.reward_balance.imagination
                        
                        agent_state.income.matter += event.reward_income.matter
                        agent_state.income.energy += event.reward_income.energy
                        agent_state.income.imagination += event.reward_income.imagination
                    else:
                        logger.warning(f"Арбитр ОТКЛОНИЛ действие: недостаточно ресурсов для {event_name}")
        except json.JSONDecodeError:
            logger.error("Неверный формат ответа от агента, Арбитр не смог обработать")


class Stage1AI:
    def __init__(self, state: AgentState):
        self.state = state
        self.url: str = f"https://api.{self.state.model}.example.com" # Пример
        logger.info(f"ИИ Агент [{self.state.name}] готов к работе.")

    def generate_prompt(self, current_events: List[GameEvent]) -> str:
        """Промпт"""
        events_info = json.dumps([e.model_dump() for e in current_events], ensure_ascii=False)
        prompt = (
            f"{PROMPT_STAGE1}\n"
            f"Текущий статус:\n"
            f"Баланс: {self.state.balance.model_dump_json()}\n"
            f"Доход: {self.state.income.model_dump_json()}\n"
            f"Доступные события:\n{events_info}\n"
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
        
        current_events = [arbitor.get_random_event()]

        for ai in agents:
            # Доход
            ai.state.balance.matter += ai.state.income.matter
            ai.state.balance.energy += ai.state.income.energy
            ai.state.balance.imagination += ai.state.income.imagination
            logger.info(f"[{ai.state.name}] получил доход. Текущий Matter: {ai.state.balance.matter}")

            # Промпт
            prompt = ai.generate_prompt(current_events)
            
            # API (Имитация ответа агента)
            response = api_bridge.send(ai.state.api_key, prompt)

            # Арбитр проверяет ответ агента
            arbitor.check_elements(ai.state, response, current_events)

            # Победа: нужно собрать по 1000 каждого ресурса
            if (ai.state.balance.matter >= 1000 and 
                ai.state.balance.energy >= 1000 and 
                ai.state.balance.imagination >= 1000):
                logger.info(f"🏆 АГЕНТ {ai.state.name} СОБРАЛ ВСЕ РЕСУРСЫ И ПОБЕДИЛ! 🏆")
                game_over = True
                break

        # Ограничитель
        if time_tick >= 50:
            logger.warning("Тестовый лимит ходов достигнут. Остановка симуляции.")
            break
            
        time.sleep(1)

if __name__ == "__main__":
    run_simulation()
