import { Compass, Plus, Trash2, X, MessageSquare } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { HistoryEntry } from "@/lib/useHistory"

type Props = {
  entries: HistoryEntry[]
  activeId: string | null
  onOpen: (entry: HistoryEntry) => void
  onNew: () => void
  onRemove: (id: string) => void
  onClear: () => void
}

// Sidebar de historial al estilo ChatGPT: botón de "nueva consulta" arriba y la
// lista de consultas previas debajo, con la activa resaltada.
export function HistorySidebar({ entries, activeId, onOpen, onNew, onRemove, onClear }: Props) {
  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-card/40">
      {/* Marca */}
      <div className="flex items-center gap-2 px-3 py-3.5">
        <div className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-fuchsia-500/20 to-cyan-500/20 ring-1 ring-border">
          <Compass className="size-4" />
        </div>
        <span className="text-sm font-semibold">Agent Orchestrator</span>
      </div>

      {/* Nueva consulta */}
      <div className="px-3 pb-2">
        <Button
          variant="outline"
          onClick={onNew}
          className="w-full justify-start gap-2 bg-background/50"
        >
          <Plus className="size-4" /> Nueva consulta
        </Button>
      </div>

      {/* Lista */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {entries.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            Tus consultas aparecerán aquí.
          </p>
        ) : (
          <>
            <p className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
              Historial
            </p>
            <div className="space-y-0.5">
              {entries.map((entry) => (
                <div
                  key={entry.id}
                  className={cn(
                    "group flex items-center gap-2 rounded-lg px-2 py-2 text-sm transition-colors",
                    entry.id === activeId
                      ? "bg-accent text-foreground"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                  )}
                >
                  <button
                    onClick={() => onOpen(entry)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <MessageSquare className="size-4 shrink-0 opacity-70" />
                    <span className="line-clamp-1">{entry.question}</span>
                  </button>
                  <button
                    onClick={() => onRemove(entry.id)}
                    className="shrink-0 opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                    aria-label="Eliminar"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Pie: vaciar */}
      {entries.length > 0 && (
        <div className="border-t border-border px-3 py-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onClear}
            className="w-full justify-start gap-2 text-xs text-muted-foreground"
          >
            <Trash2 className="size-3.5" /> Vaciar historial
          </Button>
        </div>
      )}
    </aside>
  )
}
