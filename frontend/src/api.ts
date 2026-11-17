import type { AskResponse, Brain, BrainStatus, BriefBoard, CardBoard, ChatIndex, ConfigBoard, Digest, KnowledgeIndex, KnowledgePreview, McpDoctor, McpUsage, Timeline } from "./types"

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

export async function fetchChats(): Promise<ChatIndex> {
  const res = await fetch("/api/chats")
  if (!res.ok) throw new Error(await readDetail(res, "Copilot chats are not ready."))
  return res.json() as Promise<ChatIndex>
}

export async function fetchBriefs(): Promise<BriefBoard> {
  const res = await fetch("/api/briefs")
  if (!res.ok) throw new Error(await readDetail(res, "Handoff briefs are not ready."))
  return res.json() as Promise<BriefBoard>
}

export async function saveHandoff(projectId: string): Promise<{ path: string; name: string }> {
  const res = await fetch(`/api/brief/${encodeURIComponent(projectId)}/handoff`, { method: "POST" })
  if (!res.ok) throw new Error(await readDetail(res, "Could not write BRAIN_HANDOFF.md."))
  return res.json() as Promise<{ path: string; name: string }>
}

export async function fetchDigest(period: "day" | "week"): Promise<Digest> {
  const res = await fetch(`/api/digest?period=${period}`)
  if (!res.ok) throw new Error(await readDetail(res, "The digest is not ready."))
  return res.json() as Promise<Digest>
}

export async function exportDigest(period: "day" | "week"): Promise<Digest> {
  const res = await fetch(`/api/digest/export?period=${period}`, { method: "POST" })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save the digest."))
  return res.json() as Promise<Digest>
}

export async function fetchConfig(): Promise<ConfigBoard> {
  const res = await fetch("/api/microstation/config")
  if (!res.ok) throw new Error(await readDetail(res, "MicroStation configuration is not ready."))
  return res.json() as Promise<ConfigBoard>
}

export async function fetchCards(): Promise<CardBoard> {
  const res = await fetch("/api/cards")
  if (!res.ok) throw new Error(await readDetail(res, "Project cards are not ready."))
  return res.json() as Promise<CardBoard>
}

export async function fetchMcpUsage(): Promise<McpUsage> {
  const res = await fetch("/api/mcp/usage")
  if (!res.ok) throw new Error(await readDetail(res, "MCP usage is not ready."))
  return res.json() as Promise<McpUsage>
}

export async function fetchMcpDoctor(): Promise<McpDoctor> {
  const res = await fetch("/api/mcp/doctor")
  if (!res.ok) throw new Error(await readDetail(res, "The doctor could not run."))
  return res.json() as Promise<McpDoctor>
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

export async function fetchKnowledge(): Promise<KnowledgeIndex> {
  const res = await fetch("/api/knowledge")
  if (!res.ok) throw new Error(await readDetail(res, "Knowledge is not ready."))
  return res.json() as Promise<KnowledgeIndex>
}

export async function previewKnowledge(id: string): Promise<KnowledgePreview> {
  const res = await fetch(`/api/knowledge/${encodeURIComponent(id)}/preview`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not preview project knowledge."))
  return res.json() as Promise<KnowledgePreview>
}

export async function approveKnowledge(id: string, content: string, expected_revision: string | null, expected_sources: Record<string, string>) {
  const res = await fetch(`/api/knowledge/${encodeURIComponent(id)}/approve`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, expected_revision, expected_sources }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save knowledge page."))
  return res.json()
}

export async function saveAnswer(project_id: string, title: string, answer: string, source_ids: string[]) {
  const res = await fetch("/api/answers", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id, title, answer, source_ids }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save answer."))
  return res.json()
}

export async function saveReviewedSkill(project_id: string, name: string, description: string, steps: string) {
  const res = await fetch("/api/skills/reviewed", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id, name, description, steps }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save reviewed skill."))
  return res.json() as Promise<{ path: string; name: string }>
}
