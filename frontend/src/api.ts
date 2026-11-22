import type { AskResponse, Brain, BrainStatus, BriefBoard, CardBoard, ChatIndex, ClipDraft, ConfigBoard, DeliverableDraft, DeliverableRecord, Digest, KnowledgeIndex, KnowledgePreview, McpDoctor, McpUsage, MeetingItem, ObsidianPreview, SavedMeetingItem, Timeline, VoiceDraft, VoiceItem, VoiceNote, WebClip, WorkflowBoard } from "./types"
import type { CaptureItem, CaptureReceipt, LinkReview, ScanReplay, TraceQuestion, TraceRecord } from "./types"

async function localReview<T>(path: string, fallback: string, body?: object): Promise<T> {
  const res = await fetch(path, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readDetail(res, fallback))
  return res.json() as Promise<T>
}

export function fetchSourceReview(project: string) {
  return localReview<{ items: KnowledgeIndex["source_impact"]; limited: boolean }>(`/api/source-review/${encodeURIComponent(project)}`, "Could not check source changes.")
}

export function getLinkReview(project: string, review?: { id: string; state: "kept" | "dismissed" }) {
  return localReview<LinkReview>(`/api/link-review/${encodeURIComponent(project)}${review ? `/${encodeURIComponent(review.id)}` : ""}`,
    "Could not review suggested links.", review && { state: review.state })
}

export function getCaptures(project: string) {
  return localReview<{ items: CaptureItem[] }>(`/api/captures/${encodeURIComponent(project)}`, "Could not load captures.")
}

export function stageCapture(project: string, filename: string, text: string, kind: CaptureItem["kind"]) {
  return localReview<CaptureReceipt>(`/api/captures/${encodeURIComponent(project)}`, "Could not stage this item.", { filename, text, kind })
}

export function changeCapture(project: string, id: string, action: "approve" | "undo" | "remove", tags = "", filing = "") {
  return localReview<{ item?: CaptureItem; removed?: boolean; duplicate?: WebClip }>(`/api/captures/${encodeURIComponent(project)}/${encodeURIComponent(id)}`,
    "Could not update this capture.", { action, tags, filing })
}

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
    if (typeof body.detail === "string") return body.detail
  } catch {
    /* keep the fallback */
  }
  return fallback
}

export async function ask(question: string, projectId: string | null, projectIds?: string[]): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, project_id: projectId, project_ids: projectIds }),
  })
  if (!res.ok) throw new Error("The question could not be answered.")
  return res.json() as Promise<AskResponse>
}

export async function fetchKnowledge(): Promise<KnowledgeIndex> {
  const res = await fetch("/api/knowledge")
  if (!res.ok) throw new Error(await readDetail(res, "Knowledge is not ready."))
  return res.json() as Promise<KnowledgeIndex>
}

export async function previewKnowledge(id: string, topic?: string, sourceIds?: string[]): Promise<KnowledgePreview> {
  const search = new URLSearchParams()
  if (topic) search.set("topic", topic)
  for (const sourceId of sourceIds ?? []) search.append("source_ids", sourceId)
  const res = await fetch(`/api/knowledge/${encodeURIComponent(id)}/preview?${search}`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not preview project knowledge."))
  return res.json() as Promise<KnowledgePreview>
}

export async function approveKnowledge(id: string, content: string, expected_revision: string | null, expected_sources: Record<string, string>,
  topic: string | null, source_ids: string[] | null) {
  const res = await fetch(`/api/knowledge/${encodeURIComponent(id)}/approve`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, expected_revision, expected_sources, topic, source_ids }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save knowledge page."))
  return res.json()
}

export async function fetchScanReplay(project: string | null, frame: number | null, signal?: AbortSignal): Promise<ScanReplay> {
  const search = new URLSearchParams()
  if (project) search.set("project_id", project)
  if (frame !== null) search.set("frame", String(frame))
  const res = await fetch(`/api/scan-replay?${search}`, { signal })
  if (!res.ok) throw new Error(await readDetail(res, "Scan history is not available."))
  return res.json()
}

export async function fetchTraceQuestions(signal: AbortSignal): Promise<{ items: TraceQuestion[] }> {
  const res = await fetch("/api/living-questions", { signal })
  if (!res.ok) throw new Error(await readDetail(res, "Followed questions could not be loaded."))
  return res.json()
}

export async function fetchTraceRecords(project: string, signal: AbortSignal): Promise<{ items: TraceRecord[]; history: TraceRecord[] }> {
  const res = await fetch(`/api/project-records/${encodeURIComponent(project)}`, { signal })
  if (!res.ok) throw new Error(await readDetail(res, "Project decisions could not be loaded."))
  return res.json()
}

export async function reviewKnowledge(draft: KnowledgePreview, content: string) {
  const res = await fetch(`/api/knowledge/${encodeURIComponent(draft.project_id)}/review`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, expected_revision: draft.current_revision,
      expected_sources: Object.fromEntries(draft.sources.map((item) => [item.id, item.sha256])), topic: draft.topic, source_ids: draft.source_ids }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not check the draft."))
  return res.json() as Promise<{ findings: { kind: string; detail: string; blocking: boolean }[]; diff: string; diff_limited: boolean }>
}

export async function fetchMeetings(project: string) {
  const res = await fetch(`/api/meetings/${encodeURIComponent(project)}`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not load approved meeting items."))
  return res.json() as Promise<{ items: SavedMeetingItem[] }>
}

export async function previewMeeting(project: string, notes: string) {
  const res = await fetch(`/api/meetings/${encodeURIComponent(project)}/preview`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not review meeting notes."))
  return res.json() as Promise<{ source_id: string; items: MeetingItem[] }>
}

export async function approveMeeting(project: string, notes: string, sourceName: string, sourceId: string, items: MeetingItem[]) {
  const res = await fetch(`/api/meetings/${encodeURIComponent(project)}/approve`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes, source_name: sourceName, source_id: sourceId,
      items: items.map(({ line, text, owner, due }) => ({ line, text, owner, due })) }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save meeting items."))
  return res.json() as Promise<{ added: number; already_saved: number }>
}

export async function fetchClips(project: string) {
  const res = await fetch(`/api/web-clips/${encodeURIComponent(project)}`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not load web clips."))
  return res.json() as Promise<{ items: WebClip[] }>
}

export async function previewClip(project: string, filename: string, markdown: string) {
  const res = await fetch(`/api/web-clips/${encodeURIComponent(project)}/preview`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename, markdown }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not preview the clip."))
  return res.json() as Promise<ClipDraft>
}

export async function approveClip(project: string, filename: string, markdown: string, expected_id: string) {
  const res = await fetch(`/api/web-clips/${encodeURIComponent(project)}/approve`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename, markdown, expected_id }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not approve the clip."))
  return res.json() as Promise<{ clip: WebClip; created: boolean }>
}

export async function setClipActive(project: string, clip: string, active: boolean) {
  const res = await fetch(`/api/web-clips/${encodeURIComponent(project)}/${encodeURIComponent(clip)}/state`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not update the clip."))
  return res.json() as Promise<WebClip>
}

export async function fetchDeliverables(project: string) {
  const res = await fetch(`/api/deliverables/${encodeURIComponent(project)}`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not load tracked deliverables."))
  return res.json() as Promise<{ items: DeliverableRecord[] }>
}

export async function writeDeliverable<T = DeliverableDraft>(project: string, action: string, body: object) {
  const res = await fetch(`/api/deliverables/${encodeURIComponent(project)}/${action}`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not process the deliverable."))
  return res.json() as Promise<T>
}

export async function fetchWorkflowEvents(project: string) {
  const res = await fetch(`/api/workflow-events/${encodeURIComponent(project)}`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not load workflow events."))
  return res.json() as Promise<WorkflowBoard>
}

export async function postWorkflowEvent<T>(project: string, action: string, body?: object) {
  const res = await fetch(`/api/workflow-events/${encodeURIComponent(project)}/${action}`, { method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) throw new Error(await readDetail(res, "Could not process the workflow event."))
  return res.json() as Promise<T>
}

export async function fetchVoiceNotes(project: string) {
  const res = await fetch(`/api/voice-notes/${encodeURIComponent(project)}`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not load voice notes."))
  return res.json() as Promise<{ available: boolean; items: VoiceNote[] }>
}

export async function previewVoiceNote(project: string, file: File) {
  const query = new URLSearchParams({ filename: file.name.slice(0, 160) })
  const res = await fetch(`/api/voice-notes/${encodeURIComponent(project)}/preview?${query}`, { method: "POST",
    headers: { "Content-Type": "audio/wav" }, body: file })
  if (!res.ok) throw new Error(await readDetail(res, "Could not transcribe the audio locally."))
  return res.json() as Promise<VoiceDraft>
}

export async function approveVoiceNote(project: string, draft: string, items: VoiceItem[]) {
  const res = await fetch(`/api/voice-notes/${encodeURIComponent(project)}/${encodeURIComponent(draft)}/approve`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items: items.map(({ segment, kind, text }) => ({ segment, kind, text })) }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save approved voice notes."))
  return res.json() as Promise<VoiceNote>
}

export async function discardVoiceNote(project: string, draft: string) {
  const res = await fetch(`/api/voice-notes/${encodeURIComponent(project)}/${encodeURIComponent(draft)}/discard`, { method: "POST" })
  if (!res.ok) throw new Error(await readDetail(res, "Could not discard the voice draft."))
}

export async function previewObsidian(project: string) {
  const res = await fetch(`/api/obsidian/${encodeURIComponent(project)}/preview`)
  if (!res.ok) throw new Error(await readDetail(res, "Could not preview the Obsidian package."))
  return res.json() as Promise<ObsidianPreview>
}

export async function downloadObsidian(project: string, preview: ObsidianPreview) {
  const res = await fetch(`/api/obsidian/${encodeURIComponent(project)}/download`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ export_id: preview.export_id, token: preview.token }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not download the Obsidian package."))
  return res.blob()
}

export async function saveAnswer(project_id: string, title: string, answer: string, source_ids: string[],
  passages: { id: string; excerpt: string; page?: number | null }[] = []) {
  const res = await fetch("/api/answers", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id, title, answer, source_ids, passages }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save answer."))
  return res.json()
}

export async function saveReviewedSkill(project_id: string, name: string, description: string, steps: string) {
  const res = await fetch("/api/skills/reviewed", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id, name, description, steps }) })
  if (!res.ok) throw new Error(await readDetail(res, "Could not save reviewed skill."))
  return res.json() as Promise<{ path: string; name: string }>
}
