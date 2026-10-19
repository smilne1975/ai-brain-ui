import type { AskResponse, Brain, BrainStatus } from "./types"

export async function fetchStatus(): Promise<BrainStatus> {
  const res = await fetch("/api/health")
  if (!res.ok) throw new Error("AI Brain is not responding.")
  return res.json() as Promise<BrainStatus>
}

export async function fetchBrain(): Promise<Brain> {
  const res = await fetch("/api/brain")
  if (!res.ok) {
    let detail = "The folder could not be scanned."
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* keep the fallback */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<Brain>
}

export async function rescan(): Promise<BrainStatus> {
  const res = await fetch("/api/rescan", { method: "POST" })
  if (!res.ok) throw new Error("Rescan failed.")
  return res.json() as Promise<BrainStatus>
}

export async function ask(question: string, projectId: string | null): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, project_id: projectId }),
  })
  if (!res.ok) throw new Error("The question could not be answered.")
  return res.json() as Promise<AskResponse>
}
