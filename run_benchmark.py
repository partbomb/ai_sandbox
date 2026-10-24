#!/usr/bin/env python3
"""
run_benchmark.py — Automated Scientific Benchmark & Memory Ablation Suite for AI Sandbox.

Executes N=20 fast headless multi-agent simulations (without asyncio.sleep) across
three experimental conditions:
  1. Full Memory LLM vs RL (PPO)                       [use_compass=True,  use_short_memory=True]
  2. Ablation: No Strategic Compass (Only Short-Term)  [use_compass=False, use_short_memory=True]
  3. Ablation: No Memory (Pure Reactive)               [use_compass=False, use_short_memory=False]

Outputs a publication-ready summary table (Win Rate %, Survival Rate %, Fixation Loop Rate %,
Avg Net Worth) to the console and exports detailed telemetry to `data/benchmark_results.csv`.
"""

import argparse
import asyncio
import csv
import logging
import os
import random
import time
from typing import Dict, List, Any

import numpy as np
import world

# Подавляем подробный лог каждого шага во время быстрого бенчмарка
logging.getLogger("WorldMap").setLevel(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)


EXPERIMENTAL_MODES = [
    {
        "id": "full_memory",
        "name": "Full Memory LLM vs RL (PPO)",
        "use_compass": True,
        "use_short_memory": True,
    },
    {
        "id": "no_compass",
        "name": "Ablation: No Strategic Compass (Only Short-Term Memory)",
        "use_compass": False,
        "use_short_memory": True,
    },
    {
        "id": "no_memory",
        "name": "Ablation: No Memory (Pure Reactive)",
        "use_compass": False,
        "use_short_memory": False,
    },
]


def load_shared_rl_model(model_path: str = "rl_models/best/best_model"):
    """Загружает веса PPO один раз для ускорения серии из 60 эпизодов."""
    probe = world.Stage2AI(
        name="RL-Loader",
        api_key="",
        model="PPO",
        start_pos=world.Position(x=0, y=0),
        init_income={"matter": 10, "energy": 10, "imagination": 10},
        is_rl=True,
        rl_model_path=model_path,
    )
    return probe.rl_model


async def run_single_episode(
    mode_cfg: Dict[str, Any],
    shared_rl_model: Any,
    episode_idx: int,
    max_ticks: int = 55,
    seed: int = 42,
) -> Dict[str, Any]:
    """Проводит один быстрый эпизод симуляции без задержек asyncio.sleep."""
    rng_seed = seed + episode_idx * 137
    random.seed(rng_seed)
    np.random.seed(rng_seed)

    world_map = world.MapCore(width=10, height=10)
    world_map.spawn_mines()
    world_map.spawn_casinos(4)
    arbiter = world.ArbitorPhysical()

    use_compass = mode_cfg["use_compass"]
    use_stm = mode_cfg["use_short_memory"]

    # Спавним 3 исследуемых архетипа LLM + обученного RL-PPO-Bot
    spawn_coords = [(1, 1), (8, 1), (1, 8), (8, 8)]
    random.shuffle(spawn_coords)

    alpha = world.Stage2AI(
        name="Alpha-Net",
        api_key="",  # Zero-Key fast evaluation
        model="gemini-3.5-flash-lite",
        start_pos=world.Position(x=spawn_coords[0][0], y=spawn_coords[0][1]),
        init_income={"matter": 10, "energy": 10, "imagination": 10},
        use_compass=use_compass,
        use_short_memory=use_stm,
    )
    beta = world.Stage2AI(
        name="Beta-Core",
        api_key="",
        model="gemini-3.5-flash-lite",
        start_pos=world.Position(x=spawn_coords[1][0], y=spawn_coords[1][1]),
        init_income={"matter": 10, "energy": 10, "imagination": 10},
        use_compass=use_compass,
        use_short_memory=use_stm,
    )
    omega = world.Stage2AI(
        name="Omega-Robot",
        api_key="",
        model="gemini-3.5-flash-lite",
        start_pos=world.Position(x=spawn_coords[2][0], y=spawn_coords[2][1]),
        init_income={"matter": 10, "energy": 10, "imagination": 10},
        use_compass=use_compass,
        use_short_memory=use_stm,
    )
    rl_bot = world.Stage2AI(
        name="RL-PPO-Bot",
        api_key="",
        model="PPO-Policy",
        start_pos=world.Position(x=spawn_coords[3][0], y=spawn_coords[3][1]),
        init_income={"matter": 10, "energy": 10, "imagination": 10},
        is_rl=True,
        rl_model_path="",  # Передаем уже загруженную модель ниже
    )
    rl_bot.rl_model = shared_rl_model

    agents: List[world.Stage2AI] = [alpha, beta, omega, rl_bot]
    total_mines = sum(1 for row in world_map.grid for c in row if c.resource_type is not None)

    winner = None
    alive_ticks = {a.name: 0 for a in agents}

    for tick in range(1, max_ticks + 1):
        # 1. Ход каждого живого агента
        for agent in agents:
            if agent.is_dead:
                continue
            action_data = await agent.get_action_from_llm(world_map, agents)
            result = await arbiter.execute_action(agent, action_data, world_map, agents)

            # Обновление краткосрочной памяти
            action_name = action_data.get("action", "PASS")
            journal_entry = f"Ход {tick}: {action_name} -> {result}"
            agent.short_term_memory.append(journal_entry)
            if len(agent.short_term_memory) > 4:
                agent.short_term_memory.pop(0)

            # Обновление долгосрочной памяти (только если use_compass=True)
            new_compass = action_data.get("new_compass")
            if getattr(agent, "use_compass", True) and new_compass and isinstance(new_compass, str) and new_compass.strip():
                agent.long_term_memory = new_compass.strip()

        # 2. Экономический тик карты (доход от шахт, голод, возрождение, проверка победы)
        for agent in agents:
            if agent.is_dead:
                if getattr(agent, "respawn_timer", 0) > 0:
                    agent.respawn_timer -= 1
                    if agent.respawn_timer <= 0:
                        agent.is_dead = False
                        agent.hp = 100
                        agent.balance = {"matter": 50, "energy": 50, "imagination": 50}
                        agent.position = world.Position(x=agent.base_position.x, y=agent.base_position.y)
                continue

            alive_ticks[agent.name] += 1
            agent.score = sum(1 for row in world_map.grid for cell in row if cell.owner_id == agent.name)

            matter_mines = sum(
                1 for row in world_map.grid for c in row if c.owner_id == agent.name and c.resource_type == "Matter"
            )
            energy_mines = sum(
                1 for row in world_map.grid for c in row if c.owner_id == agent.name and c.resource_type == "Energy"
            )
            imag_mines = sum(
                1 for row in world_map.grid for c in row if c.owner_id == agent.name and c.resource_type == "Imagination"
            )

            income_base = 12 if "economy_lvl_2" in agent.unlocked_techs else 10
            agent.balance["matter"] += matter_mines * income_base
            agent.balance["energy"] += energy_mines * income_base
            agent.balance["imagination"] += imag_mines * income_base

            # Голод (-5 Energy за тик)
            agent.balance["energy"] -= 5
            if agent.balance["energy"] <= 0:
                agent.balance["energy"] = 0
                if not agent.is_dead:
                    agent.is_dead = True
                    agent.deaths_count += 1
                    agent.respawn_timer = 5
                    c = world_map.get_cell(agent.position.x, agent.position.y)
                    if c:
                        for res in ("matter", "energy", "imagination"):
                            c.loot[res] = c.loot.get(res, 0) + agent.balance[res]
                            agent.balance[res] = 0
                continue

            # Условие 1: Технологическая Сингулярность
            if (
                agent.balance["matter"] >= 5000
                and agent.balance["energy"] >= 5000
                and agent.balance["imagination"] >= 5000
            ):
                winner = agent.name
                break

            # Условие 2: Абсолютная Монополия (80% шахт)
            agent_mines = matter_mines + energy_mines + imag_mines
            if total_mines > 0 and (agent_mines / total_mines) >= 0.8:
                winner = agent.name
                break

        if winner is not None:
            break

    # Если досрочной победы не было, победитель определяется по комплексному индексу (шахты * 250 + капитал + тех * 150)
    if winner is None:
        best_agent = max(
            agents,
            key=lambda a: a.score * 250 + sum(a.balance.values()) + len(a.unlocked_techs) * 150 - a.deaths_count * 200,
        )
        winner = best_agent.name

    llm_agents = [alpha, beta, omega]
    llm_won = 1 if winner in ("Alpha-Net", "Beta-Core", "Omega-Robot") else 0
    rl_won = 1 if winner == "RL-PPO-Bot" else 0

    # Метрики по LLM-агентам за эпизод
    llm_survival_rates = [(alive_ticks[a.name] / max_ticks) * 100.0 for a in llm_agents]
    llm_fixation_rates = [a.get_metrics()["fixation_rate"] for a in llm_agents]
    llm_invalid_rates = [a.get_metrics()["invalid_rate"] for a in llm_agents]
    llm_net_worths = [sum(a.balance.values()) for a in llm_agents]

    return {
        "winner": winner,
        "llm_won": llm_won,
        "rl_won": rl_won,
        "llm_survival_rate": float(np.mean(llm_survival_rates)),
        "llm_fixation_rate": float(np.mean(llm_fixation_rates)),
        "llm_invalid_rate": float(np.mean(llm_invalid_rates)),
        "llm_avg_net_worth": float(np.mean(llm_net_worths)),
        "rl_net_worth": float(sum(rl_bot.balance.values())),
        "per_agent": {
            a.name: {
                "won": 1 if winner == a.name else 0,
                "survival_rate": (alive_ticks[a.name] / max_ticks) * 100.0,
                "fixation_rate": a.get_metrics()["fixation_rate"],
                "invalid_rate": a.get_metrics()["invalid_rate"],
                "net_worth": sum(a.balance.values()),
                "score": a.score,
                "deaths": a.deaths_count,
                "techs": len(a.unlocked_techs),
            }
            for a in agents
        },
    }


async def run_benchmark_suite(num_episodes: int = 20, max_ticks: int = 55) -> List[Dict[str, Any]]:
    t0 = time.time()
    shared_rl_model = load_shared_rl_model("rl_models/best/best_model")

    summary_rows = []

    for mode_cfg in EXPERIMENTAL_MODES:
        episodes_data = []
        for ep in range(num_episodes):
            ep_res = await run_single_episode(mode_cfg, shared_rl_model, ep, max_ticks=max_ticks)
            episodes_data.append(ep_res)

        llm_win_rate = np.mean([d["llm_won"] for d in episodes_data]) * 100.0
        rl_win_rate = np.mean([d["rl_won"] for d in episodes_data]) * 100.0
        survival_rate = np.mean([d["llm_survival_rate"] for d in episodes_data])
        fixation_rate = np.mean([d["llm_fixation_rate"] for d in episodes_data])
        invalid_rate = np.mean([d["llm_invalid_rate"] for d in episodes_data])
        avg_net_worth = np.mean([d["llm_avg_net_worth"] for d in episodes_data])
        rl_avg_net_worth = np.mean([d["rl_net_worth"] for d in episodes_data])

        # Детализация по каждому архетипу
        archetype_breakdown = {}
        for agent_name in ("Alpha-Net", "Beta-Core", "Omega-Robot", "RL-PPO-Bot"):
            archetype_breakdown[agent_name] = {
                "win_rate": round(float(np.mean([d["per_agent"][agent_name]["won"] for d in episodes_data]) * 100.0), 1),
                "survival_rate": round(float(np.mean([d["per_agent"][agent_name]["survival_rate"] for d in episodes_data])), 1),
                "fixation_rate": round(float(np.mean([d["per_agent"][agent_name]["fixation_rate"] for d in episodes_data])), 1),
                "avg_net_worth": round(float(np.mean([d["per_agent"][agent_name]["net_worth"] for d in episodes_data])), 1),
                "avg_deaths": round(float(np.mean([d["per_agent"][agent_name]["deaths"] for d in episodes_data])), 2),
            }

        summary_rows.append(
            {
                "mode_id": mode_cfg["id"],
                "mode_name": mode_cfg["name"],
                "episodes": num_episodes,
                "use_compass": mode_cfg["use_compass"],
                "use_short_memory": mode_cfg["use_short_memory"],
                "llm_win_rate_pct": round(float(llm_win_rate), 1),
                "rl_win_rate_pct": round(float(rl_win_rate), 1),
                "survival_rate_pct": round(float(survival_rate), 1),
                "fixation_loop_rate_pct": round(float(fixation_rate), 1),
                "invalid_action_rate_pct": round(float(invalid_rate), 1),
                "avg_net_worth": round(float(avg_net_worth), 1),
                "rl_avg_net_worth": round(float(rl_avg_net_worth), 1),
                "archetypes": archetype_breakdown,
            }
        )

    elapsed = time.time() - t0
    print_results(summary_rows, num_episodes, max_ticks, elapsed)
    save_csv(summary_rows, "data/benchmark_results.csv")
    return summary_rows


def print_results(rows: List[Dict[str, Any]], num_episodes: int, max_ticks: int, elapsed: float):
    """Выводит красивую таблицу результатов в консоль (с использованием rich или форматированного ASCII)."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()
        console.print()
        console.print(
            Panel.fit(
                f"[bold cyan]🧪 AI SANDBOX — SCIENTIFIC ABLATION & RL BENCHMARK SUITE[/bold cyan]\n"
                f"[dim]Episodes per condition: N={num_episodes} | Horizon: T={max_ticks} ticks | "
                f"Total simulations: {num_episodes * len(rows)} | Elapsed: {elapsed:.2f}s[/dim]",
                border_style="cyan",
            )
        )

        table = Table(title="📊 Aggregate Experimental Results (LLM Cohort vs PPO RL Baseline)", show_lines=True)
        table.add_column("Experimental Condition", style="bold white", min_width=38)
        table.add_column("LLM Win Rate %", justify="right", style="bold green")
        table.add_column("RL Win Rate %", justify="right", style="bold magenta")
        table.add_column("Survival Rate %", justify="right", style="cyan")
        table.add_column("Fixation Loop Rate %", justify="right", style="yellow")
        table.add_column("Avg Net Worth", justify="right", style="bold blue")

        for r in rows:
            table.add_row(
                r["mode_name"],
                f"{r['llm_win_rate_pct']:.1f}%",
                f"{r['rl_win_rate_pct']:.1f}%",
                f"{r['survival_rate_pct']:.1f}%",
                f"{r['fixation_loop_rate_pct']:.1f}%",
                f"{r['avg_net_worth']:.1f}",
            )

        console.print(table)

        # Таблица по архетипам
        arch_table = Table(title="🤖 Per-Archetype Breakdown Across Memory Regimes", show_lines=True)
        arch_table.add_column("Condition", style="white")
        arch_table.add_column("Agent (Archetype)", style="bold")
        arch_table.add_column("Win Rate %", justify="right")
        arch_table.add_column("Survival %", justify="right")
        arch_table.add_column("Fixation %", justify="right")
        arch_table.add_column("Avg Net Worth", justify="right")

        for r in rows:
            for agent_name, stats in r["archetypes"].items():
                arch_table.add_row(
                    r["mode_id"],
                    agent_name,
                    f"{stats['win_rate']:.1f}%",
                    f"{stats['survival_rate']:.1f}%",
                    f"{stats['fixation_rate']:.1f}%",
                    f"{stats['avg_net_worth']:.1f}",
                )
        console.print(arch_table)
        console.print("[bold green]✅ Saved full benchmark telemetry to:[/bold green] [underline]data/benchmark_results.csv[/underline]\n")
    except ImportError:
        print("=" * 105)
        print(f"AI SANDBOX — SCIENTIFIC BENCHMARK (N={num_episodes} per mode, T={max_ticks} ticks, Elapsed={elapsed:.2f}s)")
        print("=" * 105)
        header = f"{'Experimental Condition':<54} | {'Win %':>7} | {'Surv %':>7} | {'Fix %':>7} | {'NetWorth':>9}"
        print(header)
        print("-" * 105)
        for r in rows:
            print(
                f"{r['mode_name']:<54} | "
                f"{r['llm_win_rate_pct']:>6.1f}% | "
                f"{r['survival_rate_pct']:>6.1f}% | "
                f"{r['fixation_loop_rate_pct']:>6.1f}% | "
                f"{r['avg_net_worth']:>9.1f}"
            )
        print("=" * 105)
        print("Saved results to data/benchmark_results.csv")


def save_csv(rows: List[Dict[str, Any]], filepath: str):
    """Сохраняет результаты бенчмарка в CSV для вставки в научную статью."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Condition_ID",
                "Experimental_Condition",
                "Episodes_N",
                "Use_Compass",
                "Use_Short_Memory",
                "LLM_Win_Rate_Pct",
                "RL_Win_Rate_Pct",
                "Survival_Rate_Pct",
                "Fixation_Loop_Rate_Pct",
                "Invalid_Action_Rate_Pct",
                "LLM_Avg_Net_Worth",
                "RL_Avg_Net_Worth",
                "Alpha_Win_Pct",
                "Beta_Win_Pct",
                "Omega_Win_Pct",
                "Alpha_Fixation_Pct",
                "Beta_Fixation_Pct",
                "Omega_Fixation_Pct",
            ]
        )
        for r in rows:
            arch = r["archetypes"]
            writer.writerow(
                [
                    r["mode_id"],
                    r["mode_name"],
                    r["episodes"],
                    r["use_compass"],
                    r["use_short_memory"],
                    r["llm_win_rate_pct"],
                    r["rl_win_rate_pct"],
                    r["survival_rate_pct"],
                    r["fixation_loop_rate_pct"],
                    r["invalid_action_rate_pct"],
                    r["avg_net_worth"],
                    r["rl_avg_net_worth"],
                    arch["Alpha-Net"]["win_rate"],
                    arch["Beta-Core"]["win_rate"],
                    arch["Omega-Robot"]["win_rate"],
                    arch["Alpha-Net"]["fixation_rate"],
                    arch["Beta-Core"]["fixation_rate"],
                    arch["Omega-Robot"]["fixation_rate"],
                ]
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run AI Sandbox Memory Ablation & RL Benchmark Suite")
    parser.add_argument("--episodes", type=int, default=20, help="Number of episodes per experimental condition (default: 20)")
    parser.add_argument("--ticks", type=int, default=55, help="Max ticks per episode (default: 55)")
    args = parser.parse_args()

    asyncio.run(run_benchmark_suite(num_episodes=args.episodes, max_ticks=args.ticks))
