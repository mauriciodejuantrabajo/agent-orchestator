import { Loader2, Check, X } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { agentMeta } from "@/lib/agents"

export type StepState = "running" | "done" | "failed"

export type StepView = {
  id: string
  agent: string
  task: string
  state: StepState
  tools?: string
}

export function StepCard({ step }: { step: StepView }) {
  const meta = agentMeta(step.agent)
  const Icon = meta.icon

  return (
    <Card
      className={cn(
        "flex flex-row items-start gap-3 p-4 ring-1 transition-all",
        meta.ring,
        step.state === "running" && "animate-in fade-in slide-in-from-bottom-2",
      )}
    >
      <div
        className={cn(
          "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted",
          meta.text,
        )}
      >
        <Icon className="size-5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn("text-sm font-semibold", meta.text)}>{meta.label}</span>
          <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-mono">
            {step.id}
          </Badge>
          <span className="ml-auto">
            {step.state === "running" && (
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            )}
            {step.state === "done" && <Check className="size-4 text-emerald-500" />}
            {step.state === "failed" && <X className="size-4 text-destructive" />}
          </span>
        </div>

        <p className="mt-1 text-sm text-foreground/90">{step.task}</p>

        {step.tools && (
          <p className="mt-1.5 truncate font-mono text-xs text-muted-foreground">
            {step.tools}
          </p>
        )}
      </div>
    </Card>
  )
}
