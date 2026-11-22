import { useMemo, useState } from "react"
import type { FileRec } from "../types"

export function ProjectFlow({ files, onFile }: { files: FileRec[]; onFile: (id: string) => void }) {
  const [picked, setPicked] = useState("")
  const scripts = useMemo(() => files.filter((file) => ["python", "shell", "notebook"].includes(file.kind))
    .sort((a, b) => Number(!!b.workflow_refs?.length) - Number(!!a.workflow_refs?.length) ||
      Number(b.entry) - Number(a.entry) || a.rel.localeCompare(b.rel)), [files])
  const script = scripts.find((file) => file.id === picked) ?? scripts[0]
  const filesById = new Map(files.map((file) => [file.id, file]))
  function side(direction: "read" | "write") {
    const groups = new Map<string, number[]>()
    for (const ref of script?.workflow_refs ?? []) {
      if (ref.direction === direction && filesById.has(ref.file_id)) {
        groups.set(ref.file_id, [...new Set([...(groups.get(ref.file_id) ?? []), ref.line])])
      }
    }
    return [...groups].map(([id, lines]) => <button key={id} type="button" className="brain-diagram-card" onClick={() => onFile(id)}>
      <strong>{filesById.get(id)?.rel}</strong><small>Inferred · script {lines.length === 1 ? "line" : "lines"} {lines.join(", ")}</small>
    </button>)
  }
  const reads = side("read"), writes = side("write")
  const imports = script?.imports_local.filter((id) => filesById.has(id)) ?? []
  return <section className="brain-map-panel" aria-label="Project flow diagram">
    <header><div><h2>Project flow</h2><p className="quiet">Dashed arrows are possible reads and writes inferred from literal paths in Python. Nothing was run.</p></div>
      {!!script && <label>Workflow <select value={script.id} onChange={(event) => setPicked(event.target.value)}>
        {scripts.map((file) => <option key={file.id} value={file.id}>{file.rel}</option>)}</select></label>}
    </header>
    {!script ? <p>No scripts or notebooks are in this project's index.</p> : <>
      <div className="brain-flow-diagram">
        <div><h3>01 · Inputs</h3>{reads.length ? reads : <p className="quiet">No indexed input path identified.</p>}</div>
        <div className={`brain-flow-arrow${reads.length ? " linked" : ""}`} aria-hidden="true" />
        <div><h3>02 · Workflow</h3><button type="button" className="brain-diagram-card workflow" onClick={() => onFile(script.id)}>
          <strong>{script.rel}</strong><small>{script.entry ? "Likely entry point" : script.kind}</small></button></div>
        <div className={`brain-flow-arrow${writes.length ? " linked" : ""}`} aria-hidden="true" />
        <div><h3>03 · Outputs</h3>{writes.length ? writes : <p className="quiet">No indexed output path identified.</p>}</div>
      </div>
      {!!imports.length && <div className="brain-flow-imports"><strong>Indexed imports (not data flow)</strong>{imports.map((id) =>
        <button type="button" className="ghost" onClick={() => onFile(id)} key={id}>{filesById.get(id)?.rel}</button>)}</div>}
      <p className="quiet">Dynamic paths, absent outputs, shell I/O and notebook cell I/O are not resolved.</p>
    </>}
  </section>
}
