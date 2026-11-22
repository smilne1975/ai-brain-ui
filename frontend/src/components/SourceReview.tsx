import { useState } from "react"
import { fetchSourceReview, previewSourceGroup, saveSourceGroup, type SourceGroup } from "../api"
import type { KnowledgeIndex } from "../types"

export function SourceReview({ project, index, load, onSaved }: { project: string; index: KnowledgeIndex;
  load: (id: string, pageTopic?: string | null, sourceIds?: string[]) => Promise<void>; onSaved: () => void }) {
  const [report, setReport] = useState<Awaited<ReturnType<typeof fetchSourceReview>>>()
  const [sourceId, setSourceId] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [picked, setPicked] = useState<string[]>([])
  const [plan, setPlan] = useState<SourceGroup>()
  const [read, setRead] = useState(false)
  const [message, setMessage] = useState("")
  const source = report?.items.find((item) => item.source_id === sourceId) ?? report?.items[0]
  const affected = source?.affected.filter((item) => item.project_id === project) ?? []
  return <section className="knowledge-card" aria-label="Source impact review">
    <h3>Review what a source change affects</h3>
    <p className="quiet">A dependency is a reason to recheck, not a verdict that a claim is wrong. Decisions, questions, and saved answers are recheck-only. Approved pages can be refreshed together only after reviewing their exact changes.</p>
    <button className="ghost" type="button" disabled={busy} onClick={async () => {
      setBusy(true); setError(""); setMessage(""); setReport(undefined); setPlan(undefined); setPicked([]); setRead(false)
      try { setReport(await fetchSourceReview(project)) }
      catch (err) { setError(err instanceof Error ? err.message : "Could not check source changes.") }
      finally { setBusy(false) }
    }}>{busy ? "Checking…" : "Check source impact"}</button>
    {error && <p role="status">{error}</p>}
    {message && <p role="status">{message}</p>}
    {report?.limited && <p className="knowledge-warning">The scan has incomplete coverage. This report only follows recorded citations.</p>}
    {report && !source && <p>No changed dependencies found. Older followed questions may not have a recorded source version.</p>}
    {source && <>
      <label>Changed source <select value={source.source_id} disabled={busy} onChange={(event) => {
        setSourceId(event.target.value); setPlan(undefined); setRead(false); setPicked([]); setError(""); setMessage("")
      }}>
        {report?.items.map((item) => <option key={item.source_id} value={item.source_id}>{item.rel} · {item.status}</option>)}
      </select></label>
      <div className="brain-trace-grid"><div className="brain-trace-origin"><strong>{source.rel}</strong><p>{source.status}</p></div>
        <ul className="brain-trace-branches">{affected.map((item) => {
          const page = item.kind === "page" ? index.pages.find((entry) => entry.page_id === item.id) : undefined
          return <li className="brain-trace-branch" key={`${item.kind}:${item.id}`}><strong>{item.label}</strong>
            <p className="quiet">{item.kind}: {page ? "Recorded page citation · draft can be previewed" : "Recorded source · recheck only"}</p>
            {item.passage && <blockquote>{item.passage}</blockquote>}
            {page && <button className="ghost" type="button" onClick={() => void load(page.project_id, page.topic,
              page.sources.map((entry) => entry.id === source.source_id && item.move ? item.move.id : entry.id))}>
              {item.move ? `Preview verified move to ${item.move.rel}` : "Preview individual page update"}</button>}
            {page && <label><input type="checkbox" checked={picked.includes(page.page_id)} disabled={busy || (picked.length >= 8 && !picked.includes(page.page_id))}
              onChange={(event) => {
                setPlan(undefined); setRead(false); setError(""); setMessage("")
                setPicked((prior) => event.target.checked ? [...prior, page.page_id] : prior.filter((id) => id !== page.page_id))
              }} /> Include {page.title} in the grouped preview</label>}
          </li>
        })}</ul>
      </div>
      {affected.some((item) => item.kind === "page") && <button type="button" className="ghost" disabled={busy || !picked.length}
        onClick={async () => {
          setBusy(true); setPlan(undefined); setRead(false); setError(""); setMessage("")
          try { setPlan(await previewSourceGroup(project, source.source_id, picked)) }
          catch (err) { setError(err instanceof Error ? err.message : "Could not preview grouped changes.") }
          finally { setBusy(false) }
        }}>Preview grouped page updates</button>}
      {plan && <div className="knowledge-card" aria-label="Grouped page update preview">
        <h4>Review {plan.targets.length} proposed revision(s)</h4>
        <p>These are regenerated drafts. If a change would remove writing you want to keep, use the individual page editor instead. This plan never changes the source files.</p>
        {plan.targets.map((target) => <details key={target.id}>
          <summary>{target.title} — exact text changes</summary>
          <pre className="knowledge-previous">{target.diff || "No text changes; source references will be refreshed."}</pre>
          {target.findings.map((item, index) => <p key={index} className="knowledge-warning">Review warning: {item.detail}</p>)}
        </details>)}
        <label><input type="checkbox" checked={read} disabled={busy} onChange={(event) => setRead(event.target.checked)} /> I reviewed every change and warning above</label>{" "}
        <button type="button" className="primary" disabled={busy || !read} onClick={async () => {
          setBusy(true); setError(""); setMessage("")
          try {
            const saved = await saveSourceGroup(project, plan)
            setPlan(undefined); setRead(false); setPicked([]); setReport(undefined)
            setMessage(`Saved all ${saved.saved} reviewed revisions. Original sources are unchanged.`); onSaved()
          } catch (err) { setPlan(undefined); setRead(false); setError(err instanceof Error ? err.message : "Could not save grouped changes.") }
          finally { setBusy(false) }
        }}>Approve all selected revisions</button>
      </div>}
    </>}
  </section>
}
