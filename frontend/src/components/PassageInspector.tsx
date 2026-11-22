import type { AskEvidence } from "../types"

export function PassageInspector({ item, available, changed }: { item: AskEvidence; available?: boolean; changed?: boolean }) {
  return <article className="knowledge-card passage-inspector">
    <strong>{item.label}</strong>
    <p className="quiet">{item.project_id}{item.page ? ` · PDF page ${item.page}` : ""}
      {item.derived ? " · derived, not independent evidence" : " · recorded search excerpt"}</p>
    {item.captured_at ? <p className="quiet">Captured: {item.captured_at}</p> : item.source_mtime ?
      <p className="quiet">File modified at indexing: {new Date(item.source_mtime * 1000).toLocaleString()}</p> : null}
    {available === false ? <p className="knowledge-warning">Source is not in the current index.</p> :
      (changed || item.stale) && <p className="knowledge-warning">Needs recheck. This is the recorded excerpt, not a fresh read.</p>}
    {item.excerpt ? <blockquote>{item.excerpt}</blockquote> : <p>No passage was recorded for this citation.</p>}
    {item.source_url && /^https?:\/\//i.test(item.source_url) && <a href={item.source_url} target="_blank" rel="noreferrer">Open original web source</a>}
  </article>
}
