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
