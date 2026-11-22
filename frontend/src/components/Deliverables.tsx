import { useEffect, useState } from "react"
import { fetchDeliverables, writeDeliverable } from "../api"
import type { DeliverableDraft, DeliverableRecord, KnowledgePage } from "../types"

export function Deliverables({ project, pages }: { project: string; pages: KnowledgePage[] }) {
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [draft, setDraft] = useState<DeliverableDraft | null>(null)
  const [items, setItems] = useState<DeliverableRecord[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const scoped = pages.filter((page) => page.project_id === project)

  useEffect(() => {
    let active = true
    void fetchDeliverables(project).then((result) => { if (active) setItems(result.items) })
      .catch((err: Error) => { if (active) setMessage(err.message) })
    return () => { active = false }
  }, [project, pages])

  async function act(work: () => Promise<void>) {
    setBusy(true); setMessage("")
    try { await work() }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not process deliverable.") }
    finally { setBusy(false) }
  }

  return <div>
    <p className="quiet">Save a local Markdown report or handover with the exact approved pages and source files that support it. Nothing is published or rewritten automatically.</p>
    <label>Deliverable title <input maxLength={150} value={title} disabled={busy}
      onChange={(event) => { setTitle(event.target.value); setDraft(null) }} /></label>
    <textarea aria-label="Deliverable Markdown" rows={8} maxLength={80_000} value={content} disabled={busy}
      onChange={(event) => { setContent(event.target.value); setDraft(null) }} />
    <fieldset disabled={busy}>
      <legend>Approved knowledge pages</legend>
      {!scoped.length && <p className="quiet">Approve a knowledge page for this project first.</p>}
      {scoped.map((page) => <label key={page.page_id}><input type="checkbox" checked={selected.includes(page.page_id)}
        disabled={!!page.stale_sources.length || (selected.length >= 12 && !selected.includes(page.page_id))}
        onChange={(event) => { setDraft(null); setSelected(event.target.checked ? [...selected, page.page_id] : selected.filter((item) => item !== page.page_id)) }} />
        {page.title}{page.stale_sources.length ? " · needs recheck" : ""}</label>)}
    </fieldset>
    <button className="ghost" type="button" disabled={busy || !title.trim() || !content.trim() || !selected.length}
      onClick={() => void act(async () => { setDraft(await writeDeliverable(project, "preview", { title, content, page_ids: selected })) })}>Preview export</button>
    {draft && <div className="knowledge-card">
      <pre className="knowledge-previous">{draft.markdown}</pre>
      <h3>Evidence to record</h3>
      <ul>{draft.pages.map((page) => <li key={page.id}>{page.title} · revision <code>{page.revision}</code>
        <ul>{page.sources.map((source) => <li key={source.id}>{source.source_url ?
          <a href={source.source_url} target="_blank" rel="noreferrer">{source.title ?? source.rel}</a> : source.rel}</li>)}</ul></li>)}</ul>
      <button className="primary" type="button" disabled={busy} onClick={() => void act(async () => {
        const result = await writeDeliverable<{ artifact_path: string }>(project, "export", { title, content, page_ids: selected, token: draft.token })
        setDraft(null); setTitle(""); setContent(""); setSelected([]); setMessage(`Saved locally: ${result.artifact_path}`)
        setItems((await fetchDeliverables(project)).items)
      })}>Save Markdown and evidence</button>
    </div>}
    {message && <p role="status">{message}</p>}
    <h3>Tracked deliverables</h3>
    <button className="ghost" type="button" disabled={busy} onClick={() => void act(async () => setItems((await fetchDeliverables(project)).items))}>Check source changes</button>
    {items.map((item) => <details key={item.id}>
      <summary>{item.title} · {item.status}</summary>
      <p><code>{item.artifact_path}</code></p>
      {item.reviews.length > 0 && <p className="quiet">Last acknowledged: {new Date(item.reviews[item.reviews.length - 1].at).toLocaleString()}</p>}
      <ul>{item.pages.map((page) => <li key={page.id}>{page.title} · {page.revision}: {page.sources.map((source) => source.rel).join(", ")}</li>)}</ul>
      {item.changes.length > 0 && <ul>{item.changes.map((change, index) => <li key={index}>{change.kind}: {change.label} — {change.status}</li>)}</ul>}
      {item.status === "needs review" && <button className="ghost" type="button" disabled={busy} onClick={() => void act(async () => {
        const updated = await writeDeliverable<DeliverableRecord>(project, `${encodeURIComponent(item.id)}/acknowledge`, { snapshot: item.snapshot })
        setItems((previous) => previous.map((entry) => entry.id === item.id ? updated : entry))
      })}>Acknowledge changes without altering export</button>}
    </details>)}
  </div>
}
