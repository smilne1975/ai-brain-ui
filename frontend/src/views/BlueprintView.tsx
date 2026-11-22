import { lazy, Suspense, useEffect, useMemo, useState } from "react"
import { ask, fetchKnowledge, fetchTraceQuestions, fetchTraceRecords, saveAnswer } from "../api"
import { BrainReplay } from "../components/BrainReplay"
import { BrainTrace } from "../components/BrainTrace"
import { FlowGraph } from "../components/FlowGraph"
import { GraphFileFinder } from "../components/GraphFileFinder"
import { ProjectFlow } from "../components/ProjectFlow"
import { QuestionWorkbench } from "../components/QuestionWorkbench"
import { containingFolder, sliceProjectGraph } from "../graphInventory"
import type { AskResponse, Brain, FileRec, GraphNode, KnowledgeIndex, Selection, TraceQuestion, TraceRecord } from "../types"

type Props = {
  brain: Brain
  query: string
  focus: string | null
  onFocus: (id: string | null) => void
  onSelect: (selection: Selection) => void
  onOpenKnowledge: (projectId: string) => void
}

const Graph3D = lazy(() => import("../components/Graph3D").then((module) => ({ default: module.SafeGraph3D })))
type MapMode = "explore" | "trace" | "replay" | "flow"
const MODES: [MapMode, string][] = [["explore", "Explore"], ["trace", "Trace"], ["replay", "Replay"], ["flow", "Project flow"]]
const EMPTY_RECORDS: TraceRecord[] = []

const FILTERS: { id: string; label: string; kinds: Set<string> | null }[] = [
  { id: "all", label: "All", kinds: null },
  { id: "scripts", label: "Scripts", kinds: new Set(["project", "entry", "script", "tool", "store", "keyin", "function"]) },
  { id: "notes", label: "Notes", kinds: new Set(["project", "note", "model"]) },
  { id: "decisions", label: "Decisions & questions", kinds: new Set(["project", "decision", "question", "entry", "script"]) },
  { id: "services", label: "Services", kinds: new Set(["project", "service"]) },
  { id: "config", label: "Config", kinds: new Set(["project", "workspace", "workset", "pcf", "variable", "cfg", "script"]) },
]

export function BlueprintView({ brain, query, focus, onFocus, onSelect, onOpenKnowledge }: Props) {
  const [filter, setFilter] = useState("all")
  const [draft, setDraft] = useState("")
  const [pending, setPending] = useState(false)
  const [reply, setReply] = useState<AskResponse | null>(null)
  const [lastAsked, setLastAsked] = useState<{ question: string; project_ids: string[] } | null>(null)
  const [askError, setAskError] = useState("")
  const [dimension, setDimension] = useState<"2d" | "3d">("2d")
  const [mode, setMode] = useState<MapMode>("explore")
  const [clusterSelection, setClusterSelection] = useState<{ project: string | null; id: string } | null>(null)
  const [folderScope, setFolderScope] = useState<{ project: string | null; path: string | null } | null>(null)
  const [revealed, setRevealed] = useState<{ project: string | null; id: string } | null>(null)
  const [traceTarget, setTraceTarget] = useState<string>()
  const [traceRevision, setTraceRevision] = useState(0)
  const [askedAt, setAskedAt] = useState<string>()
  const [links, setLinks] = useState("all")
  const [saved, setSaved] = useState("")
  const [selectedProjects, setSelectedProjects] = useState<string[]>([])
  const [knowledge, setKnowledge] = useState<KnowledgeIndex | null>(null)
  const [questions, setQuestions] = useState<TraceQuestion[]>([])
  const [board, setBoard] = useState<{ project: string; items: TraceRecord[]; history: TraceRecord[] } | null>(null)
  const [questionsWarning, setQuestionsWarning] = useState("")
  const [boardWarning, setBoardWarning] = useState<{ project: string; text: string } | null>(null)
  const knowledgePages = knowledge?.pages
  const records = !brain.privacy && focus && board?.project === focus ? board.items : EMPTY_RECORDS
  const history = !brain.privacy && focus && board?.project === focus ? board.history : EMPTY_RECORDS
  const projectFiles = useMemo(() => focus ? brain.files.filter((file) => file.project_id === focus) : [], [brain.files, focus])
  const revealedFile = revealed?.project === focus ? projectFiles.find((file) => file.id === revealed.id) : undefined
  const previousFolder = folderScope?.project === focus ? folderScope.path : null
  const visibleFolder = revealedFile ? containingFolder(revealedFile.rel) : previousFolder

  useEffect(() => {
    let active = true
    void fetchKnowledge().then((data) => { if (active) setKnowledge(data) }).catch(() => { if (active) setKnowledge(null) })
    return () => { active = false }
  }, [brain.scanned_at, brain.signature, brain.privacy])

  useEffect(() => {
    if (brain.privacy) return
    const controller = new AbortController()
    void fetchTraceQuestions(controller.signal).then(({ items }) => {
      if (!controller.signal.aborted) { setQuestions(items); setQuestionsWarning("") }
    }).catch((error: Error) => { if (!controller.signal.aborted) { setQuestions([]); setQuestionsWarning(error.message) } })
    return () => controller.abort()
  }, [brain.privacy, brain.scanned_at, brain.signature, traceRevision])

  useEffect(() => {
    if (!focus || brain.privacy) return
    const controller = new AbortController()
    void fetchTraceRecords(focus, controller.signal).then((value) => {
      if (!controller.signal.aborted) { setBoard({ ...value, project: focus }); setBoardWarning(null) }
    }).catch((error: Error) => { if (!controller.signal.aborted) { setBoard(null); setBoardWarning({ project: focus, text: error.message }) } })
    return () => controller.abort()
  }, [focus, brain.privacy, brain.scanned_at, brain.signature])

  const graph = focus ? brain.architecture.projects[focus] : brain.architecture.corpus
  const activeFilter = FILTERS.find((item) => item.id === filter) ?? FILTERS[0]

  const flow = useMemo(() => {
    const rootsOnly = dimension === "3d" && !focus
    const sourceNodes = (graph?.nodes ?? []).filter((node) => (!rootsOnly || node.kind === "project" || node.kind === "service") &&
      (focus || !activeFilter.kinds || activeFilter.kinds.has(node.kind)))
    const extraEdges: { id: string; source: string; target: string; label: string }[] = []
    const projectNode = sourceNodes.find((node) => node.kind === "project" && node.project_id === focus)
    if (focus && projectNode) {
      const fileNodes = new Map<string, GraphNode>()
      for (const node of sourceNodes) if (node.file_id && node.kind !== "decision" &&
        (!fileNodes.has(node.file_id) || node.id === `n:${node.file_id}`)) fileNodes.set(node.file_id, node)
      for (const file of projectFiles) {
        const kind = file.entry ? "entry" : ["python", "shell", "notebook"].includes(file.kind) ? "script" :
          ["config", "env"].includes(file.kind) ? "config" : "note"
        if (fileNodes.has(file.id)) continue
        const node = { id: `n:${file.id}`, label: file.title || file.name, sub: file.rel, kind, file_id: file.id,
          project_id: focus, service_id: null }
        if (sourceNodes.some((item) => item.id === node.id)) continue
        sourceNodes.push(node); fileNodes.set(file.id, node)
        extraEdges.push({ id: `cluster:${file.id}`, source: projectNode.id, target: node.id, label: "contains" })
      }
      for (const file of projectFiles) for (const target of file.imports_local) {
        const from = fileNodes.get(file.id), to = fileNodes.get(target)
        if (from && to) extraEdges.push({ id: `e:imp:${file.id}:${target}`, source: from.id, target: to.id, label: "imports" })
      }
      for (const file of projectFiles) for (const ref of file.workflow_refs ?? []) {
        const script = fileNodes.get(file.id), asset = fileNodes.get(ref.file_id)
        if (script && asset) extraEdges.push({ id: `workflow:${file.id}:${ref.file_id}:${ref.direction}:${ref.line}`,
          source: ref.direction === "read" ? asset.id : script.id, target: ref.direction === "read" ? script.id : asset.id,
          label: `${ref.direction === "read" ? "Reads" : "Writes"} · script line ${ref.line}` })
      }
      for (const [prefix, kind, rows] of [["record", "decision", records.filter((row) => row.kind === "decision")],
        ["watch", "question", !brain.privacy ? questions.filter((row) => row.state === "following" && row.scope.some((scope) => scope.id === focus)) : []]] as const) {
        for (const row of rows.slice(0, 25)) {
          const id = `${prefix}:${row.id}`
          sourceNodes.unshift({ id, label: "title" in row ? row.title : row.question, sub: kind === "decision" ? "Reviewed decision" : "Followed question",
            kind, project_id: focus, file_id: null, service_id: null })
          extraEdges.push({ id: `knowledge-root:${id}`, source: projectNode.id, target: id, label: kind })
          for (const item of "sources" in row ? row.sources : row.reviewed.items) {
            const node = fileNodes.get(item.id)
            if (node) extraEdges.push({ id: `knowledge-cite:${node.id}:${id}`, source: node.id, target: id, label: "cites" })
          }
        }
      }
    }
    const pageNodes = (knowledgePages ?? []).filter((page) => !rootsOnly && (!focus || page.project_id === focus) &&
      (focus || !activeFilter.kinds || activeFilter.kinds.has("note"))).map((page) => ({
        id: `knowledge:${page.page_id}`, label: `${page.title} knowledge`, sub: page.stale_sources.length ? "Needs recheck" : "Approved page",
        kind: "note", project_id: page.project_id, file_id: null, service_id: null,
      }))
    sourceNodes.push(...pageNodes)
    const ids = new Set(sourceNodes.map((node) => node.id))
    const sourceEdges = (graph?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    const edgeIds = new Set(sourceEdges.map((edge) => edge.id))
    for (const edge of extraEdges) if (!edgeIds.has(edge.id)) { sourceEdges.push(edge); edgeIds.add(edge.id) }
    for (const page of knowledgePages ?? []) {
      if (!ids.has(`knowledge:${page.page_id}`)) continue
      const projectNode = (graph?.nodes ?? []).find((node) => node.kind === "project" && node.project_id === page.project_id)
      if (projectNode && ids.has(projectNode.id)) sourceEdges.push({ id: `knowledge-edge:${page.page_id}`, source: projectNode.id,
        target: `knowledge:${page.page_id}`, label: "knowledge" })
      for (const source of page.sources) {
        const fileNode = sourceNodes.find((node) => node.file_id === source.id && node.kind !== "decision")
        if (fileNode && ids.has(fileNode.id)) sourceEdges.push({ id: `knowledge-source:${page.page_id}:${source.id}`,
          source: fileNode.id, target: `knowledge:${page.page_id}`, label: "cites" })
      }
    }
    return { nodes: sourceNodes, edges: sourceEdges.filter((edge) => {
      const kind = /^(e:svc:|e:svcroot:|workflow:)/.test(edge.id) || edge.label === "mentions" ? "inferred" :
        edge.id.startsWith("knowledge-") ? "knowledge" : "indexed"
      return links === "all" || (links === kind)
    }) }
  }, [graph, activeFilter, knowledgePages, focus, links, dimension, projectFiles, records, questions, brain.privacy])
  const revealedNode = revealedFile && (flow.nodes.find((node) => node.id === `n:${revealedFile.id}`) ??
    flow.nodes.find((node) => node.file_id === revealedFile.id && node.kind !== "decision"))
  const selectedNodeId = revealedNode?.id ?? (clusterSelection?.project === focus && flow.nodes.some((node) => node.id === clusterSelection.id)
    ? clusterSelection.id : null)
  const projectSlice = useMemo(() => focus ? sliceProjectGraph(flow, projectFiles, visibleFolder, activeFilter.kinds, selectedNodeId) : null,
    [focus, flow, projectFiles, visibleFolder, activeFilter, selectedNodeId])
  const drawn = projectSlice ?? flow
  const accessibleNodes = drawn.nodes.filter((node) => `${node.label} ${node.sub || ""}`.toLowerCase().includes(query.trim().toLowerCase()))
  function revealFile(file: FileRec) { setRevealed({ project: focus, id: file.id }); setClusterSelection(null) }
  function clearSelection() { setRevealed(null); setClusterSelection(null) }
  function showTrace(id: string) { setTraceTarget(id); setMode("trace") }
  function selectNode(node: GraphNode) {
    if (mode === "explore" && (focus || dimension === "3d")) {
      const file = revealedFile && projectFiles.find((item) => item.id === node.file_id)
      if (file) revealFile(file)
      else { setRevealed(null); setClusterSelection({ project: focus, id: node.id }) }
    }
    if (node.id.startsWith("watch:") || node.id.startsWith("record:")) showTrace(node.id)
    else if (node.id.startsWith("knowledge:") && node.project_id) {
      if (focus || dimension === "3d") showTrace(node.id)
      else onOpenKnowledge(node.project_id)
    }
    else openNode(node, focus, onFocus, onSelect)
  }

  const suggestions = focus
    ? [
        `What does ${brain.projects.find((project) => project.id === focus)?.name ?? "this folder"} actually do?`,
        `How is ${brain.projects.find((project) => project.id === focus)?.name ?? "this folder"} wired?`,
        "What is still unfinished?",
      ]
    : brain.suggestions

  async function submit(question: string) {
    const text = question.trim()
    if (!text || pending) return
    setDraft(text)
    setPending(true)
    setAskError("")
    setSaved("")
    try {
      const result = await ask(text, focus, focus ? undefined : selectedProjects)
      setReply(result)
      setAskedAt(brain.scanned_at)
      setLastAsked(result.scope?.length ? { question: text, project_ids: result.scope } : null)
    } catch (error) {
      setReply(null)
      setLastAsked(null)
      setAskError(error instanceof Error ? error.message : "The question could not be answered.")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="view with-ask">
      <div id="brain-map" className={`viz flow-viz${mode !== "explore" ? " brain-panel-viz" : focus ? " graph-inventory-viz" : ""}`}>
        <div className="bp-toolbar">
          <button type="button" className={!focus ? "on" : ""} onClick={() => onFocus(null)}>
            All folders
          </button>
          {brain.projects.map((project) => (
            <button
              key={project.id}
              type="button"
              className={focus === project.id ? "on" : ""}
              onClick={() => onFocus(project.id)}
            >
              {project.name}
            </button>
          ))}
        </div>
        <div className="bp-toolbar brain-mode-nav" role="group" aria-label="Brain map mode">
          {MODES.map(([id, label]) => <button key={id} type="button" className={mode === id ? "on" : ""} aria-pressed={mode === id}
            onClick={() => { setTraceTarget(undefined); setMode(id) }}>{label}</button>)}
        </div>
        {mode === "explore" && <><div className="bp-toolbar">
          <button type="button" aria-pressed={dimension === "2d"} className={dimension === "2d" ? "on" : ""} onClick={() => setDimension("2d")}>2D</button>
          <button type="button" aria-pressed={dimension === "3d"} className={dimension === "3d" ? "on" : ""} onClick={() => setDimension("3d")}>3D</button>
          <span className="toolbar-gap" />
          {FILTERS.map((item) => (
            <button key={item.id} type="button" aria-pressed={filter === item.id} className={filter === item.id ? "on" : ""} onClick={() => setFilter(item.id)}>
              {item.label}
            </button>
          ))}
          <label>Links <select aria-label="Graph link type" value={links} onChange={(event) => setLinks(event.target.value)}>
            <option value="all">All</option><option value="indexed">Indexed</option><option value="knowledge">Knowledge citations</option>
            <option value="inferred">Inferred references</option>
          </select></label>
        </div>
        {focus && projectSlice && <GraphFileFinder key={focus} files={projectFiles}
          project={brain.projects.find((item) => item.id === focus)?.name ?? focus}
          folder={visibleFolder} revealed={revealedFile} onReveal={revealFile} onFolder={(path) => {
            clearSelection(); setFolderScope({ project: focus, path })
          }} onBack={() => {
            clearSelection(); if (!revealedFile) setFolderScope(null)
          }} onOpen={(id) => onSelect({ kind: "file", id })} shownFiles={projectSlice.shownFiles}
          omittedNodes={projectSlice.omittedNodes} omittedLinks={projectSlice.omittedLinks} hiddenNeighbors={projectSlice.hiddenNeighbors}
          truncated={brain.truncated} coverageNote={!!brain.coverage?.issues.some((issue) => issue.project_id === focus)} />}
        <div className="flow-canvas">
          {dimension === "3d" ? <Suspense fallback={<p className="quiet">Loading 3D graph...</p>}><Graph3D nodes={drawn.nodes} edges={drawn.edges} query={query}
            scope={focus} selectedId={selectedNodeId} fitNodeId={revealedNode?.id}
            onClear={clearSelection} onNodeClick={selectNode}
            fallback={<div className="brain-map-panel" role="status">The 3D renderer is unavailable. Switch to 2D or use the keyboard list below.</div>} /></Suspense> : <FlowGraph
            key={JSON.stringify([focus, filter, links, visibleFolder, revealedNode?.id])}
            nodes={drawn.nodes}
            edges={drawn.edges}
            query={query}
            selectedId={selectedNodeId} fitNodeId={revealedNode?.id}
            onNodeClick={selectNode}
          />}
        </div>
        {dimension === "3d" && <div className="brain-map-caption"><strong>{focus ? brain.projects.find((item) => item.id === focus)?.name : "Project constellation"}</strong>
          <span>{focus ? "Select a file to preview it and highlight its neighbours." : "Choose a project hub on the map or above to reveal its files."}</span></div>}
        </>}
        {mode === "trace" && <BrainTrace key={`${focus ?? "all"}:${traceTarget ?? "pick"}:${brain.signature ?? brain.scanned_at}`}
          focus={focus} files={brain.files} pages={knowledgePages ?? []} records={records} history={history}
          watches={brain.privacy ? [] : questions} preferred={traceTarget}
          warning={(boardWarning?.project === focus ? boardWarning?.text : "") || (!brain.privacy ? questionsWarning : "")}
          ask={reply && lastAsked && (!focus || lastAsked.project_ids.includes(focus)) ? { title: lastAsked.question, answer: reply.answer,
            when: askedAt, evidence: reply.evidence ?? [] } : null} onFocus={onFocus} onFile={(id) => onSelect({ kind: "file", id })} />}
        {mode === "replay" && <BrainReplay key={focus ?? "all"} brain={brain} project={focus} impacts={knowledge?.source_impact ?? []} records={records}
          onFile={(id) => onSelect({ kind: "file", id })} onKnowledge={onOpenKnowledge} onDecision={(id) => showTrace(`record:${id}`)} />}
        {mode === "flow" && (focus ? <ProjectFlow key={focus} files={projectFiles} onFile={(id) => onSelect({ kind: "file", id })} /> :
          <section className="brain-map-panel" aria-label="Project flow diagram"><h2>Project flow</h2><p>Choose a project above to see its inputs, workflows and outputs.</p></section>)}
      </div>
      {mode === "explore" && <><h1 className="stage-title">blueprint</h1>
      <details className="knowledge-card" aria-label="Graph nodes keyboard list">
        <summary>Browse graph nodes as a list ({accessibleNodes.length})</summary>
        {accessibleNodes.slice(0, 250).map((node) => <button key={node.id} type="button" className="ghost" onClick={() => selectNode(node)}>
          {node.label} · {node.kind}</button>)}
        {accessibleNodes.length > 250 && <p className="quiet">Showing the first 250 nodes. Narrow your project, node type, or search.</p>}
      </details></>}
      <form
        className="ask"
        onSubmit={(event) => {
          event.preventDefault()
          void submit(draft)
        }}
      >
        {reply && (
          <div className="ask-answer">
            <p>{reply.answer}</p>
            <div className="cite-row">
              <span className="quiet">{reply.provider === "heuristic" ? "Local index" : reply.provider}</span>
              {!!reply.evidence?.length && <button type="button" className="ghost" onClick={() => {
                showTrace("ask"); document.getElementById("brain-map")?.scrollIntoView({ block: "start" })
              }}>Trace this answer</button>}
              {reply.citations.map((cite) => (
                <button key={cite.id} type="button" onClick={() => onSelect({ kind: "file", id: cite.id })}>
                  {cite.label}
                </button>
              ))}
            </div>
            {reply.incomplete && <p className="quiet">The scan hit its file cap; other files may hold more evidence.</p>}
            {reply.hybrid_warning && <p className="quiet">{reply.hybrid_warning}</p>}
            {!!reply.external_note_warnings?.length && <details><summary>Local note search coverage</summary>
              {reply.external_note_warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details>}
            {brain.coverage && Object.values(brain.coverage.counts).some((count) => count > 0) &&
              <p className="quiet">Some files were skipped or not fully read. See Scan coverage in Knowledge.</p>}
            {!!reply.pdf_gaps?.length && <details className="ask-evidence">
              <summary>{reply.pdf_gaps.length} PDF(s) not fully indexed</summary>
              {reply.pdf_gaps.map((item) => <button key={item.id} type="button"
                onClick={() => onSelect({ kind: "file", id: item.id })}>{item.label} — {item.reason}</button>)}
            </details>}
            {reply.evidence?.length ? <div className="ask-evidence">
              <strong>Evidence from {new Set(reply.evidence.map((item) => item.project_id)).size} project(s)</strong>
              <p className="quiet">Different links are not necessarily independent sources.</p>
              {reply.evidence.map((item) => <div key={`${item.id}:${item.page ?? ""}`}>
                {item.source_url ? <p><a href={item.source_url} target="_blank" rel="noreferrer">{item.label}</a> — {item.excerpt}</p>
                  : <button type="button" onClick={() => item.kind === "file" ? onSelect({ kind: "file", id: item.id }) : onFocus(item.project_id)}>
                    {item.label}{item.stale ? " · needs recheck" : ""}{item.semantic ? " · local similarity" : ""}{item.derived ? " · derived, not independent evidence" : ""} — {item.excerpt}
                  </button>}
                {!!item.repeated_count && <details><summary>{item.repeated_count} related citation(s) grouped · {item.evidence_basis?.join(", ")}</summary>
                  {item.confirmed_origin && <p>Recorded original: <a href={item.confirmed_origin} target="_blank" rel="noreferrer">{item.confirmed_origin}</a></p>}
                  {item.repeated_sources?.map((copy) => <p key={`${copy.id}:${copy.page ?? ""}`}>
                    {copy.source_url ? <a href={copy.source_url} target="_blank" rel="noreferrer">{copy.label}</a> : <button type="button"
                      onClick={() => onSelect({ kind: "file", id: copy.id })}>{copy.label}</button>} — {copy.excerpt}</p>)}
                  <p className="quiet">Grouped links do not count as separate evidence. Ungrouped links are not proven independent.</p>
                </details>}
              </div>)}
            </div> : null}
            {!brain.privacy && lastAsked && <button type="button" className="ghost" onClick={() =>
              document.getElementById("question-workbench")?.scrollIntoView({ block: "start" })}>Follow this question or revisit an old idea</button>}
            {!reply.local_only_evidence && reply.evidence?.some((item) => item.kind === "file") && <button type="button" className="ghost" onClick={async () => {
              const title = window.prompt("Title for this saved answer", draft.slice(0, 80))
              if (!title) return
              const projectId = focus ?? reply.evidence?.find((item) => item.kind === "file")?.project_id
              if (!projectId) return
              const sourceIds = [...new Set(reply.evidence?.filter((item) => item.kind === "file").map((item) => item.id))]
              try {
                await saveAnswer(projectId, title, reply.answer, sourceIds)
                setSaved("Saved under .brain/answers; originals unchanged.")
              } catch (reason) { setSaved(reason instanceof Error ? reason.message : "Could not save answer") }
            }}>Save answer</button>}
            {saved && <p className="quiet">{saved}</p>}
          </div>
        )}
        {askError && <p className="ask-error">{askError}</p>}
        <div className="ask-suggestions">
          {suggestions.map((question) => (
            <button key={question} type="button" onClick={() => void submit(question)}>
              {question}
            </button>
          ))}
        </div>
        <div className="ask-row">
          {!focus && <details className="ask-scope"><summary>{selectedProjects.length ? `${selectedProjects.length} projects` : "All projects"}</summary>
            <div className="ask-scope-list">{brain.projects.map((project) => <label key={project.id}>
              <input type="checkbox" checked={selectedProjects.includes(project.id)} onChange={(event) =>
                setSelectedProjects((before) => event.target.checked ? [...before, project.id] : before.filter((id) => id !== project.id))} />
              {project.name}</label>)}</div></details>}
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask anything about this system"
            aria-label="Ask anything about this system"
          />
          <button type="submit" className="primary" disabled={pending}>
            {pending ? "Thinking" : "Ask"}
          </button>
        </div>
      </form>
      {!brain.privacy && <div id="question-workbench"><QuestionWorkbench target={lastAsked} scannedAt={brain.scanned_at}
        onQuestionsChanged={() => setTraceRevision((value) => value + 1)}
        onEvidence={(item) => item.kind === "file" && onSelect({ kind: "file", id: item.id })} /></div>}
    </div>
  )
}

function openNode(
  node: { kind: string; project_id: string | null; file_id: string | null; service_id: string | null },
  focus: string | null,
  onFocus: (id: string | null) => void,
  onSelect: (selection: Selection) => void,
) {
  if (node.file_id) {
    onSelect({ kind: "file", id: node.file_id })
    return
  }
  if (node.kind === "project" && node.project_id) {
    onSelect({ kind: "project", id: node.project_id })
    if (focus !== node.project_id) onFocus(node.project_id)
    return
  }
  if ((node.kind === "workset" || node.kind === "workspace" || node.kind === "pcf") && node.project_id) {
    onSelect({ kind: "project", id: node.project_id })
    if (focus !== node.project_id) onFocus(node.project_id)
    return
  }
  if (node.service_id) onSelect({ kind: "connection", id: node.service_id })
}
