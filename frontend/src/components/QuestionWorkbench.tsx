import { useEffect, useState } from "react"
import type { AskEvidence } from "../types"

type Target = { question: string; project_ids: string[] }
type Snapshot = { items: AskEvidence[]; incomplete: boolean; missing_scopes: number }
type Watch = { id: string; revision: number; question: string; challenge: string; state: "following" | "unfollowed";
  scope: { rel: string; id: string; name: string }[]; checked_at: string; reviewed: Snapshot; snoozed_until: string | null;
  pending: { candidate: Snapshot; coverage_changed: boolean; changes: { type: string; before: AskEvidence | null; after: AskEvidence | null }[] } | null }
type Idea = { id: string; relation: string; why: string; older: AskEvidence & { date: string }; current: AskEvidence & { date: string } }
type Kept = { id: string; question: string; older: string; current: string }

async function request<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(path, body && { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  const data = await res.json() as T & { detail?: string }
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "The local review could not be completed.")
  return data
}

type Props = { target: Target | null; scannedAt: string; onEvidence: (item: AskEvidence) => void; onQuestionsChanged?: () => void }

export function QuestionWorkbench({ target, scannedAt, onEvidence, onQuestionsChanged }: Props) {
  const [watches, setWatches] = useState<Watch[]>([])
  const [kept, setKept] = useState<Kept[]>([])
  const [challenge, setChallenge] = useState("")
  const [proposal, setProposal] = useState<{ target: Target; idea: Idea } | null>(null)
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  const [clock, setClock] = useState(() => Date.now())
  useEffect(() => {
    let active = true
    void Promise.all([request<{ items: Watch[] }>("/api/living-questions"), request<{ items: Kept[] }>("/api/old-ideas")])
      .then(([questions, ideas]) => { if (active) { setWatches(questions.items); setKept(ideas.items) } })
      .catch((err: Error) => { if (active) setMessage(err.message) })
    return () => { active = false }
  }, [])

  async function act(work: () => Promise<void>) {
    setBusy(true); setMessage("")
    try { await work() }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not complete the local check.") }
    finally { setBusy(false); setClock(Date.now()) }
  }

  function update(row: Watch) {
    setWatches((before) => [row, ...before.filter((item) => item.id !== row.id)])
    onQuestionsChanged?.()
  }

  async function change(row: Watch, action: string) {
    const updated = await request<Watch>(`/api/living-questions/${encodeURIComponent(row.id)}`, { revision: row.revision, action })
    update(updated)
    setMessage(action === "check" ? (updated.pending ? "Open the comparison to review what changed." : "No material change was found in the checked evidence.") :
      action === "accept" ? "Evidence comparison accepted. No saved answer was rewritten." : "Followed question updated.")
  }

  function passage(item: AskEvidence) {
    return <><blockquote>{item.excerpt}</blockquote>{item.source_url ?
      <a href={item.source_url} target="_blank" rel="noreferrer">{item.label}</a> :
      <button type="button" className="ghost" onClick={() => onEvidence(item)}>{item.label}</button>}</>
  }

  const visible = watches.filter((row) => row.state === "following")
  const idea = proposal && proposal.target === target ? proposal.idea : null
  return <section className="knowledge-card" aria-label="Living questions and old ideas">
    <h2>Living questions</h2>
    <p className="quiet">Follow a question even before you know the answer. Checks use the pinned project scope, indexed passages and approved local clips. No web fetch, model call, or automatic answer rewrite.</p>
    {target && <div>
      <p>Last question: {target.question}</p>
      <label>What would change your mind? <input maxLength={280} value={challenge} placeholder="Optional phrases; separate with semicolons"
        onChange={(event) => setChallenge(event.target.value)} /></label>
      <button type="button" className="primary" disabled={busy} onClick={() => void act(async () => {
        update(await request<Watch>("/api/living-questions", { ...target, challenge })); setChallenge("")
        setMessage("Following this question locally.")
      })}>Follow this question</button>
      <button type="button" className="ghost" disabled={busy} onClick={() => void act(async () => {
        setProposal(null)
        const result = await request<{ idea: Idea | null }>("/api/old-ideas/preview", target)
        if (result.idea) setProposal({ target, idea: result.idea })
        else setMessage("No useful older connection found in the checked scope.")
      })}>Find a useful old connection</button>
    </div>}
    {message && <p role="status">{message}</p>}
    {idea && <div>
      <h3>{idea.relation}</h3><p>{idea.why}</p>
      <p><strong>Older · {idea.older.date}</strong></p>{passage(idea.older)}
      <p><strong>Current · {idea.current.date}</strong></p>{passage(idea.current)}
      {(["keep", "dismiss", "snooze"] as const).map((action) => <button key={action} type="button" className="ghost" disabled={busy}
        onClick={() => void act(async () => {
          await request("/api/old-ideas/feedback", { ...target, id: idea.id, action }); setProposal(null)
          if (action === "keep") setKept((await request<{ items: Kept[] }>("/api/old-ideas")).items)
          setMessage(action === "keep" ? "Connection kept locally." : action === "snooze" ? "Connection snoozed for a week." : "Connection dismissed.")
        })}>{action === "keep" ? "Keep connection" : action === "dismiss" ? "Not useful" : "Snooze a week"}</button>)}
    </div>}
    {visible.map((row) => {
      const snoozed = !!row.snoozed_until && Date.parse(row.snoozed_until) > clock
      return <details key={row.id}>
        <summary>{row.question}{snoozed ? " · snoozed" : row.pending ? " · changes to review" : row.reviewed.items.length ? "" : " · no matching evidence yet"}</summary>
        <p>Scope: {row.scope.map((item) => item.name).join(", ")}. Checked {new Date(row.checked_at).toLocaleString()}.</p>
        {row.challenge && <p>Challenge phrases: {row.challenge}</p>}
        {Date.parse(row.checked_at) < Date.parse(scannedAt) && <p className="quiet">There has been a new scan. Check it before relying on the last comparison.</p>}
        {!snoozed && <button className="ghost" type="button" disabled={busy} onClick={() => void act(() => change(row, "check"))}>Check local evidence</button>}
        <button className="ghost" type="button" disabled={busy} onClick={() => void act(() => change(row, snoozed ? "resume" : "snooze"))}>
          {snoozed ? "Resume" : "Snooze a week"}</button>
        <button className="ghost" type="button" disabled={busy} onClick={() => void act(() => change(row, "unfollow"))}>Unfollow</button>
        <details><summary>Last reviewed evidence ({row.reviewed.items.length})</summary>
          {row.reviewed.incomplete && <p className="quiet">Coverage was incomplete.</p>}
          {row.reviewed.items.map((item, index) => <div key={index}>{passage(item)}</div>)}
        </details>
        {!snoozed && row.pending && <div>
          <strong>Evidence comparison</strong>
          {(row.pending.coverage_changed || row.pending.candidate.incomplete) && <p className="quiet">Coverage changed or was incomplete. A missing hit is not a confirmed removal.</p>}
          {row.pending.changes.map((item, index) => <details key={index}><summary>{item.type} — {item.after?.label ?? item.before?.label}</summary>
            {item.before && <><p>Before</p>{passage(item.before)}</>}
            {item.after && <><p>Now</p>{passage(item.after)}</>}
          </details>)}
          <button type="button" className="primary" disabled={busy} onClick={() => void act(() => change(row, "accept"))}>Accept evidence comparison</button>
        </div>}
      </details>
    })}
    {!!kept.length && <details><summary>Connections you kept ({kept.length})</summary>
      {kept.map((item) => <p key={item.id}>{item.question}: {item.older} → {item.current}</p>)}</details>}
  </section>
}
