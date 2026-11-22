import { useState } from "react"
import type { AskEvidence, FileRec, KnowledgeIndex, KnowledgePage, KnowledgeSource, TraceQuestion, TraceRecord } from "../types"

type Passage = { id: string; label: string; text?: string; url?: string; note: string; evidence?: AskEvidence }
type Artifact = { id: string; title: string; kind: string; detail: string; when?: string; passages: Passage[]; record?: TraceRecord }

function fromSearch(item: AskEvidence): Passage {
  return { id: item.id, label: `${item.label}${item.page ? ` · page ${item.page}` : ""}`, text: item.excerpt,
    url: item.source_url, evidence: item, note: item.stale ? "Recorded excerpt · source needs recheck" : "Recorded search excerpt · not a verdict" }
}

function fromSource(source: KnowledgeSource, stale: boolean, current: FileRec | undefined, historical = false): Passage {
  return { id: source.id, label: source.title || source.rel, url: source.source_url,
    text: !stale && !historical ? current?.excerpt : undefined,
    note: historical ? "Cited by the older revision · original excerpt not stored" : stale ? "Stored citation · source changed or unavailable" :
      current?.excerpt ? "Current indexed preview · not a claim-level quotation" : "Recorded citation · no excerpt available" }
}

export function BrainTrace({ focus, files, pages, savedAnswers, records, history, watches, ask, preferred, warning, onFocus, onFile, onMap }: {
  focus: string | null; files: FileRec[]; pages: KnowledgePage[]; records: TraceRecord[]; history: TraceRecord[]; watches: TraceQuestion[];
  savedAnswers: KnowledgeIndex["answers"];
  ask: { title: string; answer: string; evidence: AskEvidence[]; when?: string } | null; preferred?: string;
  warning?: string; onFocus: (id: string) => void; onFile: (id: string) => void;
  onMap: (item: AskEvidence, origin: string) => void
}) {
  const [picked, setPicked] = useState(preferred ?? "")
  const [selected, setSelected] = useState<{ artifact: string; key: string; passage: Passage } | null>(null)
  const byId = new Map(files.map((file) => [file.id, file]))
  const recordPassages = (record: TraceRecord, historical = false) => record.sources.map((src) =>
    fromSource(src, !!record.stale_sources?.includes(src.id), byId.get(src.id), historical))
  const artifacts: Artifact[] = [
    ...(ask ? [{ id: "ask", title: ask.title, kind: "Last Ask answer", detail: ask.answer, when: ask.when,
      passages: ask.evidence.filter((item) => !focus || item.project_id === focus).map(fromSearch) }] : []),
    ...savedAnswers.filter((item) => !focus || item.project_id === focus).map((item) => ({
      id: `saved:${item.project_id}:${item.name}`, title: item.name, kind: "Saved answer", detail: item.content.slice(0, 1200),
      passages: (item.passages ?? []).map(fromSearch) })),
    ...records.filter((row) => ["decision", "fact"].includes(row.kind)).map((row) => ({ id: `record:${row.id}`,
      title: row.title, kind: row.kind, detail: row.text, when: row.updated_at, passages: recordPassages(row), record: row })),
    ...watches.filter((row) => row.state === "following" && (!focus || row.scope.some((item) => item.id === focus))).map((row) => ({
      id: `watch:${row.id}`, title: row.question, kind: "Followed question", when: row.checked_at,
      detail: row.reviewed.incomplete || row.reviewed.missing_scopes ? "The last reviewed search had coverage gaps." : "Last reviewed search evidence.",
      passages: row.reviewed.items.filter((item) => !focus || item.project_id === focus).map(fromSearch) })),
    ...pages.filter((page) => !focus || page.project_id === focus).map((page) => ({ id: `knowledge:${page.page_id}`,
      title: page.title, kind: "Approved page", detail: page.content.slice(0, 1200), when: page.updated_at,
      passages: page.sources.map((src) => fromSource(src, page.stale_sources.includes(src.id), byId.get(src.id))) })),
  ]
  const artifact = artifacts.find((item) => item.id === picked) ?? artifacts[0]
  const row = artifact?.record
  const previous = row && history.find((item) => item.id === row.id && item.revision === row.revision - 1)
  const normalize = (text: string) => text.trim().toLowerCase().replace(/\s+/g, " ")
  const conflicting = row?.kind === "fact" && row.state === "confirmed" ? records.filter((other) =>
    other.id !== row.id && other.kind === "fact" && other.state === "confirmed" && normalize(other.title) === normalize(row.title) &&
    normalize(other.text) !== normalize(row.text)).slice(0, 3) : []
  function date(value: string) { return new Date(value).toLocaleString() }
  function passageCard(passage: Passage, relation: string, key: number) {
    const identity = `${passage.id}:${relation}:${key}`
    return <button key={identity} type="button" className={`brain-diagram-card${selected?.artifact === artifact.id && selected.key === identity ? " on" : ""}`}
      onClick={() => setSelected({ artifact: artifact.id, key: identity, passage })}><strong>{passage.label}</strong><small>{relation} · {passage.note}</small></button>
  }
  return <section className="brain-map-panel" aria-label="Evidence trail">
    <header><div><h2>Evidence trail</h2><p className="quiet">Follow recorded citations and decisions back to the source. A connection is not proof.</p></div>
      {!!artifact && <label>Trace <select value={artifact.id} onChange={(event) => { setPicked(event.target.value); setSelected(null) }}>
        {artifacts.map((item) => <option key={item.id} value={item.id}>{item.kind} · {item.title}</option>)}
      </select></label>}
    </header>
    {warning && <p role="status">{warning}</p>}
    {!focus && <p className="quiet">Focus a project to trace its reviewed decisions and recorded revisions.</p>}
    {!artifact ? <p>Ask a question, approve a knowledge page, or review a project decision to see its trail here.</p> : <>
      <div className="brain-trace-grid">
        <div className="brain-trace-origin"><small>{artifact.kind}{artifact.when ? ` · ${date(artifact.when)}` : ""}</small>
          <h3>{artifact.title}</h3><div className="brain-passage">{artifact.detail}</div></div>
        <div className="brain-trace-branches">
          <h3>{row?.state === "reviewed" || row?.state === "confirmed" ? "Recorded support" : "Cited or retrieved evidence"}</h3>
          {artifact.passages.length ? artifact.passages.map((passage, i) => passageCard(passage,
            row?.state === "reviewed" || row?.state === "confirmed" ? "Supports (recorded)" : "Cites", i)) : <p className="quiet">No source is recorded for this selection.</p>}
          {previous && <div className="brain-trace-branch supersedes"><h3>Supersedes revision {previous.revision}</h3><p className="quiet">{date(previous.updated_at)}</p>
            <div className="brain-passage">{previous.text}</div>{recordPassages(previous, true).map((p, i) => passageCard(p, "Older citation", i))}</div>}
          {conflicting.map((other) => <div key={other.id} className="brain-trace-branch conflict"><h3>May contradict</h3>
            <p className="quiet">Same confirmed subject, different wording · {date(other.updated_at)}. Check the context.</p>
            <div className="brain-passage">{other.text}</div>{recordPassages(other).map((p, i) => passageCard(p, "Other statement's source", i))}</div>)}
        </div>
      </div>
      {selected?.artifact === artifact.id && <aside className="brain-trace-inspector" aria-label="Selected evidence">
        <div><strong>{selected.passage.label}</strong><p className="quiet">{selected.passage.note}</p></div>
        <button type="button" className="ghost" onClick={() => setSelected(null)}>Close evidence</button>
        {selected.passage.text && <blockquote>{selected.passage.text}</blockquote>}
        {selected.passage.url && /^https?:\/\//i.test(selected.passage.url) && <a href={selected.passage.url} target="_blank" rel="noreferrer">Open original web source</a>}
        {byId.has(selected.passage.id) && <button type="button" className="ghost" onClick={() => onFile(selected.passage.id)}>Open current file preview</button>}
        {selected.passage.evidence && byId.has(selected.passage.id) && <button type="button" className="ghost"
          onClick={() => onMap(selected.passage.evidence!, artifact.title)}>Reveal this passage on map</button>}
        {selected.passage.evidence?.kind === "file" && !byId.has(selected.passage.id) && <p>Source is not in the current index.</p>}
      </aside>}
      {!focus && ask && <div className="brain-flow-imports">{[...new Set(ask.evidence.map((item) => item.project_id))].map((id) =>
        <button type="button" key={id} className="ghost" onClick={() => onFocus(id)}>Focus {id}</button>)}</div>}
    </>}
  </section>
}
