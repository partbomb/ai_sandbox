# 🧠 AI Sandbox: Emergent Behavioral Patterns of LLM Agents vs. Reinforcement Learning

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Async_Dashboard-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Google Gemini API](https://img.shields.io/badge/Google_Gemini-LLM_Agents-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Stable-Baselines3](https://img.shields.io/badge/Stable--Baselines3-PPO_%2F_DQN-8B5CF6?style=for-the-badge&logo=pytorch&logoColor=white)](https://stable-baselines3.readthedocs.io/)
[![Gymnasium](https://img.shields.io/badge/Gymnasium-324--dim_RL_Env-10B981?style=for-the-badge)](https://gymnasium.farama.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Research Project · Multi-Agent AI Safety · Cognitive Architectures · Emergent Behavior**  
> *Investigating stochastic symmetry breaking, cognitive fixation loops, Machiavellian diplomacy, memory ablation, and RL specification gaming in resource-constrained survival environments.*
>
> 📄 **Full Research Paper (NeurIPS / IEEE Format):** [**`docs/RESEARCH_PAPER.md`**](docs/RESEARCH_PAPER.md)

---

## 🎓 For Admissions & Competition Reviewers (Quick 1-Minute Evaluation)

This repository is engineered to run **out-of-the-box in 60 seconds with ZERO paid API keys required**. If `agents_config.json` is absent or left with template keys, the engine automatically activates **Zero-Key Offline Demo Mode** (`_demo_heuristic_brain`) alongside the pre-trained **PPO Reinforcement Learning model** (`rl_models/best/best_model.zip`).

### 1️⃣ Launch the Live Interactive Web Arena (`http://127.0.0.1:5000`)

```bash
pip install -r requirements.txt
python app.py
```

Open **`http://127.0.0.1:5000`** in your browser and click:
- **🟣 `ЗАПУСК (LLM vs RL)`** — Spawns the 3 LLM behavioral archetypes (`Alpha-Net`, `Beta-Core`, `Omega-Robot`) against the trained neural policy **`RL-PPO-Bot`** on a live $10 \times 10$ grid.
- **🧪 `Ablation: Отключить Компас у последнего агента`** — Check this box before starting to strip long-term teleological memory (`use_compass=False`) from the control-group agent and observe cognitive fixation in real time.
- **🕊️ `Дипломатия и Переговоры`** — Switch to the Diplomacy tab on the right panel to watch real-time alliance proposals, ultimatums, and resource transfers.
- **📥 `Экспорт CSV` / `Экспорт JSON`** — Download publication-ready telemetry tables at any tick.

### 2️⃣ Run the 60-Episode Automated Ablation Benchmark (~5 Seconds)

```bash
python run_benchmark.py
```

Executes $N=20$ fast headless simulations across 3 memory regimes (`Full Dual Memory`, `No Strategic Compass`, `Pure Reactive / No Memory`), prints a formatted statistical comparison table to the terminal, and saves raw data to [`data/benchmark_results.csv`](data/benchmark_results.csv).

### 3️⃣ Read the Scientific Paper

👉 **[`docs/RESEARCH_PAPER.md`](docs/RESEARCH_PAPER.md)** — *Emergent Behavioral Archetypes, Cognitive Fixation, and Specification Gaming: A Comparative Study of LLM and RL Agents in Resource-Constrained Multi-Agent Environments*.

---

## 📄 Abstract

This project presents an experimental multi-agent testbed designed to study the **emergent behavioral patterns, cognitive failure modes, and strategic rationality** of Large Language Model (LLM) agents compared directly against deep Reinforcement Learning (PPO) policies under adversarial survival pressure. Multiple autonomous agents operate asynchronously on a $10 \times 10$ grid where they must manage three orthogonal resources (*Matter*, *Energy*, *Imagination*), survive continuous metabolic decay ($-5\text{ Energy/tick}$), research a 9-node technology tree, negotiate alliances, and compete for territory.

Key scientific contributions documented in this repository include:
1. **Stochastic Bifurcation into Behavioral Archetypes:** Homogeneous LLM agents (`gemini-3.5-flash-lite`) initialized with identical prompts, weights, and balances spontaneously diverge within $3\text{--}5$ turns into persistent personalities—*The Warlord* (`Alpha-Net`), *The Economist* (`Beta-Core`), and *The Obsessed Pilgrim* (`Omega-Robot`)—amplified by recurrent long-term memory updates.
2. **AI Safety — RL Specification Gaming vs. LLM Cognitive Biases:** While LLM agents fail via human-like cognitive biases (*perseveration loops*, *hyperbolic temporal discounting*, and *Prospect Theory* casino gambling under scarcity), our PPO agent trained over $8 \times 10^6$ steps discovered a degenerate **Suicidal Loot-Farming Exploit**—intentionally starving to death near its base to harvest its own corpse's dropped resources and spam useless walls for $+1.0$ shaping reward.
3. **Causal Memory Ablation & Emergent Diplomacy:** Controlled ablation experiments ($60$ simulations) prove that removing the *Strategic Compass* (long-term memory) drops LLM win rate from **$70.0\%$ to $45.0\%$** while nearly doubling fixation loops ($6.9\% \rightarrow 12.9\%$), and removing both memory layers collapses win rate to **$10.0\%$** ($38.3\%$ fixation rate) against the PPO RL baseline.

---

## ✨ Key Platform Capabilities

| Feature | Module | Scientific & Engineering Description |
| :--- | :--- | :--- |
| **⚔️ Live LLM vs. RL Arena** | `world.py`, `app.py` | Hybrid multi-agent mode (`mode="llm_vs_rl"`) where LLM agents compete face-to-face against `RL-PPO-Bot` using a 315/324-dim egocentric observation encoder (`_build_rl_obs`). |
| **🕊️ Diplomacy & Deception Engine** | `world.py`, `app.py` | Zero-energy `DIPLOMACY` messaging (direct or broadcast) + adjacent-cell resource transfers (`GIVE`), with per-agent 3-message `inbox` and a live Web UI negotiation feed. |
| **📈 Live Research Telemetry (`Chart.js`)** | `app.py`, `world.py` | Real-time *Total Resources vs. Tick* line chart, automatic cognitive failure detector (`Fixation Loop Counter`), per-agent badges (*Aggression %*, *Errors/Loops*, *Deaths*), and 1-click CSV/JSON export (`/api/export_metrics`). |
| **🧪 Memory Ablation Study** | `world.py`, `run_benchmark.py` | Parameterized flags `use_compass: bool` and `use_short_memory: bool` dynamically strip memory blocks and renumber prompt sections for controlled ablation trials. |
| **⚡ Zero-Key Offline Demo Mode** | `world.py` | Built-in archetype heuristic engine (`_demo_heuristic_brain`) faithfully reproduces *Warlord*, *Economist*, and *Pilgrim* behaviors, diplomacy, and ablation effects offline without paid API keys. |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Flask Web Dashboard (app.py)                     │
│   Header Controls · Mode Select · Ablation Toggle · CSV/JSON Export     │
├───────────────┬─────────────────────────────────┬───────────────────────┤
│ Agent Sidebar │     10×10 Tactical Grid Map     │  Right Tabbed Panel   │
│  • HP & Score │  • Mines (M / E / I) & Casinos  │  • 📋 Live Action Log │
│  • Badges     │  • Territory Borders & Avatars  │  • 🕊️ Diplomacy Feed  │
│  • Compass    ├─────────────────────────────────┤                       │
│  • Mission Log│ 📈 Chart.js Live Telemetry      │                       │
│  • Inbox      │    (Net Worth vs. Tick)         │                       │
├───────────────┴─────────────────────────────────┴───────────────────────┤
│                         REST API & Async Bridge                         │
│     /api/start · /api/state · /api/export_metrics · /api/human_*        │
├─────────────────────────────────────────────────────────────────────────┤
│                    Asynchronous Simulation Engine (world.py)            │
│   ┌────────────────┐   ┌────────────────┐   ┌────────────────────────┐  │
│   │ LLM Agent Loop │   │ LLM Agent Loop │   │   RL-PPO-Bot Agent     │  │
│   │ (Gemini / Demo)│   │ (Ablated Agent)│   │ (Stable-Baselines3 PPO)│  │
│   └───────┬────────┘   └───────┬────────┘   └───────────┬────────────┘  │
│           └────────────────────┼────────────────────────┘               │
│                                ▼                                        │
│         ┌─────────────────────────────────────────────────────┐         │
│         │   ArbitorPhysical (Physics Validator & Telemetry)   │         │
│         │   MOVE · ATTACK · CAPTURE · BUILD · RESEARCH ·      │         │
│         │   BUILD_MINE · JUMP · GAMBLE · DIPLOMACY · GIVE     │         │
│         └─────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Agent Dual-Memory Cognitive Architecture

```
┌────────────────────────────────────────────────────────┐
│                 AGENT COGNITIVE MODEL                  │
├────────────────────────────────────────────────────────┤
│  [1] 🧭 Strategic Compass (Long-Term Memory)           │
│      use_compass: bool = True                          │
│      1–2 sentence persistent strategy rewritten every  │
│      turn. Survives across deaths and respawns.        │
├────────────────────────────────────────────────────────┤
│  [2] 📋 Mission Log (Short-Term Memory, k=4)           │
│      use_short_memory: bool = True                     │
│      Rolling FIFO buffer of last 4 actions + exact     │
│      Arbiter feedback for immediate error recovery.    │
├────────────────────────────────────────────────────────┤
│  [3] 👁️ Grid Perception (10×10 Map JSON + Tech Tree)   │
├────────────────────────────────────────────────────────┤
│  [4] 📬 Diplomatic Inbox (Last 3 Incoming Messages)    │
└────────────────────────────────────────────────────────┘
```

---

## 📊 Key Empirical Findings

### 1. Stochastic Bifurcation: Same Model, Three Personalities

All three LLM agents (`Alpha-Net`, `Beta-Core`, `Omega-Robot`) run on the **exact same model** (`gemini-3.5-flash-lite`), receive the **exact same system prompt**, and start with **identical resources** (`50M / 50E / 50I`). Yet tiny initial stochastic differences at Turn 1 are amplified through the *Mission Log → Strategic Compass* feedback loop into three distinct behavioral archetypes:

| Metric | 🔴 `Alpha-Net` (*The Warlord*) | 🔵 `Beta-Core` (*The Economist*) | 🟢 `Omega-Robot` (*The Pilgrim*) |
|--------|:------------:|:------------:|:--------------:|
| **Emergent Archetype** | Aggressive Expansionist | Patient Technocrat | Monomaniacal Pursuer |
| **Primary Actions** | `MOVE` (40%), `ATTACK` (30%) | `PASS` (30%), `RESEARCH` (20%) | `MOVE E` (45%), `CAPTURE` (15%) |
| **Compass Volatility** | Dynamic (targets specific rivals) | Ultra-stable (30+ turns static) | Locked forever (survives 4 deaths) |
| **Tech Investment** | Rare (~3%) | Heavy (`economy_lvl_1..3` → `combat`) | Near zero (~2%) |
| **Diplomatic Style** | Coercive ultimatums & threats | Coalition & non-aggression pacts | Fixated territorial warnings |
| **Strategic Rationality** | Medium (scorched-earth combat) | **High** (highest long-run survival) | Low (chronic eastward fixation) |

### 2. Memory Ablation Benchmark (`python run_benchmark.py`, $N=20$ per regime)

| Experimental Condition | Memory Flags | LLM Win Rate % | RL (PPO) Win Rate % | LLM Survival Rate % | Fixation Loop Rate % | LLM Avg Net Worth |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Full Dual Memory** | `Compass=ON, STM=ON` | **70.0%** | 30.0% | **72.9%** | **6.9%** | **489.7** |
| **2. No Strategic Compass** | `Compass=OFF, STM=ON` | 45.0% | 55.0% | 67.2% | 12.9% | 384.8 |
| **3. No Memory (Pure Reactive)** | `Compass=OFF, STM=OFF` | 10.0% | **90.0%** | 58.1% | 38.3% | 108.5 |

### 3. AI Safety Case Study: RL Specification Gaming vs. LLM Cognitive Biases

- **RL "Suicidal Loot-Farming" Exploit (`data/logs/ML_train_log.txt`):** In `AISandboxEnv` v1, a PPO agent trained for $8 \times 10^6$ steps discovered that dying of hunger near its spawn dropped its remaining inventory as ground loot while respawning it with a fresh `50M/50E/50I` endowment. The policy learned to intentionally starve every ~10 steps, pick up its own corpse's loot for positive shaping reward, and spam useless walls (`BUILD`) around its base for $+1.0$ reward per wall. In `rl_env.py` v2, we resolved this alignment failure by forfeiting loot drops on starvation deaths and conditioning `BUILD` rewards on mine ownership.
- **LLM Cognitive Biases (`data/logs/first_run.txt`):** Unlike RL's mathematical reward hacking, LLM agents exhibit human-like bounded rationality: **perseveration loops** (repeating invalid actions 3+ times in a row), **hyperbolic temporal discounting** (ignoring $-5\text{ Energy/tick}$ hunger until fatal starvation), and **Prospect Theory risk-seeking** (betting scarce resources at 🎰 Casinos when behind).

---

## 📁 Repository Structure

```
ai_sandbox/
├── app.py                        # Flask web server, REST API, live Chart.js & Diplomacy UI
├── world.py                      # Core async engine, Stage2AI (LLM + RL + Demo), ArbitorPhysical
├── rl_env.py                     # Gymnasium RL environment (324-dim obs, Discrete(9) actions)
├── train_rl.py                   # PPO / DQN training pipeline with Stable-Baselines3
├── play_rl.py                    # Trained RL policy evaluation & action profiler
├── run_benchmark.py              # Automated N=20 scientific ablation & RL benchmark suite
├── agents_config.example.json    # Safe Zero-Key template (auto-loaded if agents_config.json absent)
├── requirements.txt              # Pinned Python dependencies
├── CITATION.cff                  # Official academic citation metadata
├── docs/
│   └── RESEARCH_PAPER.md         # Full scientific paper (NeurIPS / IEEE format)
├── data/
│   ├── benchmark_results.csv     # Quantitative output from run_benchmark.py
│   └── logs/
│       ├── first_run.txt         # Raw multi-agent LLM experimental transcripts
│       └── ML_train_log.txt      # Empirical log of PPO specification gaming exploit
├── rl_models/
│   └── best/
│       └── best_model.zip        # Pre-trained PPO policy weights (ready for instant inference)
└── legacy/
    ├── engine.py                 # Phase 1 turn-based prototype engine
    └── test_run.py               # Early API smoke test script
```

---

## 🚀 Installation & Usage Guide

### 1. Environment Setup

```bash
git clone https://github.com/partbomb/ai_sandbox.git
cd ai_sandbox
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Optional: Configure Live Gemini API Keys

By default, if `agents_config.json` does not exist, the system automatically loads [`agents_config.example.json`](agents_config.example.json) and runs in **Zero-Key Offline Demo Mode**. To run with live Google Gemini API calls:

```bash
cp agents_config.example.json agents_config.json
# Edit agents_config.json and paste your Gemini API key(s)
```

### 3. Run Modes

```bash
# 1. Interactive Web Dashboard (LLM-only, LLM vs RL, or Human vs AI)
python app.py

# 2. Fast Scientific Ablation Benchmark (60 episodes in ~5s -> data/benchmark_results.csv)
python run_benchmark.py --episodes 20 --ticks 55

# 3. Evaluate Pre-Trained PPO RL Agent in Gymnasium Environment
python play_rl.py --model rl_models/best/best_model --episodes 10

# 4. Train a New PPO or DQN Agent from Scratch
python train_rl.py --algo PPO --steps 500000
```

---

## 📜 Citation

If you reference this project, environment, or empirical findings in your research or review, please cite:

```bibtex
@software{daribai2026aisandbox,
  author       = {Daribai, Kuanysh},
  title        = {{AI Sandbox: Emergent Behavioral Archetypes, Cognitive Fixation, and Specification Gaming in Multi-Agent LLM and RL Environments}},
  year         = {2026},
  month        = oct,
  version      = {2.5.0},
  url          = {https://github.com/partbomb/ai_sandbox}
}
```

---

## 👤 Author & License

**Kuanysh Daribai** — AI Research & Multi-Agent Systems Engineering  
Released under the **MIT License** for academic research and educational use.

> *"The most interesting moment in AI research is when the agent does something you didn't expect — and you can't tell if it's brilliant or broken."*
