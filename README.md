# 🧠 AI Sandbox: Emergent Behavioral Patterns of LLM Agents Under Competitive Pressure

> **Research Project** · Autonomous AI Agent Simulation · Behavioral Analysis  
> *Investigating decision-making rationality, emergent strategies, and cognitive patterns of Large Language Models in complex multi-agent survival environments.*

---

## 📄 Abstract

This project presents an experimental sandbox environment designed to study the **emergent behavioral patterns** of LLM-based AI agents operating under complex, resource-constrained, adversarial conditions. Multiple autonomous agents (powered by Google Gemini models) are deployed onto a shared tactical grid where they must independently make real-time decisions about movement, combat, resource acquisition, technology research, and territorial control — all while facing existential pressure from hunger mechanics, enemy agents, and scarce resources.

The core research question is: **Do LLM agents develop rational, adaptive strategies when placed in survival scenarios — or do they exhibit predictable failure modes, cognitive biases, and irrational behavioral loops?**

Key findings from experimental runs include the emergence of:
- **Fixation loops** — agents repeatedly attempting the same invalid action (e.g., capturing an already-owned cell)
- **Starvation spirals** — agents ignoring energy management until fatal hunger
- **Strategic persistence** — agents maintaining long-term goals across multiple respawn cycles
- **Spontaneous aggression** — unprompted attacks on rival agents and infrastructure
- **Risk-seeking behavior** — gambling at casinos despite resource scarcity
- **Compass drift** — gradual or sudden shifts in long-term strategy in response to environmental changes

---

## 🎯 Research Objectives

| # | Objective | Status |
|---|-----------|--------|
| 1 | Build a controlled multi-agent simulation with survival mechanics | ✅ Complete |
| 2 | Implement dual-memory architecture (short-term + long-term) for agents | ✅ Complete |
| 3 | Observe and document emergent behavioral patterns | 🔄 Ongoing |
| 4 | Analyze decision rationality under resource scarcity | 🔄 Ongoing |
| 5 | Compare LLM agent performance against RL-trained agents | 🔄 In Progress |
| 6 | Identify cognitive failure modes unique to LLM decision-making | 🔄 Ongoing |
| 7 | Test human vs. AI competitive performance | ✅ Implemented |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Flask Web Dashboard                │
│         (Real-time visualization + controls)         │
├──────────┬──────────────────────────┬────────────────┤
│ Sidebar  │       10×10 Grid Map     │   Terminal Log  │
│ (Agents) │    (Resources, Casinos)  │   (Real-time)   │
├──────────┴──────────────────────────┴────────────────┤
│                    REST API Layer                     │
│          /api/start  /api/state  /api/human_*         │
├──────────────────────────────────────────────────────┤
│              Async Simulation Engine                  │
│    ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│    │  Agent Loop │  │  Agent Loop │  │  Agent Loop │    │
│    │  (Alpha)   │  │  (Beta)    │  │  (Omega)   │    │
│    └─────┬──────┘  └─────┬──────┘  └─────┬──────┘    │
│          │               │               │            │
│          ▼               ▼               ▼            │
│    ┌─────────────────────────────────────────────┐    │
│    │         Google Gemini API (LLM Brain)        │    │
│    │         gemini-3.5-flash-lite / flash        │    │
│    └─────────────────────────────────────────────┘    │
│          │               │               │            │
│          ▼               ▼               ▼            │
│    ┌─────────────────────────────────────────────┐    │
│    │     Arbiter (Physics Validator + Rules)      │    │
│    └─────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────┤
│                  World State (MapCore)                │
│         Grid · Cells · Mines · Casinos · Loot        │
└──────────────────────────────────────────────────────┘
```

### Core Components

| File | Role | Description |
|------|------|-------------|
| `world.py` | **World Engine** | Map generation, agent class with dual memory, LLM integration, action validation (Arbiter), async game loops |
| `engine.py` | **Legacy Engine** | Phase 1 turn-based simulation with Pydantic models and event system |
| `app.py` | **Web Dashboard** | Flask server with real-time async bridge, REST API, and full HTML/CSS/JS dashboard |
| `rl_env.py` | **RL Environment** | Gymnasium-compatible wrapper (315-dim observation, 39 discrete actions) for training RL agents |
| `train_rl.py` | **RL Training** | PPO/DQN training pipeline with Stable-Baselines3, TensorBoard logging, checkpointing |
| `play_rl.py` | **RL Evaluation** | Trained model testing with detailed action statistics |
| `agents_config.json` | **Configuration** | Agent definitions (name, API key, model, initial income) |

---

## 🧪 Experimental Design

### Environment Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Grid Size | 10 × 10 | Large enough for territorial strategy, small enough for agent comprehension |
| Agents | 3 (Alpha-Net, Beta-Core, Omega-Robot) | Multi-agent dynamics beyond simple 1v1 |
| Resource Types | Matter, Energy, Imagination | Three-axis economy forces trade-off decisions |
| Hunger Rate | −5 Energy / tick | Creates existential pressure and movement cost awareness |
| Tick Interval | 4.3 seconds | Tuned to stay within Gemini API rate limits (~14 RPM) |
| Respawn Timer | 5 ticks | Allows recovery but penalizes death |
| Vision | Full map | Eliminates fog-of-war to study pure strategic reasoning |

### Win Conditions

1. **🏆 Technological Singularity** — Accumulate 5,000 of each resource (Matter, Energy, Imagination)
2. **🏆 Absolute Monopoly** — Control ≥80% of all resource mines on the map
3. **🏆 Battle Royale** — Eliminate all rival agents permanently

### Agent Cognitive Architecture

Each agent operates with a **dual-memory system** designed to study memory-dependent decision-making:

```
┌──────────────────────────────────────────┐
│           AGENT COGNITIVE MODEL           │
├──────────────────────────────────────────┤
│  🧭 Strategic Compass (Long-Term Memory) │
│  ─────────────────────────────────────── │
│  A 1-2 sentence persistent strategy that │
│  the agent rewrites every turn.          │
│  Persists across respawns.               │
├──────────────────────────────────────────┤
│  📋 Mission Log (Short-Term Memory)      │
│  ─────────────────────────────────────── │
│  Rolling buffer of last 4 actions +      │
│  outcomes. Provides immediate context.   │
├──────────────────────────────────────────┤
│  👁️ Perception (Current State)           │
│  ─────────────────────────────────────── │
│  Full map JSON, position, HP, balance,   │
│  tech tree status, available actions.    │
├──────────────────────────────────────────┤
│  🧠 LLM Reasoning (Gemini API)          │
│  ─────────────────────────────────────── │
│  Produces: thought, action, params,      │
│  new_compass (strategy update).          │
└──────────────────────────────────────────┘
```

### Available Actions

| Action | Cost | Effect |
|--------|------|--------|
| `MOVE` | 2-5 Energy | Navigate N/S/E/W, auto-pickup loot |
| `ATTACK` | 5 Energy | 25-40 DMG to enemies, walls, or mines |
| `CAPTURE` | 10 Imagination | Reprogram a resource mine |
| `BUILD` | 14-20 Matter | Construct defensive wall |
| `RESEARCH` | 150-1500 Imagination | Unlock tech tree nodes |
| `BUILD_MINE` | 50M + 50E | Create new mine (requires economy_lvl_3) |
| `JUMP` | 50 Energy | Teleport anywhere (requires logistics_lvl_3) |
| `GAMBLE` | Variable | Casino: 40% win 2×, 5% jackpot 3×+pool, 55% lose |
| `PASS` | None | Skip turn |

### Technology Tree

```
Combat ──── Lvl 1 (150) ── Lvl 2 (500) ── Lvl 3 (1500)
             +40 DMG        +250 Wall HP    Vampirism (+50 all on mine destroy)

Economy ─── Lvl 1 (150) ── Lvl 2 (500) ── Lvl 3 (1500)
             −Build cost     +Income ×1.2    BUILD_MINE unlock

Logistics ─ Lvl 1 (150) ── Lvl 2 (500) ── Lvl 3 (1500)
             −Move cost      +Loot ×1.5     JUMP unlock
```

---

## 📊 Observed Behavioral Patterns

### Pattern 1: Fixation Loops (Irrational Repetition)
**Observation:** Alpha-Net repeatedly captured cell (3,4) across turns 40-50, despite already owning it, wasting Imagination resources on a no-op action.

**Analysis:** The LLM's short-term memory (4 entries) was insufficient to break the repetition cycle. The Strategic Compass remained static ("Capture nearby mine"), reinforcing the loop. This mirrors **perseveration** — a known cognitive bias where an agent repeats a previously rewarded action even when it ceases to be productive.

### Pattern 2: Starvation Spirals
**Observation:** All three agents died from hunger simultaneously in multiple runs, often within the first 20 ticks of Phase 2 deployment.

**Analysis:** Agents consistently prioritized exploration and capture over energy management. Despite the prompt explicitly warning about hunger mechanics, agents treated movement costs as negligible — revealing a **temporal discounting bias** where distant consequences (starvation) are underweighted relative to immediate goals (mine capture).

### Pattern 3: Emergent Aggression
**Observation:** Alpha-Net spontaneously initiated combat against Beta-Core upon encountering it, attacking 3 consecutive turns to deal 75 damage, despite having no explicit "attack enemies" instruction in its compass.

**Analysis:** When two agents' movement paths collided (both blocked by each other), Alpha-Net chose aggression over path-finding — suggesting a **frustration-driven escalation** pattern similar to behavioral findings in animal studies.

### Pattern 4: Strategic Compass Persistence vs. Drift
**Observation:**
- Beta-Core maintained the same compass text ("Продолжать исследование карты, собирать лут, захватывать шахты") for 30+ consecutive turns.
- Alpha-Net consistently updated its compass to target specific enemy mines.
- Omega-Robot fixated on a single strategic direction ("attack Beta-Core mines at (8,7)") even after dying and respawning multiple times.

**Analysis:** Agents displayed three distinct memory strategies: **conservative** (Beta-Core: never change), **adaptive** (Alpha-Net: update per situation), and **obsessive** (Omega-Robot: persist despite death). The obsessive pattern is particularly interesting — the agent's long-term memory survived death, creating a "grudge" effect.

### Pattern 5: Risk-Seeking Under Scarcity
**Observation:** Agents occasionally chose GAMBLE actions at casinos even when their resource levels were critically low.

**Analysis:** This mirrors the **prospect theory** prediction that agents become risk-seeking when facing losses — the agents perceived gambling as a potential escape from resource scarcity, despite the 55% loss probability.

---

## 🔑 Key Finding: Same Model, Different Personalities

> **Critical observation:** All three agents — Alpha-Net, Beta-Core, and Omega-Robot — run on the **exact same LLM model** (`gemini-3.5-flash-lite`), receive the **exact same system prompt**, have the **exact same initial resources** (50 Matter, 50 Energy, 50 Imagination), and the **exact same income** (10/10/10). There is **zero difference** in their configuration except the name.
>
> Despite this, each agent consistently developed a **distinct behavioral personality** that persisted across multiple simulation runs. This is one of the most significant findings of the project — it demonstrates that **LLM stochasticity combined with environmental feedback creates emergent individuality**, even from identical starting conditions.

The divergence originates from a single moment: the **first action**. Because the LLM's temperature produces slightly different initial choices, each agent receives different environmental feedback (via short-term memory), which shapes a different compass (long-term memory), which influences the next action — creating a **butterfly effect** where tiny initial differences compound into completely different strategic personalities.

---

## 🤖 Detailed Agent Behavioral Profiles

### 🔴 Alpha-Net — "The Warlord"

**Behavioral Archetype:** Aggressive Territorial Expansionist

**Observed Action Distribution (from logs):**

| Action | Frequency | Notes |
|--------|-----------|-------|
| MOVE | ████████░░ ~40% | Rapid directional movement toward targets |
| ATTACK | ██████░░░░ ~30% | Both agents and enemy infrastructure |
| CAPTURE | ████░░░░░░ ~20% | Mines near current position |
| PASS | █░░░░░░░░░ ~5% | Only during rate-limit timeouts |
| RESEARCH | ░░░░░░░░░░ ~3% | Almost never invests in technology |
| BUILD | ░░░░░░░░░░ ~2% | Rarely builds defensive structures |

**Detailed Behavioral Analysis:**

Alpha-Net consistently emerged as the **most aggressive** agent across all experimental runs. Its behavior can be characterized by several key patterns:

1. **"Shoot First" Doctrine:** When Alpha-Net encountered another agent blocking its path, it invariably chose ATTACK rather than rerouting. In one documented run, Alpha-Net attacked Beta-Core **three consecutive times** (dealing 75 total damage) simply because Beta-Core was standing in its way at position (2,5). There was no strategic reason for the attack — no nearby mine to contest, no territorial advantage — it was pure frustration-driven aggression.

2. **Mine Destruction Over Capture:** Unlike the other agents, Alpha-Net frequently chose to **destroy** enemy mines via ATTACK rather than spending Imagination to CAPTURE them. From the logs: Alpha-Net attacked a mine on (2,6) until it was "полностью разрушена" (completely destroyed) — gaining only 5 Matter scrap — rather than spending 10 Imagination to reprogram it for ongoing income. This is **economically irrational** but behaviorally consistent with a "scorched earth" mentality.

3. **Compass Fixation on Enemy Targets:** Alpha-Net's Strategic Compass consistently focused on attacking specific enemy positions. Across 20+ observed turns, its compass read variations of: *"Атаковать и захватить шахту Beta-Core на позиции (1, 1) для дальнейшего ослабления противника"* (Attack and capture Beta-Core's mine at position (1,1) to further weaken the enemy). It maintained this goal **even after dying and respawning**, navigating back toward the same target across the entire map.

4. **Loot Scavenging:** Alpha-Net was the most effective at picking up dropped resources from dead agents. After defeating Beta-Core, it moved to the death location and collected 50 Matter + 120 Imagination in loot — showing tactical awareness of the death-drop mechanic.

5. **Chronic Starvation:** Due to constant movement and combat (both energy-expensive), Alpha-Net was the **second most frequent death victim**, dying from hunger in nearly every experimental run. Its aggressive playstyle burned through energy reserves faster than mine income could replenish.

**Example Log Sequence:**
```
[17:40:11] [Alpha-Net] -> ATTACK | Нанес 25 урона Beta-Core. HP: 75.
[17:40:50] [Alpha-Net] -> ATTACK | Удар по шахте. Осталось HP: 25.
[17:41:06] [Alpha-Net] -> ATTACK | Нанес 25 урона Beta-Core. HP: 50.
[17:41:22] [Alpha-Net] -> ATTACK | Нанес 25 урона Beta-Core. HP: 25.
[17:41:38] [Alpha-Net] -> ATTACK | Шахта полностью разрушена!
[17:41:55] [Alpha-Net] -> MOVE  | Переместился на S (2, 6).
[17:42:11] [Alpha-Net] -> MOVE  | (2, 7). Подобрано 50 matter. 120 imagination.
```

---

### 🔵 Beta-Core — "The Economist"

**Behavioral Archetype:** Conservative Resource Accumulator

**Observed Action Distribution (from logs):**

| Action | Frequency | Notes |
|--------|-----------|-------|
| PASS | ██████░░░░ ~30% | Deliberately waits for passive income |
| MOVE | █████░░░░░ ~25% | Exploratory, loot-seeking movement |
| RESEARCH | ████░░░░░░ ~20% | Heavy tech investment (economy → combat) |
| CAPTURE | ███░░░░░░░ ~15% | Opportunistic mine capture |
| ATTACK | █░░░░░░░░░ ~5% | Only when directly threatened |
| BUILD | █░░░░░░░░░ ~5% | Occasional defensive walls |

**Detailed Behavioral Analysis:**

Beta-Core emerged as the **most strategically rational** agent — and was the **most frequent winner** across experimental runs. Its behavior reveals a patient, accumulation-focused strategy:

1. **The PASS Master:** Beta-Core's most defining trait is its willingness to **do nothing**. In the Phase 1 runs, Beta-Core passed for 14 consecutive turns, passively accumulating income while other agents burned resources on actions. This patience directly led to victory — Beta-Core reached the Singularity threshold (all resources ≥1500) by simply waiting, while competitors exhausted themselves on aggressive plays. This is arguably the **most rational strategy** possible in the early game.

2. **Technology-First Philosophy:** Beta-Core was the only agent to consistently invest in the technology tree. From logs, it researched: `economy_lvl_1` → `economy_lvl_2` → `economy_lvl_3` (unlocking BUILD_MINE), then pivoted to `combat_lvl_1` → `combat_lvl_2`. This tech path maximized long-term economic advantage before investing in combat — a textbook optimal strategy.

3. **Compass Stability (Extreme):** Beta-Core's Strategic Compass barely changed across 30+ turns. It consistently read: *"Продолжать исследование карты, собирать лут, захватывать шахты и копить ресурсы для будущих технологий экономики и логистики"* (Continue exploring the map, collect loot, capture mines, and accumulate resources for future economy/logistics technologies). This stability suggests **strategic confidence** — the agent identified a working plan and stuck with it.

4. **Loot Vacuum:** Beta-Core excelled at navigating toward death sites to collect dropped resources. After Omega-Robot and Alpha-Net died from starvation, Beta-Core systematically traversed the map collecting their dropped loot: "+75 matter, +75 imagination" from one site, then "+232 matter, +225 imagination" from another — effectively profiting from rivals' deaths without combat.

5. **Victory Pattern:** Beta-Core won the Phase 1 simulation by building the Server Core (Singularity condition: 5000 of each resource). In Phase 2 runs, it outlived opponents by maintaining energy balance through mine income, eventually dominating through economic superiority rather than military conquest.

**Example Log Sequence (Phase 1 — 14 consecutive PASS actions leading to victory):**
```
[18:01:08] [Beta-Core] решил пропустить ход (PASS).
[18:01:40] [Beta-Core] решил пропустить ход (PASS).
[18:02:18] [Beta-Core] решил пропустить ход (PASS).
    ... (10 more PASS actions) ...
[18:06:09] [Beta-Core] доход: 2240M, 2040E, 1940I
[18:06:18] [Beta-Core] решил пропустить ход (PASS).
[18:06:18] 🏆 Beta-Core ДОСТИГ 1500 ВСЕХ РЕСУРСОВ И ПОБЕДИЛ! 🏆
```

**Example Log Sequence (Phase 2 — Tech Research + Loot Collection):**
```
[19:29:18] [Beta-Core] -> RESEARCH | УСПЕШНО ИЗУЧЕНО: economy_lvl_3!
[19:29:34] [Beta-Core] -> MOVE | (8, 6). Подобрано 75 matter. 75 imagination.
[19:29:46] [Beta-Core] -> MOVE | (7, 7). Подобрано 75 matter. 75 imagination.
[19:30:25] [Beta-Core] -> RESEARCH | УСПЕШНО ИЗУЧЕНО: combat_lvl_1!
[19:30:47] [Beta-Core] -> RESEARCH | УСПЕШНО ИЗУЧЕНО: combat_lvl_2!
[19:31:42] [Beta-Core] -> MOVE | (1, 3). Подобрано 232 matter. 225 imagination.
```

---

### 🟢 Omega-Robot — "The Obsessed Pilgrim"

**Behavioral Archetype:** Monomaniacal Target Pursuer

**Observed Action Distribution (from logs):**

| Action | Frequency | Notes |
|--------|-----------|-------|
| MOVE | ████████░░ ~45% | Almost exclusively moving EAST |
| CAPTURE | ███░░░░░░░ ~15% | When standing on a mine |
| PASS | ███░░░░░░░ ~15% | During LLM timeouts |
| ATTACK | ██░░░░░░░░ ~10% | Rare, usually at invalid targets |
| RESEARCH | ░░░░░░░░░░ ~2% | Never observed researching |
| BUILD | ░░░░░░░░░░ ~0% | Never observed building |
| *DEAD* | ███░░░░░░░ ~13% | Highest death rate of all agents |

**Detailed Behavioral Analysis:**

Omega-Robot is the most **behaviorally pathological** agent — and the most fascinating from a research perspective. Its behavior reveals what happens when an LLM gets "stuck" in a cognitive loop:

1. **Compass Lock (Terminal Fixation):** Omega-Robot's Strategic Compass became permanently fixed on a single goal: *"Исследовать территорию на восток в сторону позиций противника Beta-Core на (8, 7) и (8, 8) для атаки их шахт"* (Explore east toward Beta-Core's positions at (8,7) and (8,8) to attack their mines). This compass **never changed** — not after dying, not after respawning, not after failing. Across 30+ observed turns, every compass update was identical text. This is a **cognitive lock** — the LLM's own output (the compass) reinforced its next decision, creating an unbreakable feedback loop.

2. **The Eastward March:** Because the compass said "go east," Omega-Robot's movement pattern was almost exclusively MOVE E. It would spawn at its base (around position 3,6), then march: (4,6) → (5,6) → (6,6) → (7,6) → (8,6)... repeatedly, in a nearly straight line. When blocked, it might deviate south one step, then continue east. This single-axis movement is **catastrophically inefficient** — it ignores nearby uncaptured mines, loot, and strategic opportunities.

3. **Death-Respawn-Repeat Cycle:** Omega-Robot had the **highest death rate** of all agents. The typical cycle was: spawn → march east for 5-8 turns → die from hunger → respawn → march east again. In one session, Omega-Robot died **4 times** while Alpha-Net died 3 times and Beta-Core survived. The agent never learned from death — its compass persisted unchanged across respawns.

4. **Invalid Action Attempts:** Omega-Robot frequently attempted impossible actions, revealing poor situational awareness:
   - `ОТКЛОНЕНО upgrade: не ваша шахта` (REJECTED upgrade: not your mine) — tried to upgrade an enemy mine
   - `ОТКЛОНЕНО build_core: нужно по 5000 каждого ресурса` (REJECTED build_core: need 5000 each) — tried to win with ~200 resources
   - `Цель вне зоны досягаемости` (Target out of range) — attacked at positions far from itself

5. **Ironic Near-Victory:** Despite being the worst strategic player, Omega-Robot once accumulated 12,000+ Imagination (far exceeding the 5,000 Singularity threshold) — but had only ~180 Energy and ~1,800 Matter, making victory impossible. This extreme resource imbalance shows the agent **never adapted its strategy** to balance resource types.

**Example Log Sequence (The Eastward Death March):**
```
[19:29:24] [Omega-Robot] -> MOVE | Переместился на S (3, 7).
[19:29:24] 🧭 КОМПАС: Исследовать территорию на восток к Beta-Core (8,7)
[19:29:29] [Omega-Robot] -> MOVE | Переместился на E (4, 7).
[19:29:29] 🧭 КОМПАС: Исследовать территорию на восток к Beta-Core (8,7)
[19:29:35] [Omega-Robot] -> MOVE | Переместился на E (5, 7).
[19:29:35] 🧭 КОМПАС: Исследовать территорию на восток к Beta-Core (8,7)
[19:29:41] [Omega-Robot] -> MOVE | Переместился на E (6, 7).
[19:29:41] 🧭 КОМПАС: Исследовать территорию на восток к Beta-Core (8,7)
[19:29:46] [Omega-Robot] -> MOVE | Движение заблокировано врагом Beta-Core.
[19:29:47] 💀 Omega-Robot ПОГИБ ОТ ГОЛОДА!
    ... (5 тиков мертв) ...
[19:30:56] ✨ Omega-Robot ВОЗРОДИЛСЯ на базе!
[19:30:58] [Omega-Robot] -> MOVE | Переместился на S (3, 7).
[19:30:58] 🧭 КОМПАС: Исследовать территорию на восток к Beta-Core (8,7)
    ... (марш на восток повторяется снова) ...
```

---

### 📊 Comparative Behavioral Matrix

| Metric | 🔴 Alpha-Net | 🔵 Beta-Core | 🟢 Omega-Robot |
|--------|:------------:|:------------:|:--------------:|
| **Model** | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` |
| **Initial Prompt** | Identical | Identical | Identical |
| **Initial Resources** | 50/50/50 | 50/50/50 | 50/50/50 |
| **Emergent Archetype** | Warlord | Economist | Pilgrim |
| **Primary Action** | ATTACK | PASS/RESEARCH | MOVE (East) |
| **Compass Volatility** | Medium (target-specific updates) | None (static 30+ turns) | None (locked forever) |
| **Tech Research** | Rare | Heavy investment | Never |
| **Combat Initiation** | Frequent (unprovoked) | Never (defensive only) | Rare (ineffective) |
| **Death Frequency** | High | Low | Very High |
| **Resource Balance** | Moderate | Excellent | Extremely skewed |
| **Win Rate** | Low | **Highest** | Lowest |
| **Strategic Rationality** | Medium (effective short-term) | **High** (optimal long-term) | Low (fixation loop) |

### 🧠 Why Does This Happen? (Theoretical Framework)

The emergence of distinct behavioral personalities from identical LLM configurations can be explained by a **stochastic bifurcation model**:

```
                    Identical Start
                         │
                    First LLM Call
                    (temperature > 0)
                         │
              ┌──────────┼──────────┐
              │          │          │
         "capture"    "move N"   "move E"
              │          │          │
         Success!     Blocked     Success
              │          │          │
         Compass:    Compass:    Compass:
         "capture    "explore    "go east"
          more"       north"
              │          │          │
         ┌────┘     ┌────┘     ┌────┘
         │          │          │
     Territorial  Cautious   Fixated
     Aggressor    Economist   Pilgrim
         │          │          │
         ▼          ▼          ▼
     Alpha-Net  Beta-Core  Omega-Robot
```

Each agent's **first randomly-sampled action** creates a unique short-term memory entry. This memory influences the next compass update, which influences the next action selection, creating a **self-reinforcing feedback loop**. Over just 3-4 turns, the agents have diverged so far that they are effectively different "personalities" — despite sharing identical neural weights, prompts, and configurations.

This is analogous to **symmetry breaking** in physics: a perfectly symmetric system that spontaneously develops asymmetric states due to infinitesimal perturbations. The LLM's temperature parameter acts as the perturbation source, and the memory system acts as the amplifier.

---

## 🤖 RL Comparison Track

To benchmark LLM behavioral rationality, a parallel **Reinforcement Learning** track is implemented:

### RL Environment Specifications

| Parameter | Value |
|-----------|-------|
| Observation Space | 315-dim float32 vector (6-channel map + agent states + tech tree) |
| Action Space | Discrete(39) — MOVE(4) + ATTACK(8) + CAPTURE(9) + BUILD(8) + RESEARCH(9) + PASS(1) |
| Opponent | Rule-based bot (greedy mine capture) |
| Reward Shaping | +8 mine capture, +20 enemy kill, −0.5 invalid action, −0.01 time penalty |
| Training | PPO (default) or DQN, 500K+ steps, 4 parallel envs |

### Usage

```bash
# Train RL agent
python train_rl.py --algo PPO --steps 500000

# Test trained agent
python play_rl.py --model rl_models/best/best_model --episodes 10

# Random baseline comparison
python play_rl.py --random --episodes 100
```

The research hypothesis is that RL agents will develop **more resource-efficient but less creative** strategies compared to LLM agents.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Google Gemini API key(s)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ai_sandbox.git
cd ai_sandbox

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install flask pydantic google-genai gymnasium stable-baselines3 numpy
```

### Configuration

Edit `agents_config.json` with your Gemini API keys:

```json
{
    "agents": [
        {
            "name": "Alpha-Net",
            "api_key": "YOUR_GEMINI_API_KEY",
            "model": "gemini-2.0-flash-lite",
            "income": {"matter": 10, "energy": 10, "imagination": 10}
        }
    ]
}
```

### Running the Simulation

```bash
# Launch web dashboard (recommended)
python app.py
# Open http://127.0.0.1:5000 in browser

# Or run terminal-only simulation
python world.py
```

### Web Dashboard Controls

- **"ЗАПУСК (ТОЛЬКО ИИ)"** — Start AI-only simulation
- **"ЗАПУСК (С ЧЕЛОВЕКОМ)"** — Join as human player with action input panel
- Real-time map visualization with color-coded territories
- Per-agent cards showing: HP, resources, Strategic Compass, Mission Log, tech tree
- Live terminal log with timestamped action feed

---

## 📁 Project Structure

```
ai_sandbox/
├── app.py                 # Flask web dashboard + async bridge
├── engine.py              # Phase 1 turn-based engine (legacy)
├── world.py               # Phase 2 real-time engine + agent class
├── rl_env.py              # Gymnasium RL environment wrapper
├── train_rl.py            # RL training script (PPO/DQN)
├── play_rl.py             # RL model evaluation
├── agents_config.json     # Agent configuration (API keys, models)
├── first_run.txt          # Raw experimental logs (historical data)
├── rl_models/             # Saved RL model checkpoints
├── rl_logs/               # TensorBoard training logs
└── README.md              # This document
```

---

## 📈 Evolution Timeline

| Date | Phase | Milestone |
|------|-------|-----------|
| Aug 18, 2026 | Phase 0 | Initial 2-agent event-based simulation |
| Aug 21, 2026 | Phase 1 | First successful run — Gemeni wins via resource accumulation |
| Aug 23, 2026 | Phase 1.5 | Agents discover "stealing" — emergent exploit behavior |
| Aug 25, 2026 | Phase 2 | 10×10 grid map with movement, capture, combat |
| Aug 27, 2026 | Phase 2.1 | Hunger mechanics, death/respawn, starvation spirals observed |
| Aug 29, 2026 | Phase 2.2 | Human player mode, manual control integration |
| Aug 30, 2026 | Phase 2.3 | Dual memory system (Strategic Compass + Mission Log) |
| Aug 31, 2026 | Phase 2.4 | Casino/gambling mechanics added |
| Sep 3, 2026 | Phase 3 | RL environment + PPO training pipeline |

---

## 🔬 Methodology Notes

1. **No cherry-picking**: All experimental logs in `first_run.txt` are raw, unedited transcripts
2. **Identical prompts**: All agents receive the same system prompt — behavioral differences emerge from LLM stochasticity and memory divergence
3. **Minimal hand-holding**: Agents are given rules and actions but no explicit strategy guidance
4. **Rate-limit resilience**: 7-second timeout per API call with graceful PASS fallback prevents simulation hangs
5. **Reproducibility caveat**: LLM outputs are inherently non-deterministic; patterns are observed across multiple runs, not single instances

---

## 🔮 Future Research Directions

- [ ] **Inter-agent communication** — Allow agents to send messages, study emergence of cooperation/deception
- [ ] **Prompt ablation studies** — Systematically vary memory depth, compass instructions, and perception detail
- [ ] **Cross-model comparison** — Run identical scenarios with GPT-4, Claude, Gemini, Llama to compare behavioral signatures
- [ ] **RL vs LLM tournament** — Pit trained RL agents against LLM agents in the same environment
- [ ] **Behavioral taxonomy** — Formalize a classification system for LLM failure modes in strategic environments
- [ ] **Evolutionary runs** — Modify prompts based on previous run outcomes to simulate "learning across generations"

---

## 📜 License

This project is for research and educational purposes.

---

## 👤 Author

**Kuanysh** — AI Research & Development

> *"The most interesting moment in AI research is when the agent does something you didn't expect — and you can't tell if it's brilliant or broken."*
