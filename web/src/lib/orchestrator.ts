// Tipos y cliente del stream SSE del orquestador.
// El backend (FastAPI) emite tres tipos de eventos en /api/stream:
//   - "progress": un Event del orquestador (plan, step_start, step_done, ...)
//   - "final":    la respuesta unificada + plan + bibliografía
//   - "error":    un mensaje de error

export type ProgressEvent = {
  kind: "plan" | "step_start" | "step_done" | "step_failed" | "info" | "final"
  step_id: string
  agent: string
  message: string
}

export type PlanStep = {
  id: string
  agent: string
  task: string
  depends_on: string[]
}

export type FinalResult = {
  answer: string
  bibliography: string
  plan: PlanStep[]
}

export type StreamHandlers = {
  onProgress: (ev: ProgressEvent) => void
  onFinal: (result: FinalResult) => void
  onError: (message: string) => void
  onDone: () => void
}

// Abre el stream SSE y delega cada evento a los handlers.
// Devuelve una función para cerrar la conexión.
export function runOrchestrator(question: string, handlers: StreamHandlers): () => void {
  const url = `/api/stream?q=${encodeURIComponent(question)}`
  const source = new EventSource(url)

  source.addEventListener("progress", (e) => {
    handlers.onProgress(JSON.parse((e as MessageEvent).data))
  })
  source.addEventListener("final", (e) => {
    handlers.onFinal(JSON.parse((e as MessageEvent).data))
    source.close()
    handlers.onDone()
  })
  source.addEventListener("error", (e) => {
    // Puede ser un error de la app (con data) o un corte de conexión (sin data).
    const data = (e as MessageEvent).data
    if (data) {
      try {
        handlers.onError(JSON.parse(data).message ?? "Error desconocido.")
      } catch {
        handlers.onError("Error en el stream.")
      }
    } else {
      handlers.onError("Se perdió la conexión con el servidor.")
    }
    source.close()
    handlers.onDone()
  })

  return () => source.close()
}
