import { useMemo, useRef, useState } from "react"
import { folderScopes, searchFiles } from "../graphInventory"
import type { FileRec } from "../types"

const PAGE = 30

export function GraphFileFinder({ files, project, folder, revealed, onFolder, onReveal, onBack, onOpen, shownFiles, omittedNodes,
  omittedLinks, hiddenNeighbors, truncated, coverageNote }: {
  files: FileRec[]; project: string; folder: string | null; revealed: FileRec | undefined;
  onFolder: (folder: string | null) => void; onReveal: (file: FileRec) => void; onBack: () => void; onOpen: (id: string) => void;
  shownFiles: number; omittedNodes: number; omittedLinks: number; hiddenNeighbors: number; truncated: boolean; coverageNote: boolean
}) {
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const results = useMemo(() => searchFiles(files, query), [files, query])
  const scopes = useMemo(() => folderScopes(files), [files])
  const pages = Math.max(1, Math.ceil(results.length / PAGE))
  const currentPage = Math.min(page, pages - 1)
  function choose(file: FileRec) {
    onReveal(file); setOpen(false); input.current?.focus()
  }
  const label = folder === null ? "All folders" : folder || "Project root"
  return <section className="graph-inventory" aria-label="Indexed files on the map" onKeyDown={(event) => {
    if (event.key === "Escape" && open) { event.stopPropagation(); setOpen(false); input.current?.focus() }
  }}>
    <div className="graph-inventory-row">
      <label className="graph-search-label">Find indexed file <input ref={input} type="search" value={query} placeholder="Name or path, including hidden files"
        onClick={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setPage(0); setOpen(true) }}
        onKeyDown={(event) => {
          if (event.key === "Enter") { event.preventDefault(); if (open && results.length) choose(results[0]); else setOpen(true) }
        }} /></label>
      <button type="button" className="ghost" aria-expanded={open} aria-controls="graph-file-results" onClick={() => {
        setOpen(!open); if (!open) input.current?.focus()
      }}>{open ? "Close file list" : "Browse indexed files"}</button>
      <label>Show folder <select aria-label="Solo graph folder" value={folder === null ? "all:" : `folder:${folder}`}
        onChange={(event) => { setOpen(false); onFolder(event.target.value === "all:" ? null : event.target.value.slice(7)) }}>
        <option value="all:">All folders</option>
        {scopes.map(([path, count]) => <option key={path} value={`folder:${path}`}>{path || "Project root"} ({count})</option>)}
      </select></label>
      <span className="quiet" role="status">{shownFiles} of {files.length} indexed files displayed{omittedNodes ? ` · ${omittedNodes} eligible ${omittedNodes === 1 ? "node" : "nodes"} over display limit` : ""}
        {omittedLinks ? ` · ${omittedLinks} links not drawn` : ""}</span>
    </div>
    {(revealed || folder !== null) && <div className="graph-inventory-row graph-breadcrumb" aria-label="Map location">
      <button type="button" className="ghost" onClick={onBack}>{revealed ? "Back to previous map" : "Back to all folders"}</button>
      <span>{project} <span aria-hidden="true">›</span> {label}</span>
      {revealed && <>
        <strong>{revealed.name}</strong><button type="button" className="ghost" onClick={() => onOpen(revealed.id)}>Open file preview</button>
        <span className="quiet">Showing the selected file and linked context even outside folder or kind filters.{hiddenNeighbors ? ` ${hiddenNeighbors} direct neighbours exceed the display limit.` : ""}</span>
      </>}
    </div>}
    {(truncated || coverageNote) && <p className="quiet graph-coverage">Scan coverage is separate: {truncated ? "a scan limit was reached; " : ""}
      {coverageNote ? "some files were skipped or not fully read. " : ""}See Scan coverage in Knowledge.</p>}
    {open && <div id="graph-file-results" className="graph-file-results" aria-label="Indexed file search results">
      <p className="quiet" role="status">{results.length} of {files.length} indexed files match · search covers all folders and kinds in this project.</p>
      {results.length ? <ul>{results.slice(currentPage * PAGE, (currentPage + 1) * PAGE).map((file) => <li key={file.id}>
        <button type="button" className="ghost" aria-label={`Reveal ${file.rel}`} onClick={() => choose(file)}>
          <strong>{file.rel}</strong><small>{file.kind}</small>
        </button>
      </li>)}</ul> : <p>No matching indexed files.</p>}
      {pages > 1 && <div className="graph-inventory-row"><button type="button" className="ghost" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Previous files</button>
        <span className="quiet">Page {currentPage + 1} of {pages}</span>
        <button type="button" className="ghost" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>Next files</button></div>}
    </div>}
  </section>
}
