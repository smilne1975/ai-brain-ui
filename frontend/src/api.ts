import type { AskResponse, Brain, BrainStatus, CardBoard, Timeline } from "./types"

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

export async function fetchTimeline(days: number): Promise<Timeline> {
  const res = await fetch(`/api/timeline?days=${days}`)
  if (!res.ok) throw new Error(await readDetail(res, "The timeline is not ready."))
  return res.json() as Promise<Timeline>
}

export async function fetchCards(): Promise<CardBoard> {
  const res = await fetch("/api/cards")
  if (!res.ok) throw new Error(await readDetail(res, "Project cards are not ready."))
  return res.json() as Promise<CardBoard>
}

async function readDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string }
    if (body.detail) return body.detail
  } catch {
    /* keep the fallback */
  }
  return fallback
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
