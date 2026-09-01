"""
play_rl.py — Тест обученного RL-агента в AI Sandbox.

Использование:
    python play_rl.py                                           # Играть с лучшей моделью
    python play_rl.py --model rl_models/sandbox_ppo_final       # Указать модель
    python play_rl.py --episodes 20                             # Сколько игр показать
    python play_rl.py --no-render                               # Без визуализации (только статистика)
"""

import argparse
import os
import sys
import numpy as np

from stable_baselines3 import PPO, DQN

import rl_env
from rl_env import AISandboxEnv, NUM_ACTIONS


# Названия действий для лога
ACTION_NAMES = (
    ["MOVE_N", "MOVE_S", "MOVE_E", "MOVE_W"]
    + [f"ATTACK_{i}" for i in range(8)]
    + [f"CAPTURE_{i}" for i in range(9)]
    + [f"BUILD_{i}" for i in range(8)]
    + [f"RESEARCH_{i}" for i in range(9)]
    + ["PASS"]
)


def play(model_path: str, episodes: int = 5, render: bool = True):
    """Запускает обученного агента и показывает его игру."""

    # --- Определяем тип модели ---
    if "dqn" in model_path.lower():
        model = DQN.load(model_path)
        algo_name = "DQN"
    else:
        model = PPO.load(model_path)
        algo_name = "PPO"

    print(f"\n🤖 Загружена модель: {model_path} ({algo_name})")
    print(f"   Играем {episodes} эпизодов...\n")

    env = AISandboxEnv(render_mode="human" if render else None)

    # Статистика
    wins = 0
    losses = 0
    timeouts = 0
    total_rewards = []
    total_steps = []

    for ep in range(episodes):
        obs, info = env.reset()
        done = False
        ep_reward = 0.0
        step_count = 0
        action_counts = [0] * NUM_ACTIONS

        print(f"\n{'='*50}")
        print(f"  📺 ЭПИЗОД {ep + 1}/{episodes}")
        print(f"{'='*50}")

        while not done:
            # Модель выбирает действие
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)
            action_counts[action] += 1

            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            ep_reward += reward
            step_count += 1

            if render and step_count % 10 == 0:
                action_name = ACTION_NAMES[action] if action < len(ACTION_NAMES) else f"ACT_{action}"
                print(f"    Ход {step_count}: {action_name} → r={reward:.2f}")

        # Результат эпизода
        result = info.get("result", "UNKNOWN")
        if result == "WIN":
            wins += 1
            emoji = "🏆"
        elif result == "LOSE":
            losses += 1
            emoji = "💀"
        else:
            timeouts += 1
            emoji = "⏰"

        total_rewards.append(ep_reward)
        total_steps.append(step_count)

        print(f"\n  {emoji} Результат: {result}")
        print(f"  💰 Reward: {ep_reward:.2f} | Ходов: {step_count}")

        # Топ-5 действий
        top_actions = sorted(range(NUM_ACTIONS), key=lambda i: action_counts[i], reverse=True)[:5]
        print(f"  📊 Топ действий:")
        for a in top_actions:
            if action_counts[a] > 0:
                name = ACTION_NAMES[a] if a < len(ACTION_NAMES) else f"ACT_{a}"
                print(f"      {name}: {action_counts[a]}x")

    # --- Итоговая статистика ---
    print(f"\n{'='*50}")
    print(f"  📊 ИТОГИ ({episodes} эпизодов)")
    print(f"{'='*50}")
    print(f"  🏆 Победы:  {wins}/{episodes} ({100*wins/episodes:.0f}%)")
    print(f"  💀 Поражения: {losses}/{episodes}")
    print(f"  ⏰ Таймауты:  {timeouts}/{episodes}")
    print(f"  💰 Средний Reward: {np.mean(total_rewards):.2f}")
    print(f"  📏 Средняя длина:  {np.mean(total_steps):.0f} ходов")
    print(f"{'='*50}\n")


def play_random(episodes: int = 5):
    """Играет случайными действиями (baseline для сравнения)."""
    print(f"\n🎲 Random Agent Baseline ({episodes} эпизодов)...\n")

    env = AISandboxEnv()
    wins = 0
    rewards = []

    for ep in range(episodes):
        obs, _ = env.reset()
        done = False
        ep_reward = 0.0

        while not done:
            action = env.action_space.sample()
            obs, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
            ep_reward += reward

        rewards.append(ep_reward)

    print(f"  🎲 Random: Avg Reward = {np.mean(rewards):.2f} | Wins = {wins}")
    return np.mean(rewards)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест RL-агента")
    parser.add_argument("--model", type=str, default="rl_models/best/best_model",
                        help="Путь к .zip модели (без .zip)")
    parser.add_argument("--episodes", type=int, default=5, help="Кол-во эпизодов")
    parser.add_argument("--no-render", action="store_true", help="Без визуализации")
    parser.add_argument("--random", action="store_true", help="Baseline: случайный агент")
    args = parser.parse_args()

    if args.random:
        play_random(args.episodes)
    else:
        if not os.path.exists(args.model + ".zip") and not os.path.exists(args.model):
            print(f"❌ Модель не найдена: {args.model}")
            print(f"   Сначала обучи: python train_rl.py")
            sys.exit(1)
        play(args.model, args.episodes, render=not args.no_render)
