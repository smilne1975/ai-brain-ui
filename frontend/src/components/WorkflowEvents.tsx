import { useEffect, useState } from "react"
import { fetchWorkflowEvents, postWorkflowEvent } from "../api"
import type { WorkflowBoard, WorkflowEvent, WorkflowPreview } from "../types"

export function WorkflowEvents({ project }: { project: string }) {
  const [board, setBoard] = useState<WorkflowBoard | null>(null)
  const [kind, setKind] = useState("test")
  const [draft, setDraft] = useState<WorkflowPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  useEffect(() => {
    let active = true
    void fetchWorkflowEvents(project).then((result) => { if (active) setBoard(result) })
      .catch((err: Error) => { if (active) setMessage(err.message) })
    return () => { active = false }
  }, [project])

  async function act(work: () => Promise<void>) {
    setBusy(true); setMessage("")
    try { await work() }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not process the event.") }
    finally { setBusy(false) }
  }

  async function received(event: WorkflowEvent) {
    setDraft(null)
    setBoard((previous) => previous && { ...previous, events: [event, ...previous.events.filter((row) => row.id !== event.id)] })
    setMessage(event.status === "accepted" ? "Webhook accepted the notification. Workflow completion is not checked."
      : event.status === "rejected" ? "Webhook rejected the notification." : "Delivery is unknown. Check n8n before retrying.")
  }

  return <div>
    <p className="quiet">Send a small notification only after reviewing it. No files or notes are included.</p>
    {board?.enabled ? <>
      <label>Event <select value={kind} disabled={busy} onChange={(event) => { setKind(event.target.value); setDraft(null) }}>
        <option value="test">Test event</option>
        <option value="ifc_handover_ready">IFC handover ready</option>
        <option value="knowledge_reviewed">Knowledge reviewed</option>
      </select></label>
      <button className="ghost" type="button" disabled={busy} onClick={() => void act(async () => {
        setDraft(await postWorkflowEvent<WorkflowPreview>(project, "preview", { type: kind }))
      })}>Preview notification</button>
    </> : board && <p>No authenticated n8n destination is configured for this project.</p>}
    {draft && <div className="knowledge-card">
      <p>Destination: <code>{draft.destination}</code> (configured endpoint)</p>
      <pre className="knowledge-previous">{JSON.stringify(draft.payload, null, 2)}</pre>
      <button type="button" className="primary" disabled={busy} onClick={() => void act(async () => {
        await received(await postWorkflowEvent<WorkflowEvent>(project, "send", { payload: draft.payload,
          expires: draft.expires, confirmation: draft.confirmation }))
      })}>Confirm and send to n8n</button>
      <button type="button" className="ghost" disabled={busy} onClick={() => setDraft(null)}>Cancel</button>
    </div>}
    {message && <p role="status">{message}</p>}
    {!!board?.events.length && <h3>Delivery history</h3>}
    {board?.events.map((event) => <details key={event.id}>
      <summary>{event.payload.type.replaceAll("_", " ")} · {event.status}</summary>
      <pre className="knowledge-previous">{JSON.stringify(event.payload, null, 2)}</pre>
      <p>{event.destination} · {event.attempts.length} attempt(s)</p>
      {board.enabled && event.status !== "accepted" && event.attempts.length < 5 && <button className="ghost" type="button" disabled={busy}
        onClick={() => {
          if (!window.confirm("Resend the same event ID? Check n8n first if it may already have received the event.")) return
          void act(async () => received(await postWorkflowEvent<WorkflowEvent>(project, `${encodeURIComponent(event.id)}/retry`)))
        }}>Retry same event</button>}
    </details>)}
  </div>
}
