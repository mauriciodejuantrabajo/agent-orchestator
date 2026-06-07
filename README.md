> **Idioma / Language:** **English** · [Español](README.es.md)

# 🧭 Agent Orchestrator

A **supervisor** receives your request, **breaks it down into a plan** (a graph of
sub-tasks) and **delegates** each one to the corresponding specialized agent —web
research, calculation, SQL data or writing—, running **in parallel** what it can
and respecting the dependencies between steps.

It's not a fixed pipeline: the orchestrator **decides at runtime** who to route
to, gathers the results and produces a unified answer. It uses **native
tool-calling** from the **DeepSeek** API.

It has a **modern web interface** (React + shadcn/ui + Tailwind over a FastAPI
backend, with **live** routing via Server-Sent Events) and also a **CLI**.

```
?  Which region sold the most units and how much did it bill in total?

  🧭 Orchestrator plan: s1:data → s2:writer

  🗄️ data [s1] → find the region with the most units and total billing
     tools: run_sql(query='SELECT r.name, SUM(s.units) ...')
  ✍️ writer [s2] → write the final answer
     tools: (no tools)

  Answer
  The **Centro** region sold the most units (241), followed by
  Norte (208) and Sur (197). …
```

## The problem

A single agent with many tools (search, calculate, query the database, write)
gets confused: it picks the wrong tool, mixes responsibilities and is hard to
maintain. And solving everything "in one shot" prevents taking advantage of the
fact that some sub-tasks are **independent** and could run at the same time.

## The solution

Separate **decision** from **execution**, like a team with a leader:

1. **The supervisor plans.** It breaks the request into a **DAG** of sub-tasks:
   each one says *which* agent solves it and *which* others it depends on.
2. **The orchestrator executes the DAG.** It runs in **parallel** the steps with
   no dependencies between them, waits for those that depend on others and passes
   their results as context.
3. **A writer unifies.** The `writer` synthesizes the outputs into the final
   answer, preserving the `[N]` citations from the research.

Each agent has **a single responsibility**, its own prompt and a small set of
tools: it thinks only about its task and chooses well.

### The agents

| Agent | Role | Tools |
|-------|------|-------|
| 🔎 **research** | Searches and reads pages; answers with facts and `[N]` citations | `web_search`, `read_url` |
| 🧮 **math** | Computes **exactly** (doesn't "hallucinate" arithmetic) | `calc` (safe arithmetic parser) |
| 🗄️ **data** | Answers by querying a sample database | `run_sql` (**read-only**) |
| ✍️ **writer** | Synthesizes the results into the final answer | — |

> **Secure on purpose.** The calculator **runs no code**: it evaluates only
> arithmetic expressions (`+ - * / // % **` and parentheses) with an AST parser,
> rejecting variables, functions or imports. Data access is **read-only SQL**:
> `INSERT/UPDATE/DELETE/DROP/…` are blocked and the connection is opened in
> `read-only` mode, so not even a slip could modify the database.

## What makes it a "real" orchestrator

- 🗺️ **DAG planning**, not `if/else`: the supervisor builds the graph of sub-tasks
  with their dependencies.
- ⚡ **Real parallelism**: independent steps run at the same time (LLM calls are
  I/O, so it lowers the total time).
- 🔁 **Re-planning on failure**: if a step fails, it's retried; if the whole plan
  is invalid, there's a *fallback* to answer anyway.
- 💰 **Budget**: a global step cap to avoid expensive loops (cost is the #1 concern
  in production).

## Architecture

```
server.py             HTTP backend (FastAPI): exposes the orchestrator and
                      streams it LIVE via SSE (/api/stream).
app.py                Alternative web interface (Streamlit), no npm.
web/                  React + Vite + shadcn/ui + Tailwind frontend.
├── src/App.tsx        Main UI: input, plan, per-agent cards, answer.
├── src/components/    StepCard + shadcn/ui components.
└── src/lib/           SSE client (orchestrator.ts) and agent metadata.
src/
├── llm.py            DeepSeek client (OpenAI-compatible): tool-calling.
├── tools.py          web_search, read_url, calc (safe AST), run_sql (read-only).
├── agents.py         The 4 agents: research, math, data, writer.
├── planner.py        The supervisor: breaks the request into a DAG (with validation).
├── orchestrator.py   Executes the DAG: dependencies, parallelism, budget, re-plan.
└── main.py           CLI (rich) with a live trace of the routing.
scripts/seed_db.py    Generates data/demo.db (sample sales database).
tests/                Tests with mocks (no real network, no API calls).
```

The frontend (React) talks to the backend (FastAPI), which wraps the orchestrator
(Python). The routing progress travels from the orchestrator to the browser in
real time via **Server-Sent Events**:

```
  browser (React/shadcn) ──HTTP──► FastAPI (server.py) ──► Orchestrator (src/)
        ▲                                                          │
        └──────────────── SSE: plan, steps, answer ◄──────────────┘
```

The **flow** coordinated by `orchestrator.py`:

```
            request
               │
               ▼
        🧭 Planner ── breaks down ──► DAG of sub-tasks
               │
        ┌──────┼───────────────┐   (parallel where there's no dependency)
        ▼      ▼               ▼
   🔎 research 🧮 math      🗄️ data
        └──────┴───────┬───────┘
                       ▼   (waits on dependencies, receives their outputs)
                  ✍️ writer
                       │
        🧭 complete? ── fails ──► retry / fallback
                       │ ok
                       ▼
              final answer + sources
```

## Requirements

- **Python 3.10+**
- **Node 18+** and **npm** (for the React web interface; the Streamlit version doesn't need it)
- A **DeepSeek API key** → https://platform.deepseek.com

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/mauriciodejuantrabajo/agent-orchestrator.git
cd agent-orchestrator

# 2. (Optional) virtual environment
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate the sample database (for the data agent)
python -m scripts.seed_db

# 5. Configure the API key (see next section)
```

## Configuration

```bash
cp .env.example .env       # on Windows: copy .env.example .env
```

Edit `.env` and set your DeepSeek key:

```env
DEEPSEEK_API_KEY=sk-your-real-key-here
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

> 🔒 **`.env` is in `.gitignore` and is never committed.** The versioned file is
> `.env.example`, which only carries a placeholder (`sk-...`).

## Usage

### Web interface (React + shadcn — recommended)

You need **two processes**: the backend (FastAPI) and the frontend (Vite).

```bash
# Terminal 1 — backend (at the repo root)
uvicorn server:app --reload --port 8000

# Terminal 2 — frontend
cd web
npm install        # first time only
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the backend (port 8000), so
nothing else needs configuring. Type your request and you'll see, live, the
orchestrator's **plan** and how each agent works in its **card** (with a status
indicator), down to the final answer in Markdown.

> **For production** you can run `npm run build` (it generates `web/dist`) and
> serve those static files behind the same FastAPI; in development, the flow above
> is the comfortable one.

### Alternative web interface (Streamlit, no npm)

If you don't want to spin up Node, the Streamlit version is still available:

```bash
streamlit run app.py
```

### CLI

```bash
python -m src.main "How many laptops were sold and how much did they bill in total?"
python -m src.main                                  # interactive mode
python -m src.main "your request" -o answer.md      # saves the answer
```

### Ideas to test the routing

- *"Which region sold the most units?"* → only **data**.
- *"Add 12, 30 and 8 and multiply it by 25."* → only **math**.
- *"Look up the population of Uruguay and Paraguay and compute the difference."* →
  **research** (×2 in parallel) → **math** → **writer**.
- *"What is the Model Context Protocol and how many letters does its acronym
  have?"* → **research** + **math** → **writer**.

## The model

It uses the **DeepSeek** API (OpenAI-compatible format). The model is configurable
in `.env` without touching code:

```env
DEEPSEEK_MODEL=deepseek-v4-flash
```

## Tests

```bash
pytest
```

The tests replace the LLM with a fake one (acting as the planner and each agent
according to the role) and mock the tools. They cover: the safe `calc` parser,
the write-blocking in `run_sql`, the **DAG validation** (valid agents, existing
dependencies, no cycles) and the **full flow** of the orchestrator —including the
parallelism of independent steps and the *fallback* on an invalid plan. **No real
network call is made**, so the CI is reproducible and doesn't consume the API
quota.

## License

[MIT](LICENSE) © Mauricio De Juan
