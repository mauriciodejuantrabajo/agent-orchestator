import { useRef, useState } from "react"
import { Compass, Send, Loader2, FileText } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { StepCard, type StepView } from "@/components/StepCard"
import { HistorySidebar } from "@/components/History"
import { runOrchestrator, type FinalResult, type ProgressEvent } from "@/lib/orchestrator"
import { useHistory, type HistoryEntry } from "@/lib/useHistory"
import { agentMeta } from "@/lib/agents"

const EXAMPLES = [
  "¿Qué región vendió más unidades y cuánto facturó en total?",
  "Busca la población de Uruguay y de Paraguay y calcula la diferencia.",
  "Suma 12, 30 y 8 y multiplícalo por 25.",
  "¿Qué es el Model Context Protocol y cuántas letras tiene su sigla?",
]

export default function App() {
  const [question, setQuestion] = useState("")
  const [running, setRunning] = useState(false)
  const [planLabel, setPlanLabel] = useState<string | null>(null)
  const [steps, setSteps] = useState<Record<string, StepView>>({})
  const [order, setOrder] = useState<string[]>([])
  const [result, setResult] = useState<FinalResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const closeRef = useRef<(() => void) | null>(null)

  // Para que el closure de onFinal vea la pregunta y el plan actuales.
  const pendingRef = useRef<{ question: string; planLabel: string | null }>({
    question: "",
    planLabel: null,
  })

  const history = useHistory()

  function reset() {
    setPlanLabel(null)
    setSteps({})
    setOrder([])
    setResult(null)
    setError(null)
  }

  // "Nueva consulta": limpia la vista y vuelve a la pantalla inicial.
  function newChat() {
    if (running) return
    reset()
    setQuestion("")
    setActiveId(null)
  }

  function handleProgress(ev: ProgressEvent) {
    if (ev.kind === "plan") {
      setPlanLabel(ev.message)
      pendingRef.current.planLabel = ev.message
      return
    }
    if (ev.kind === "step_start") {
      setSteps((s) => ({
        ...s,
        [ev.step_id]: { id: ev.step_id, agent: ev.agent, task: ev.message, state: "running" },
      }))
      setOrder((o) => (o.includes(ev.step_id) ? o : [...o, ev.step_id]))
      return
    }
    if (ev.kind === "step_done" || ev.kind === "step_failed") {
      setSteps((s) => ({
        ...s,
        [ev.step_id]: {
          ...s[ev.step_id],
          state: ev.kind === "step_done" ? "done" : "failed",
          tools: ev.message,
        },
      }))
    }
  }

  function submit(q: string) {
    const text = q.trim()
    if (!text || running) return
    reset()
    setActiveId(null)
    setRunning(true)
    pendingRef.current = { question: text, planLabel: null }
    closeRef.current = runOrchestrator(text, {
      onProgress: handleProgress,
      onFinal: (r) => {
        setResult(r)
        // Guardamos la consulta en el historial al terminar y la marcamos activa.
        const id = history.add(pendingRef.current.question, r, pendingRef.current.planLabel)
        setActiveId(id)
      },
      onError: (m) => setError(m),
      onDone: () => setRunning(false),
    })
  }

  // Reabre una consulta del historial sin volver a ejecutarla.
  function openFromHistory(entry: HistoryEntry) {
    if (running) return
    reset()
    setQuestion(entry.question)
    setPlanLabel(entry.planLabel)
    setResult(entry.result)
    setActiveId(entry.id)
  }

  function handleRemove(id: string) {
    history.remove(id)
    if (id === activeId) newChat()
  }

  function handleClear() {
    history.clear()
    newChat()
  }

  const showWelcome = !result && !running && !error && order.length === 0

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Resplandor de fondo */}
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-40 left-1/2 size-[42rem] -translate-x-1/2 rounded-full bg-fuchsia-500/10 blur-3xl" />
        <div className="absolute top-20 right-0 size-[28rem] rounded-full bg-cyan-500/10 blur-3xl" />
      </div>

      {/* Sidebar de historial (estilo ChatGPT) */}
      <HistorySidebar
        entries={history.entries}
        activeId={activeId}
        onOpen={openFromHistory}
        onNew={newChat}
        onRemove={handleRemove}
        onClear={handleClear}
      />

      {/* Área principal */}
      <main className="flex min-w-0 flex-1 flex-col">
        {/* Zona scrolleable de contenido */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-8">
            {showWelcome ? (
              <div className="flex flex-col items-center pt-16 text-center">
                <div className="mb-4 inline-flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-fuchsia-500/20 to-cyan-500/20 ring-1 ring-border">
                  <Compass className="size-7 text-foreground" />
                </div>
                <h1 className="text-3xl font-bold tracking-tight">Agent Orchestrator</h1>
                <p className="mx-auto mt-3 max-w-xl text-balance text-muted-foreground">
                  Un supervisor <span className="text-foreground">planifica</span> tu petición y
                  la <span className="text-foreground">rutea</span> al agente adecuado
                  —investigación, cálculo, datos SQL o redacción—, en paralelo cuando puede.
                </p>
                <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      onClick={() => {
                        setQuestion(ex)
                        submit(ex)
                      }}
                      className="rounded-xl border border-border bg-card p-3 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {/* La consulta actual, como "mensaje del usuario" */}
                {(question || result) && (
                  <div className="mb-6 flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                      {result ? pendingRef.current.question || question : question}
                    </div>
                  </div>
                )}

                {error && (
                  <Card className="border-destructive/50 p-4 text-sm text-destructive">
                    {error}
                  </Card>
                )}

                {/* Plan */}
                {planLabel && (
                  <div className="mb-5">
                    <div className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Compass className="size-4" /> Plan del orquestador
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {planLabel.split(" → ").map((token, i) => {
                        const agent = token.split(":")[1] ?? token
                        const meta = agentMeta(agent)
                        return (
                          <div key={i} className="flex items-center gap-1.5">
                            {i > 0 && <span className="text-muted-foreground">→</span>}
                            <Badge variant="secondary" className="gap-1">
                              <span className={`size-1.5 rounded-full ${meta.dot}`} />
                              {token}
                            </Badge>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Pasos en vivo */}
                {order.length > 0 && (
                  <div className="mb-6 space-y-2.5">
                    {order.map((id) => (
                      <StepCard key={id} step={steps[id]} />
                    ))}
                  </div>
                )}

                {/* Respuesta final */}
                {result && (
                  <div>
                    <Separator className="mb-6" />
                    <div className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <FileText className="size-4" /> Respuesta
                    </div>
                    <Card className="p-6">
                      <div className="prose prose-sm prose-invert max-w-none prose-headings:font-semibold prose-a:text-cyan-400">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {result.answer}
                        </ReactMarkdown>
                      </div>
                    </Card>

                    {result.bibliography && (
                      <details className="mt-4 rounded-lg border border-border bg-card p-4 text-sm">
                        <summary className="cursor-pointer font-medium text-muted-foreground">
                          Fuentes
                        </summary>
                        <pre className="mt-3 whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                          {result.bibliography}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Barra de input fija abajo (estilo ChatGPT) */}
        <div className="border-t border-border bg-background/80 backdrop-blur">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit(question)
            }}
            className="mx-auto flex max-w-3xl gap-2 px-4 py-4"
          >
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Escribe tu petición…"
              disabled={running}
              className="h-12 text-base"
            />
            <Button type="submit" disabled={running || !question.trim()} className="h-12 px-5">
              {running ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5" />}
            </Button>
          </form>
        </div>
      </main>
    </div>
  )
}
