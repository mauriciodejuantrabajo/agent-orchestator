// Historial de consultas al orquestador, persistido en localStorage para que
// sobreviva a recargas de la página. Guarda la pregunta, la respuesta final, el
// plan (etiqueta) y la marca de tiempo.
import { useCallback, useEffect, useState } from "react"
import type { FinalResult } from "./orchestrator"

export type HistoryEntry = {
  id: string
  question: string
  result: FinalResult
  planLabel: string | null
  at: number // epoch ms
}

const KEY = "agent-orchestrator:history"
const MAX_ENTRIES = 30

function load(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : []
  } catch {
    return []
  }
}

export function useHistory() {
  const [entries, setEntries] = useState<HistoryEntry[]>(load)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(entries))
    } catch {
      // Si localStorage no está disponible, el historial vive solo en memoria.
    }
  }, [entries])

  const add = useCallback(
    (question: string, result: FinalResult, planLabel: string | null): string => {
      const entry: HistoryEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        question,
        result,
        planLabel,
        at: Date.now(),
      }
      setEntries((prev) => [entry, ...prev].slice(0, MAX_ENTRIES))
      return entry.id
    },
    [],
  )

  const remove = useCallback((id: string) => {
    setEntries((prev) => prev.filter((e) => e.id !== id))
  }, [])

  const clear = useCallback(() => setEntries([]), [])

  return { entries, add, remove, clear }
}
