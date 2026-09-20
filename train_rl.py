"""
train_rl.py — Скрипт обучения RL-агента (PPO) для AI Sandbox.

Использование:
    python train_rl.py                    # Обучить на 500K шагов
    python train_rl.py --steps 1000000    # Обучить на 1M шагов
    python train_rl.py --algo DQN         # Использовать DQN вместо PPO
    python train_rl.py --resume            # Продолжить тренировку с последнего чекпоинта
    python train_rl.py --resume rl_models/sandbox_ppo_250000_steps  # С конкретного чекпоинта

Результат:
    Сохраняет модель в папку ./rl_models/
    Логи TensorBoard в ./rl_logs/
"""

import argparse
import os
import sys
import time
import numpy as np

from stable_baselines3 import PPO, DQN
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import (
    EvalCallback, CheckpointCallback, BaseCallback
)
from stable_baselines3.common.monitor import Monitor

# Импортируем нашу среду (регистрирует AISandbox-v1)
import rl_env


class RewardLoggerCallback(BaseCallback):
    """Логирует среднюю награду каждые N шагов."""
    def __init__(self, log_freq=5000, verbose=0):
        super().__init__(verbose)
        self.log_freq = log_freq
        self.episode_rewards = []
        self.episode_lengths = []
        self.episode_wins = []

    def _on_step(self) -> bool:
        # Собираем завершённые эпизоды
        for info in self.locals.get("infos", []):
            if "episode" in info:
                self.episode_rewards.append(info["episode"]["r"])
                self.episode_lengths.append(info["episode"]["l"])
                self.episode_wins.append(1 if info.get("result") == "WIN" else 0)

        if self.num_timesteps % self.log_freq == 0 and self.episode_rewards:
            mean_r = np.mean(self.episode_rewards[-100:])
            mean_l = np.mean(self.episode_lengths[-100:])
            win_rate = np.mean(self.episode_wins[-100:]) * 100 if self.episode_wins else 0.0
            print(f"  [{self.num_timesteps:>8} steps] "
                  f"Reward: {mean_r:>8.2f} | "
                  f"Ep Length: {mean_l:>6.0f} | "
                  f"Win Rate: {win_rate:>5.1f}% | "
                  f"Episodes: {len(self.episode_rewards)}")
        return True


def _find_best_checkpoint(save_dir: str, algo_name: str) -> str | None:
    """Находит лучший чекпоинт для продолжения тренировки."""
    candidates = [
        os.path.join(save_dir, f"sandbox_{algo_name.lower()}_final"),
        os.path.join(save_dir, "best", "best_model"),
    ]
    # Ищем чекпоинты по шагам (берём самый поздний)
    if os.path.exists(save_dir):
        step_files = []
        for f in os.listdir(save_dir):
            if f.startswith(f"sandbox_{algo_name.lower()}_") and f.endswith("_steps.zip"):
                try:
                    steps = int(f.split("_")[-2])
                    step_files.append((steps, os.path.join(save_dir, f[:-4])))
                except ValueError:
                    continue
        step_files.sort(key=lambda x: x[0], reverse=True)
        candidates.extend([path for _, path in step_files])

    for c in candidates:
        if os.path.exists(c + ".zip") or os.path.exists(c):
            return c
    return None


def train(algo_name: str = "PPO", total_steps: int = 500_000,
          n_envs: int = 4, save_dir: str = "rl_models", log_dir: str = "rl_logs",
          resume_path: str | None = None):
    """Основная функция обучения."""

    os.makedirs(save_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    print("=" * 60)
    print(f"  🤖 AI Sandbox — Обучение RL-агента")
    print(f"  Алгоритм:    {algo_name}")
    print(f"  Шаги:        {total_steps:,}")
    print(f"  Параллельно: {n_envs} среды")
    if resume_path:
        print(f"  📂 Продолжение: {resume_path}")
    print("=" * 60)

    # --- Создаём параллельные среды ---
    env = make_vec_env("AISandbox-v1", n_envs=n_envs)

    # --- Среда для оценки (1 среда, без параллелизма) ---
    eval_env = Monitor(rl_env.AISandboxEnv())

    # --- Загрузка или создание модели ---
    if resume_path:
        # Продолжаем тренировку с существующей модели
        AlgoClass = PPO if algo_name.upper() == "PPO" else DQN
        model = AlgoClass.load(resume_path, env=env, device="cpu")
        model.tensorboard_log = log_dir
        print(f"\n  ✅ Модель загружена из: {resume_path}")
        print(f"    Продолжаем обучение на {total_steps:,} дополнительных шагов\n")

    elif algo_name.upper() == "PPO":
        model = PPO(
            "MlpPolicy",               # Полносвязная нейросеть
            env,
            learning_rate=3e-4,         # Скорость обучения
            n_steps=2048,               # Шагов перед обновлением
            batch_size=64,              # Размер батча
            n_epochs=10,                # Эпох оптимизации
            gamma=0.99,                 # Дисконт будущих наград
            gae_lambda=0.95,            # GAE lambda
            clip_range=0.2,             # Диапазон клиппинга PPO
            ent_coef=0.01,              # Коэффициент энтропии (исследование)
            verbose=1,
            tensorboard_log=log_dir,
            device="cpu",              # CPU быстрее для MlpPolicy
        )
        print("\n  Архитектура PPO:")
        print(f"    Policy:        MlpPolicy (2 слоя по 64 нейрона)")
        print(f"    Learning Rate: 3e-4")
        print(f"    Batch Size:    64")
        print(f"    Gamma:         0.99 (дисконт)")
        print(f"    Entropy Coef:  0.01 (баланс исследования)\n")

    elif algo_name.upper() == "DQN":
        model = DQN(
            "MlpPolicy",
            env,
            learning_rate=1e-4,
            buffer_size=100_000,        # Replay buffer
            learning_starts=10_000,     # Начать учиться после N шагов
            batch_size=64,
            gamma=0.99,
            exploration_fraction=0.3,   # 30% шагов — исследование
            exploration_final_eps=0.05, # Минимальный epsilon
            target_update_interval=1000,
            verbose=1,
            tensorboard_log=log_dir,
            device="cpu",
        )
        print("\n  Архитектура DQN:")
        print(f"    Policy:        MlpPolicy")
        print(f"    Replay Buffer: 100,000")
        print(f"    Exploration:   30% → 5% epsilon\n")
    else:
        print(f"Неизвестный алгоритм: {algo_name}. Используй PPO или DQN.")
        sys.exit(1)

    # --- Callbacks ---
    callbacks = [
        RewardLoggerCallback(log_freq=5000),
        CheckpointCallback(
            save_freq=max(10_000, 50_000 // n_envs),
            save_path=save_dir,
            name_prefix=f"sandbox_{algo_name.lower()}"
        ),
        EvalCallback(
            eval_env,
            best_model_save_path=os.path.join(save_dir, "best"),
            eval_freq=max(1000, 10_000 // n_envs),
            n_eval_episodes=5,
            deterministic=True,
        ),
    ]

    # --- Обучение ---
    print(f"\n🚀 Начало обучения ({total_steps:,} шагов)...\n")
    start_time = time.time()

    model.learn(
        total_timesteps=total_steps,
        callback=callbacks,
        progress_bar=True,
    )

    elapsed = time.time() - start_time
    print(f"\n✅ Обучение завершено за {elapsed:.0f} сек ({elapsed/60:.1f} мин)")

    # --- Сохранение ---
    final_path = os.path.join(save_dir, f"sandbox_{algo_name.lower()}_final")
    model.save(final_path)
    print(f"💾 Модель сохранена: {final_path}.zip")

    print(f"\n📊 TensorBoard: tensorboard --logdir {log_dir}")
    print(f"🎮 Тест:        python play_rl.py --model {final_path}")

    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Обучение RL-агента для AI Sandbox")
    parser.add_argument("--algo", type=str, default="PPO", help="Алгоритм: PPO или DQN")
    parser.add_argument("--steps", type=int, default=500_000, help="Количество шагов обучения")
    parser.add_argument("--envs", type=int, default=4, help="Количество параллельных сред")
    parser.add_argument("--resume", nargs="?", const="auto", default=None,
                        help="Продолжить тренировку. Без аргумента — найдёт последний чекпоинт. "
                             "С аргументом — путь к модели (без .zip)")
    args = parser.parse_args()

    # Обработка --resume
    resume_path = None
    if args.resume is not None:
        if args.resume == "auto":
            resume_path = _find_best_checkpoint("rl_models", args.algo)
            if not resume_path:
                print("❌ Не найдено чекпоинтов для продолжения.")
                print("   Сначала обучи: python train_rl.py")
                sys.exit(1)
            print(f"🔍 Найден чекпоинт: {resume_path}")
        else:
            resume_path = args.resume
            if not os.path.exists(resume_path + ".zip") and not os.path.exists(resume_path):
                print(f"❌ Модель не найдена: {resume_path}")
                sys.exit(1)

    train(algo_name=args.algo, total_steps=args.steps, n_envs=args.envs,
          resume_path=resume_path)
