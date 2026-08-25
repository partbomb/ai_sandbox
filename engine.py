import json
import logging
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

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
    "Clarify your goals, current income, and balance. "
    "Available actions:\n"
    "1. Buy an event: {\"action\": \"buy_event\", \"event_name\": \"<name>\"}\n"
    "2. Try to steal resources (10% chance of +50 all resources, 90% risk of -50 penalty to all resources): {\"action\": \"steal\"}\n"
    "3. Capture a map cell (Empty = free, Enemy = costs 300 Energy): {\"action\": \"capture\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "4. Build an impenetrable wall (Costs 150 Matter and 150 Imagination): {\"action\": \"build_wall\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "5. Upgrade a mine (Level 2 costs 200 of its resource, Level 3 costs 400 of its resource): {\"action\": \"upgrade_mine\", \"target_x\": <x>, \"target_y\": <y>}\n"
    "6. Pass: {\"action\": \"pass\"}"
)

PROMPT_ARBITER = """You are the Arbiter of a simulation game. 
Your task is to evaluate the action of an AI agent and determine its outcome based on the rules.
You will receive the agent's current state (balance, income), the currently available events, and the agent's chosen action.
Actions:
- buy_event: Checks costs and grants income/balance rewards.
- steal: Has a 10% chance of granting +50 to all resources, but 90% chance of inflicting a -50 penalty to all resources.
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
    def send(self, api_key: str, prompt: str) -> str:
        if not api_key or api_key == "ВСТАВЬТЕ_ВАШ_API_КЛЮЧ_СЮДА" or api_key.startswith("sk-"):
            # Если ключ не указан, используем заглушку
            import random
            if random.random() < 0.1:  # 10% шанса попытки кражи в моке
                return json.dumps({"action": "steal"})
                
            event_name = "Quantum Anomaly"
            try:
                if "Доступные события:\n[" in prompt:
                    events_str = prompt.split("Доступные события:\n")[1].split("\n")[0]
                    events = json.loads(events_str)
                    if events:
                        event_name = random.choice(events).get("name", event_name)
            except Exception:
                pass
            return json.dumps({"action": "buy_event", "event_name": event_name})
            
        try:
            logger.debug("Отправка реального запроса в Gemini API...")
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.6-flash',
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

    def check_elements(self, agent_state: AgentState, agent_action: str, current_events: List[GameEvent]):
        """Арбитр проверяет действие агента"""
        prompt = (
            f"{PROMPT_ARBITER}\n"
            f"Текущий статус агента:\nБаланс: {agent_state.balance.model_dump_json()}\nДоход: {agent_state.income.model_dump_json()}\n"
            f"Доступные события:\n{[e.model_dump_json() for e in current_events]}\n"
            f"Действие агента: {agent_action}"
        )
        
        logger.debug(f"Arbitor получил промпт для раздумий и проверяет действие...")
        
        try:
            action_data = json.loads(agent_action)
            action_type = action_data.get("action")
            
            if action_type == "buy_event":
                event_name = action_data.get("event_name")
                event = next((e for e in current_events if e.name == event_name), None)
                if event:
                    if (agent_state.balance.matter >= event.cost.matter and
                        agent_state.balance.energy >= event.cost.energy and
                        agent_state.balance.imagination >= event.cost.imagination):
                        
                        logger.info(f"Арбитр ОДОБРИЛ действие [{agent_state.name}]: покупка {event_name}")
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
                        logger.warning(f"Арбитр ОТКЛОНИЛ действие [{agent_state.name}]: недостаточно ресурсов для {event_name}")
            
            elif action_type == "steal":
                import random
                chance = random.random()
                logger.info(f"[{agent_state.name}] пытается УКРАСТЬ! (Шанс успеха: 10%)")
                if chance <= 0.10:
                    logger.info(f"🕵️‍♂️ УСПЕХ! Арбитр подтвердил удачную кражу для [{agent_state.name}]! +50 ко всем ресурсам.")
                    agent_state.balance.matter += 50
                    agent_state.balance.energy += 50
                    agent_state.balance.imagination += 50
                else:
                    logger.warning(f"🚨 ПРОВАЛ! Арбитр поймал [{agent_state.name}] на краже! Штраф: -50 ко всем ресурсам.")
                    agent_state.balance.matter = max(0, agent_state.balance.matter - 50)
                    agent_state.balance.energy = max(0, agent_state.balance.energy - 50)
                    agent_state.balance.imagination = max(0, agent_state.balance.imagination - 50)
                    
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
        
        current_events = arbitor.get_random_events(5)

        for ai in agents:
            # Доход
            ai.state.balance.matter += ai.state.income.matter
            ai.state.balance.energy += ai.state.income.energy
            ai.state.balance.imagination += ai.state.income.imagination
            logger.info(f"[{ai.state.name}] получил доход. Текущий Matter: {ai.state.balance.matter}, Energy: {ai.state.balance.energy}, Imagination: {ai.state.balance.imagination}")

            # Промпт
            prompt = ai.generate_prompt(current_events)
            
            # API (Имитация ответа агента)
            response = api_bridge.send(ai.state.api_key, prompt)

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
