import { useEffect, useState } from "react"
import { fetchScanReplay } from "../api"
import type { Brain, KnowledgeIndex, ScanChange, ScanReplay, TraceRecord } from "../types"

const states = { added: "Newly indexed", changed: "Metadata changed", unlisted: "No longer indexed" } as const

export function BrainReplay({ brain, project, impacts, records, onFile, onKnowledge, onDecision }: {
  brain: Brain; project: string | null; impacts: KnowledgeIndex["source_impact"]; records: TraceRecord[];
  onFile: (id: string) => void; onKnowledge: (project: string) => void; onDecision: (id: string) => void
}) {
  const [picked, setPicked] = useState<number | null>(null)
  const [data, setData] = useState<ScanReplay | null>(null)
  const [error, setError] = useState("")
  const [filter, setFilter] = useState<ScanChange["state"] | "all">("all")
  const [busy, setBusy] = useState(true)
  useEffect(() => {
    if (brain.privacy) return
    const controller = new AbortController()
    void fetchScanReplay(project, picked, controller.signal).then((value) => {
      if (!controller.signal.aborted) { setData(value); setError(""); setBusy(false) }
    }).catch((reason: Error) => {
      if (!controller.signal.aborted) { setData(null); setError(reason.message); setBusy(false) }
    })
    return () => controller.abort()
  }, [project, picked, brain.scanned_at, brain.signature, brain.privacy])
  const frames = data?.frames ?? []
  const index = picked === null ? frames.length - 1 : frames.findIndex((row) => row.id === picked)
  const comparison = data?.comparison
  const changes = comparison?.changes ?? []
  const ids = new Set(brain.files.map((file) => file.id))
  const projects = new Map(brain.projects.map((row) => [row.id, row.name]))
  const date = (value: string) => new Date(value).toLocaleString()
  function choose(i: number) {
    if (i < 0 || i >= frames.length || i === index) return
    setBusy(true); setPicked(i === frames.length - 1 ? null : frames[i].id)
  }
  return <section className="brain-map-panel" aria-label="Scan replay" aria-busy={!brain.privacy && busy}>
    <header><div><h2>Change replay</h2><p className="quiet">Compare recorded snapshots of the file index. No activity is inferred between scans.</p></div></header>
    {brain.privacy || data?.disabled ? <p>Replay is unavailable while private-folder protection is active.</p> : error ?
      <p role="alert">{error} {picked !== null && <button type="button" className="ghost" onClick={() => { setBusy(true); setPicked(null) }}>Back to latest</button>}</p> :
      !frames.length ? <p role="status">{busy ? "Loading recorded scans…" : "No recorded scans yet. Rescan to establish a baseline."}</p> : <>
      <div className="brain-replay-controls">
        <button type="button" className="ghost" disabled={index <= 0} onClick={() => choose(index - 1)}>Earlier</button>
        <input aria-label="Recorded scan" aria-valuetext={frames[index] ? date(frames[index].at) : undefined} type="range"
          min={0} max={frames.length - 1} value={Math.max(0, index)} disabled={frames.length < 2}
          onChange={(event) => choose(Number(event.target.value))} />
        <button type="button" className="ghost" disabled={index >= frames.length - 1} onClick={() => choose(index + 1)}>Later</button>
      </div>
      <div className="brain-replay-axis" aria-hidden="true">{frames.map((frame, i) => <i className={i === index ? "on" : ""} key={frame.id} />)}</div>
      {busy ? <p role="status">Loading scan comparison…</p> : comparison && <>
        <p><strong>{comparison.before ? `${date(comparison.before)} → ` : "Baseline · "}{date(comparison.after)}</strong></p>
        {!comparison.before ? <p className="quiet">No older snapshot is retained before this one. Changes will be visible after a different scan is recorded.</p> : <>
          {comparison.incomplete && <p className="quiet">At least one scan hit the index limit. Missing entries may reflect incomplete coverage.</p>}
          <div className="brain-replay-counts" aria-label="Change filters">
            <button type="button" className={filter === "all" ? "on" : ""} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All changes</button>
            {(Object.keys(states) as (keyof typeof states)[]).map((state) => <button key={state} type="button" className={`${state}${filter === state ? " on" : ""}`}
              aria-pressed={filter === state} onClick={() => setFilter(state)}><b>{changes.filter((row) => row.state === state).length}</b> {states[state]}</button>)}
          </div>
          <ul className="brain-replay-list">{changes.filter((row) => filter === "all" || row.state === filter).map((row) => {
            const affected = row.state === "added" ? [] : impacts.find((item) => item.source_id === row.id)?.affected ?? []
            const decisions = row.state === "added" ? [] : records.filter((rec) => rec.kind === "decision" && rec.stale_sources?.includes(row.id))
            return <li key={row.id} className={row.state}><span>{states[row.state]}</span>
              <div>{ids.has(row.id) ? <button type="button" className="ghost" onClick={() => onFile(row.id)}>{row.rel}</button> : <strong>{row.rel}</strong>}
                {!project && <small>{projects.get(row.project_id) ?? row.project_id}</small>}
                {(affected.length > 0 || decisions.length > 0) && <div className="brain-flow-imports"><small>Needs review now</small>
                  {affected.map((item) => <button key={`${item.kind}:${item.id}`} type="button" className="ghost" onClick={() => onKnowledge(item.project_id)}>{item.kind} · {item.label}</button>)}
                  {decisions.map((item) => <button key={item.id} type="button" className="ghost" onClick={() => onDecision(item.id)}>Decision · {item.title}</button>)}
                </div>}
              </div></li>
          })}</ul>
          {!changes.some((row) => filter === "all" || row.state === filter) && <p>No changes in this selection.</p>}
          {!!comparison.omitted && <p className="quiet">{comparison.omitted} more changes omitted. Focus a project to narrow the results.</p>}
          <p className="quiet">Changes use observed modification time and size, not content history. No longer indexed does not prove a file was deleted. Review badges use today's citations{project ? "." : "; focus a project to include its decisions."}</p>
        </>}
      </>}
    </>}
  </section>
}
