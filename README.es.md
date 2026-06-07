> **Idioma / Language:** [English](README.md) · **Español**

# 🧭 Agent Orchestrator

Un **supervisor** recibe tu petición, la **descompone en un plan** (un grafo de
sub-tareas) y **delega** cada una al agente especializado que corresponde —
investigación web, cálculo, datos SQL o redacción—, ejecutando **en paralelo**
lo que puede y respetando las dependencias entre pasos.

No es un pipeline fijo: el orquestador **decide en runtime** a quién rutear, junta
los resultados y produce una respuesta unificada. Usa **tool-calling nativo** de
la API de **DeepSeek**.

Tiene una **interfaz web moderna** (React + shadcn/ui + Tailwind sobre un backend
FastAPI, con el routing **en vivo** vía Server-Sent Events) y también **CLI**.

```
?  ¿Qué región vendió más unidades y cuánto facturó en total?

  🧭 Plan del orquestador: s1:data → s2:writer

  🗄️ data [s1] → averiguar región con más unidades y facturación total
     herramientas: run_sql(query='SELECT r.name, SUM(s.units) ...')
  ✍️ writer [s2] → redactar la respuesta final
     herramientas: (sin herramientas)

  Respuesta
  La región **Centro** fue la que más unidades vendió (241), seguida por
  Norte (208) y Sur (197). …
```

## El problema

Un único agente con muchas herramientas (buscar, calcular, consultar la base,
redactar) se confunde: elige mal la herramienta, mezcla responsabilidades y es
difícil de mantener. Y resolver todo "de un saque" impide aprovechar que algunas
sub-tareas son **independientes** y podrían correr a la vez.

## La solución

Separar **decisión** de **ejecución**, como un equipo con un líder:

1. **El supervisor planifica.** Descompone la petición en un **DAG** de
   sub-tareas: cada una dice *qué* agente la resuelve y *de qué* otras depende.
2. **El orquestador ejecuta el DAG.** Corre en **paralelo** los pasos sin
   dependencias entre sí, espera a los que dependen de otros y les pasa sus
   resultados como contexto.
3. **Un redactor unifica.** El `writer` sintetiza las salidas en la respuesta
   final, conservando las citas `[N]` de la investigación.

Cada agente tiene **una sola responsabilidad**, su propio prompt y un juego chico
de herramientas: piensa solo en su tarea y elige bien.

### Los agentes

| Agente | Rol | Herramientas |
|--------|-----|--------------|
| 🔎 **research** | Busca y lee páginas; responde con hechos y citas `[N]` | `web_search`, `read_url` |
| 🧮 **math** | Calcula de forma **exacta** (no "alucina" cuentas) | `calc` (parser aritmético seguro) |
| 🗄️ **data** | Responde consultando una base de ejemplo | `run_sql` (**solo lectura**) |
| ✍️ **writer** | Sintetiza los resultados en la respuesta final | — |

> **Seguro a propósito.** La calculadora **no ejecuta código**: evalúa solo
> expresiones aritméticas (`+ - * / // % **` y paréntesis) con un parser de AST,
> rechazando variables, funciones o imports. El acceso a datos es **SQL de solo
> lectura**: se bloquean `INSERT/UPDATE/DELETE/DROP/…` y la conexión se abre en
> modo `read-only`, así que ni un descuido puede modificar la base.

## Lo que lo hace un orquestador "de verdad"

- 🗺️ **Planificación en DAG**, no `if/else`: el supervisor arma el grafo de
  sub-tareas con sus dependencias.
- ⚡ **Paralelismo real**: los pasos independientes se ejecutan a la vez (las
  llamadas al LLM son I/O, así que baja el tiempo total).
- 🔁 **Re-planificación ante fallos**: si un paso falla, se reintenta; si el plan
  entero es inválido, hay un *fallback* para responder igual.
- 💰 **Presupuesto**: tope global de pasos para no entrar en loops caros (el costo
  es la preocupación #1 en producción).

## Arquitectura

```
server.py             Backend HTTP (FastAPI): expone el orquestador y lo
                      transmite EN VIVO por SSE (/api/stream).
app.py                Interfaz web alternativa (Streamlit), sin npm.
web/                  Frontend React + Vite + shadcn/ui + Tailwind.
├── src/App.tsx        UI principal: input, plan, tarjetas por agente, respuesta.
├── src/components/    StepCard + componentes de shadcn/ui.
└── src/lib/           Cliente SSE (orchestrator.ts) y metadata de agentes.
src/
├── llm.py            Cliente DeepSeek (compatible OpenAI): tool-calling.
├── tools.py          web_search, read_url, calc (AST seguro), run_sql (read-only).
├── agents.py         Los 4 agentes: research, math, data, writer.
├── planner.py        El supervisor: descompone la petición en un DAG (con validación).
├── orchestrator.py   Ejecuta el DAG: dependencias, paralelismo, presupuesto, re-plan.
└── main.py           CLI (rich) con traza viva del routing.
scripts/seed_db.py    Genera data/demo.db (base de ventas de ejemplo).
tests/                Tests con mocks (sin red real ni llamadas a la API).
```

El frontend (React) habla con el backend (FastAPI), que envuelve el orquestador
(Python). El progreso del routing viaja del orquestador al navegador en tiempo
real por **Server-Sent Events**:

```
  navegador (React/shadcn) ──HTTP──► FastAPI (server.py) ──► Orchestrator (src/)
        ▲                                                          │
        └──────────────── SSE: plan, pasos, respuesta ◄───────────┘
```

El **flujo** que coordina `orchestrator.py`:

```
            petición
               │
               ▼
        🧭 Planner ── descompone ──► DAG de sub-tareas
               │
        ┌──────┼───────────────┐   (paralelo donde no hay dependencia)
        ▼      ▼               ▼
   🔎 research 🧮 math      🗄️ data
        └──────┴───────┬───────┘
                       ▼   (espera dependencias, recibe sus salidas)
                  ✍️ writer
                       │
        🧭 ¿completo? ── falla ──► reintenta / fallback
                       │ ok
                       ▼
              respuesta final + fuentes
```

## Requisitos

- **Python 3.10+**
- **Node 18+** y **npm** (para la interfaz web React; la versión Streamlit no lo necesita)
- Una **API key de DeepSeek** → https://platform.deepseek.com

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/mauriciodejuantrabajo/agent-orchestrator.git
cd agent-orchestrator

# 2. (Opcional) entorno virtual
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Generar la base de ejemplo (para el agente de datos)
python -m scripts.seed_db

# 5. Configurar la API key (ver siguiente sección)
```

## Configuración

```bash
cp .env.example .env       # en Windows: copy .env.example .env
```

Edita `.env` y coloca tu key de DeepSeek:

```env
DEEPSEEK_API_KEY=sk-tu-key-real-aca
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

> 🔒 **`.env` está en `.gitignore` y nunca se sube.** El archivo versionado es
> `.env.example`, que solo trae un placeholder (`sk-...`).

## Uso

### Interfaz web (React + shadcn — recomendada)

Necesitás **dos procesos**: el backend (FastAPI) y el frontend (Vite).

```bash
# Terminal 1 — backend (en la raíz del repo)
uvicorn server:app --reload --port 8000

# Terminal 2 — frontend
cd web
npm install        # solo la primera vez
npm run dev
```

Abrí `http://localhost:5173`. Vite redirige `/api` al backend (puerto 8000), así
que no hay que configurar nada más. Escribí tu petición y vas a ver, en vivo, el
**plan** del orquestador y cómo cada agente trabaja en su **tarjeta** (con un
indicador de estado), hasta la respuesta final en Markdown.

> **Para producción** podés hacer `npm run build` (genera `web/dist`) y servir esos
> estáticos detrás del mismo FastAPI; en desarrollo, el flujo de arriba es lo cómodo.

### Interfaz web alternativa (Streamlit, sin npm)

Si no querés levantar Node, la versión Streamlit sigue disponible:

```bash
streamlit run app.py
```

### CLI

```bash
python -m src.main "¿Cuántas notebooks se vendieron y cuánto facturaron en total?"
python -m src.main                                  # modo interactivo
python -m src.main "tu petición" -o respuesta.md    # guarda la respuesta
```

### Ideas para probar el routing

- *"¿Qué región vendió más unidades?"* → solo **data**.
- *"Suma 12, 30 y 8 y multiplícalo por 25."* → solo **math**.
- *"Busca la población de Uruguay y de Paraguay y calcula la diferencia."* →
  **research** (×2 en paralelo) → **math** → **writer**.
- *"¿Qué es el Model Context Protocol y cuántas letras tiene su sigla?"* →
  **research** + **math** → **writer**.

## El modelo

Se usa la API de **DeepSeek** (formato compatible con OpenAI). El modelo es
configurable en `.env` sin tocar código:

```env
DEEPSEEK_MODEL=deepseek-v4-flash
```

## Tests

```bash
pytest
```

Los tests reemplazan el LLM por uno falso (que hace de planner y de cada agente
según el rol) y mockean las herramientas. Cubren: el parser seguro de `calc`, el
bloqueo de escritura en `run_sql`, la **validación del DAG** (agentes válidos,
dependencias existentes, sin ciclos) y el **flujo completo** del orquestador
—incluido el paralelismo de pasos independientes y el *fallback* ante un plan
inválido—. **No se hace ninguna llamada de red real**, así el CI es reproducible
y no consume la cuota de API.

## Licencia

[MIT](LICENSE) © Mauricio De Juan
