import { useEffect, useState } from "react"
import type { KnowledgeIndex, KnowledgeSource } from "../types"

type Session = { id: string; title: string; when: string | null }
type Kind = "decision" | "constraint" | "gotcha" | "failed attempt" | "fact" | "handoff"
type Entry = { id: string; revision: number; kind: Kind; state: string; title: string; text: string; next_step: string;
  intended: string; owner: string | null; actor?: string; sources: KnowledgeSource[]; stale_sources: string[]; stale_memory: string[];
  memory: { id: string; title: string; text: string; revision: number }[]; session: Session | null; updated_at: string }
type Board = { items: Entry[]; history: Entry[] }
const empty = { kind: "decision" as Kind, state: "confirmed", title: "", text: "", next_step: "", intended: "",
  source_ids: [] as string[], memory_ids: [] as string[], session_id: null as string | null }

async function request<T>(project: string, suffix = "", body?: object): Promise<T> {
  const response = await fetch(`/api/project-records/${encodeURIComponent(project)}${suffix}`, body && {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  const value = await response.json() as T & { detail?: string }
  if (!response.ok) throw new Error(value.detail || "Unable to read or save the project record.")
  return value
}

export function ProjectRecords({ project, sources, clips, scan }: { project: string; sources: { id: string; label: string }[];
  clips: KnowledgeIndex["available_clips"]; scan: string }) {
  const [board, setBoard] = useState<Board>({ items: [], history: [] })
  const [input, setInput] = useState(empty)
  const [editing, setEditing] = useState<Entry | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [filter, setFilter] = useState("")
  const [actor, setActor] = useState("")
  const [message, setMessage] = useState("")
  const [recallPreview, setRecallPreview] = useState<{ payload: object; receipts: { id: string; at: string; layer: string;
    delivery: string; items: { id: string; title: string }[]; omitted: object }[] } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void request<Board>(project).then((value) => { if (active) setBoard(value) })
      .catch((err: Error) => { if (active) setMessage(err.message) })
    return () => { active = false }
  }, [project, scan])

  async function act(work: () => Promise<void>) {
    setBusy(true); setMessage("")
    try { await work() }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not update the record.") }
    finally { setBusy(false) }
  }

  const selectedSources = [...sources, ...clips.filter((clip) => clip.project_id === project).map((clip) => ({ id: clip.id, label: `Web clip: ${clip.title}` }))]
  const facts = board.items.filter((item) => item.kind === "fact")
  const shown = board.items.filter((item) => `${item.title} ${item.kind} ${item.state} ${item.text}`.toLowerCase().includes(filter.trim().toLowerCase()))
  return <div>
    <p className="quiet">Record decisions, constraints, failed attempts, or facts with evidence. Handoffs stay here until someone claims them; nothing is sent to another agent.</p>
    <fieldset disabled={busy}>
      <legend>{editing ? "Correct reviewed record" : "New reviewed record or handoff"}</legend>
      <label>Record type <select disabled={!!editing} value={input.kind} onChange={(event) => setInput({ ...input, kind: event.target.value as Kind })}>
        {(["decision", "constraint", "gotcha", "failed attempt", "fact", "handoff"] as const).map((kind) => <option key={kind}>{kind}</option>)}
      </select></label>
      {input.kind === "fact" && <label>Confidence <select value={input.state} onChange={(event) => setInput({ ...input, state: event.target.value })}>
        <option>confirmed</option><option>inferred</option><option>unknown</option>
      </select></label>}
      <input aria-label="Record subject" maxLength={140} placeholder="Subject (use the same subject for competing facts)" value={input.title}
        onChange={(event) => setInput({ ...input, title: event.target.value })} />
      <textarea aria-label="Record details" maxLength={3000} rows={4} value={input.text}
        placeholder={input.kind === "handoff" ? "Current state, failed approaches and open questions" : "Statement, reasons, constraints, or evidence notes"}
        onChange={(event) => setInput({ ...input, text: event.target.value })} />
      {input.kind === "handoff" && <>
        <input aria-label="Next action" maxLength={1200} placeholder="Next action" value={input.next_step} onChange={(event) => setInput({ ...input, next_step: event.target.value })} />
        <input aria-label="Intended assistant" maxLength={120} placeholder="Intended assistant (optional)" value={input.intended} onChange={(event) => setInput({ ...input, intended: event.target.value })} />
        <button type="button" className="ghost" onClick={() => void act(async () => {
          const result = await request<{ items: Session[]; incomplete: boolean }>(project, "/sessions")
          setSessions(result.items)
          if (!result.items.length || result.incomplete) setMessage("Session evidence may be incomplete. You can save the handoff manually without it.")
        })}>Find local session evidence</button>
        {!!sessions.length && <select aria-label="Attached session evidence" value={input.session_id ?? ""}
          onChange={(event) => setInput({ ...input, session_id: event.target.value || null })}>
          <option value="">No attached session</option>{sessions.map((session) => <option key={session.id} value={session.id}>{session.title}</option>)}
        </select>}
        <details><summary>Attach reviewed memory (up to 8)</summary>
          {board.items.filter((item) => ["reviewed", "confirmed"].includes(item.state) && !item.stale_sources.length).map((item) =>
            <label key={item.id}><input type="checkbox" checked={input.memory_ids.includes(item.id)}
              disabled={input.memory_ids.length >= 8 && !input.memory_ids.includes(item.id)} onChange={(event) => setInput({ ...input,
                memory_ids: event.target.checked ? [...input.memory_ids, item.id] : input.memory_ids.filter((id) => id !== item.id) })} />{item.title}</label>)}
        </details>
      </>}
      <details><summary>Supporting evidence ({input.source_ids.length} selected)</summary>
        <div className="knowledge-source-list">{selectedSources.map((source) => <label key={source.id}><input type="checkbox"
          checked={input.source_ids.includes(source.id)} disabled={input.source_ids.length >= 12 && !input.source_ids.includes(source.id)}
          onChange={(event) => setInput({ ...input, source_ids: event.target.checked ? [...input.source_ids, source.id] : input.source_ids.filter((id) => id !== source.id) })} />{source.label}</label>)}</div>
        {input.source_ids.filter((id) => !selectedSources.some((source) => source.id === id)).map((id) =>
          <button type="button" className="ghost" key={id} onClick={() => setInput({ ...input, source_ids: input.source_ids.filter((key) => key !== id) })}>Remove unavailable source {id}</button>)}
      </details>
      <button type="button" className="primary" disabled={!input.title.trim() || !input.text.trim() || input.kind === "handoff" && !input.next_step.trim()}
        onClick={() => void act(async () => {
          await request(project, editing ? `/${encodeURIComponent(editing.id)}/edit` : "", { ...input,
            state: input.kind === "fact" ? input.state : null, expected_revision: editing?.revision })
          setInput(empty); setEditing(null); setBoard(await request<Board>(project)); setMessage("Record saved locally.")
        })}>{editing ? "Save correction" : "Approve and save"}</button>
      {editing && <button type="button" className="ghost" onClick={() => { setInput(empty); setEditing(null) }}>Cancel correction</button>}
    </fieldset>
    {message && <p role="status">{message}</p>}
    <label>Find reviewed records <input value={filter} onChange={(event) => setFilter(event.target.value)} /></label>
    <label>Handoff claimant name <input maxLength={120} value={actor} onChange={(event) => setActor(event.target.value)} /></label>
    {shown.map((item) => <details key={item.id}>
      <summary>{item.title} · {item.kind} · {item.state}{(item.stale_sources.length || item.stale_memory.length) ? " · evidence needs recheck" : ""}</summary>
      <p>{item.text}</p>
      {!!item.sources.length && <ul>{item.sources.map((source) => <li key={source.id}>
        {source.source_url ? <a href={source.source_url} target="_blank" rel="noreferrer">{source.title ?? source.rel}</a> : <code>{source.rel}</code>}
        {item.stale_sources.includes(source.id) ? " · changed or unavailable" : ""}</li>)}</ul>}
      {item.kind === "fact" && facts.filter((other) => other.id !== item.id && other.title.toLowerCase() === item.title.toLowerCase() && other.text !== item.text)
        .map((other) => <p key={other.id}>Alternative ({other.state}): {other.text} · {other.sources.map((source) => source.rel).join(", ") || "No evidence attached"}</p>)}
      {item.kind !== "handoff" ? <button type="button" className="ghost" disabled={busy} onClick={() => {
        setEditing(item); setInput({ ...empty, kind: item.kind, title: item.title, text: item.text,
          state: item.kind === "fact" ? item.state : "confirmed", source_ids: item.sources.map((source) => source.id) })
      }}>Correct this record</button> : <>
        <p>Next: {item.next_step}{item.intended ? ` · Intended: ${item.intended}` : ""}{item.owner ? ` · Claimed by ${item.owner}` : ""}</p>
        <p className="quiet">{item.session ? `Session evidence: ${item.session.title}` : "Manual handoff; no session evidence attached."}</p>
        {item.memory.map((ref) => <p key={ref.id}>Reviewed memory: {ref.title} — {ref.text}</p>)}
        {(["claim", "complete", "cancel"] as const).filter((action) => item.state === "pending" ? action !== "complete" : item.state === "claimed" && action !== "claim")
          .map((action) => <button key={action} type="button" className="ghost" disabled={busy || !actor.trim()} onClick={() => void act(async () => {
            await request(project, `/${encodeURIComponent(item.id)}/transition`, { action, actor, expected_revision: item.revision })
            setBoard(await request<Board>(project)); setMessage("Handoff updated locally.")
          })}>{action}</button>)}
      </>}
    </details>)}
    {!!board.history.length && <details><summary>Recent project work log and corrections</summary>
      {board.history.map((item) => <details key={`${item.id}:${item.revision}`}><summary>{item.updated_at} · {item.title} · {item.state}{item.actor ? ` · ${item.actor}` : ""}</summary>
        <p>{item.text}</p></details>)}
    </details>}
    <details><summary>Copilot context and recall receipts</summary>
      <p className="quiet">Preview recent context here, or ask Copilot to call the opt-in <code>get_project_context</code> tool. Session-start context requires a separate hook you install yourself.</p>
      <button type="button" className="ghost" disabled={busy} onClick={() => void act(async () => {
        const result = await request<{ enabled: boolean; payload: object; receipts: NonNullable<typeof recallPreview>["receipts"] }>(project, "/recall")
        if (!result.enabled) { setRecallPreview(null); setMessage("Set BRAIN_ENABLE_PROJECT_RECALL=1 to enable this feature."); return }
        setRecallPreview(result)
      })}>Preview recent context and refresh receipts</button>
      {recallPreview && <>
        <pre className="knowledge-previous">{JSON.stringify(recallPreview.payload, null, 2)}</pre>
        <button type="button" className="ghost" onClick={() => void act(async () => {
          await navigator.clipboard.writeText(JSON.stringify(recallPreview.payload, null, 2))
          setMessage("Copied the preview. It was not sent to Copilot.")
        })}>Copy reviewed context</button>
        <h3>Recent recall receipts</h3>
        {!recallPreview.receipts.length && <p className="quiet">No receipts. Log explicit tool calls with BRAIN_RECALL_RECEIPTS=1.</p>}
        {recallPreview.receipts.map((row) => <details key={row.id}><summary>{row.at} · {row.layer} · {row.delivery}</summary>
          <ul>{row.items.map((item) => <li key={item.id}>{item.title}</li>)}</ul><pre>{JSON.stringify(row.omitted, null, 2)}</pre></details>)}
      </>}
    </details>
  </div>
}
