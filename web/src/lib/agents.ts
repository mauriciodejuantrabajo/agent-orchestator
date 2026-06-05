// Presentación de cada agente en la UI: emoji, etiqueta y clases de color.
import { Search, Calculator, Database, PenLine, type LucideIcon } from "lucide-react"

export type AgentMeta = {
  label: string
  icon: LucideIcon
  // Clases Tailwind para el acento de color de cada agente.
  ring: string
  text: string
  dot: string
}

export const AGENTS: Record<string, AgentMeta> = {
  research: {
    label: "Research",
    icon: Search,
    ring: "ring-cyan-500/30",
    text: "text-cyan-400",
    dot: "bg-cyan-500",
  },
  math: {
    label: "Math",
    icon: Calculator,
    ring: "ring-amber-500/30",
    text: "text-amber-400",
    dot: "bg-amber-500",
  },
  data: {
    label: "Data",
    icon: Database,
    ring: "ring-emerald-500/30",
    text: "text-emerald-400",
    dot: "bg-emerald-500",
  },
  writer: {
    label: "Writer",
    icon: PenLine,
    ring: "ring-fuchsia-500/30",
    text: "text-fuchsia-400",
    dot: "bg-fuchsia-500",
  },
}

export function agentMeta(agent: string): AgentMeta {
  return (
    AGENTS[agent] ?? {
      label: agent,
      icon: Search,
      ring: "ring-zinc-500/30",
      text: "text-zinc-400",
      dot: "bg-zinc-500",
    }
  )
}
