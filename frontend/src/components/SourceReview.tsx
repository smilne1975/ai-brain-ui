import { useState } from "react"
import { fetchSourceReview } from "../api"
import type { KnowledgeIndex } from "../types"

export function SourceReview({ project, index, load }: { project: string; index: KnowledgeIndex;
  load: (id: string, pageTopic?: string | null, sourceIds?: string[]) => Promise<void> }) {
  const [report, setReport] = useState<Awaited<ReturnType<typeof fetchSourceReview>>>()
  const [sourceId, setSourceId] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const source = report?.items.find((item) => item.source_id === sourceId) ?? report?.items[0]
  const affected = source?.affected.filter((item) => item.project_id === project) ?? []
  return <section className="knowledge-card" aria-label="Source impact review">
    <h3>Review what a source change affects</h3>
    <p className="quiet">Read-only plan for this project. A dependency is a reason to recheck, not a verdict that a claim is wrong. Nothing is applied together.</p>
    <button className="ghost" type="button" disabled={busy} onClick={async () => {
      setBusy(true); setError(""); setReport(undefined)
      try { setReport(await fetchSourceReview(project)) }
      catch (err) { setError(err instanceof Error ? err.message : "Could not check source changes.") }
      finally { setBusy(false) }
    }}>{busy ? "Checking…" : "Check source impact"}</button>
    {error && <p role="status">{error}</p>}
    {report?.limited && <p className="knowledge-warning">The scan has incomplete coverage. This report only follows recorded citations.</p>}
    {report && !source && <p>No changed dependencies found. Older followed questions may not have a recorded source version.</p>}
    {source && <>
      <label>Changed source <select value={source.source_id} onChange={(event) => setSourceId(event.target.value)}>
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
          </li>
        })}</ul>
      </div>
    </>}
  </section>
}
