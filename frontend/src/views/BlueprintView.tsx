import { lazy, Suspense, useEffect, useMemo, useState } from "react"
import { ask, fetchKnowledge, saveAnswer } from "../api"
import { FlowGraph } from "../components/FlowGraph"
import type { AskResponse, Brain, KnowledgePage, Selection } from "../types"

type Props = {
  brain: Brain
  query: string
  focus: string | null
  onFocus: (id: string | null) => void
  onSelect: (selection: Selection) => void
  onOpenKnowledge: (projectId: string) => void
}

const Graph3D = lazy(() => import("../components/Graph3D").then((module) => ({ default: module.Graph3D })))

const FILTERS: { id: string; label: string; kinds: Set<string> | null }[] = [
  { id: "all", label: "All", kinds: null },
  { id: "scripts", label: "Scripts", kinds: new Set(["project", "entry", "script", "tool", "store", "keyin", "function"]) },
  { id: "notes", label: "Notes", kinds: new Set(["project", "note", "model"]) },
  { id: "decisions", label: "Decisions", kinds: new Set(["project", "decision", "entry", "script"]) },
  { id: "services", label: "Services", kinds: new Set(["project", "service"]) },
  { id: "config", label: "Config", kinds: new Set(["project", "workspace", "workset", "pcf", "variable", "cfg", "script"]) },
]

export function BlueprintView({ brain, query, focus, onFocus, onSelect, onOpenKnowledge }: Props) {
  const [filter, setFilter] = useState("all")
  const [draft, setDraft] = useState("")
  const [pending, setPending] = useState(false)
  const [reply, setReply] = useState<AskResponse | null>(null)
  const [askError, setAskError] = useState("")
  const [dimension, setDimension] = useState<"2d" | "3d">("2d")
  const [saved, setSaved] = useState("")
  const [selectedProjects, setSelectedProjects] = useState<string[]>([])
  const [knowledgePages, setKnowledgePages] = useState<KnowledgePage[]>([])

  useEffect(() => {
    let active = true
    void fetchKnowledge().then((data) => { if (active) setKnowledgePages(data.pages) }).catch(() => undefined)
    return () => { active = false }
  }, [brain.scanned_at])

  const graph = focus ? brain.architecture.projects[focus] : brain.architecture.corpus
  const activeFilter = FILTERS.find((item) => item.id === filter) ?? FILTERS[0]

  const flow = useMemo(() => {
    const sourceNodes = (graph?.nodes ?? []).filter((node) => !activeFilter.kinds || activeFilter.kinds.has(node.kind))
    const pageNodes = knowledgePages.filter((page) => (!focus || page.project_id === focus) &&
      (!activeFilter.kinds || activeFilter.kinds.has("note"))).map((page) => ({
        id: `knowledge:${page.page_id}`, label: `${page.title} knowledge`, sub: page.stale_sources.length ? "Needs recheck" : "Approved page",
        kind: "note", project_id: page.project_id, file_id: null, service_id: null,
      }))
    sourceNodes.push(...pageNodes)
    const ids = new Set(sourceNodes.map((node) => node.id))
    const sourceEdges = (graph?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    for (const page of knowledgePages) {
      if (!ids.has(`knowledge:${page.page_id}`)) continue
      const projectNode = (graph?.nodes ?? []).find((node) => node.kind === "project" && node.project_id === page.project_id)
      if (projectNode && ids.has(projectNode.id)) sourceEdges.push({ id: `knowledge-edge:${page.page_id}`, source: projectNode.id,
        target: `knowledge:${page.page_id}`, label: "knowledge" })
      for (const source of page.sources) {
        const fileNode = (graph?.nodes ?? []).find((node) => node.file_id === source.id)
        if (fileNode && ids.has(fileNode.id)) sourceEdges.push({ id: `knowledge-source:${page.page_id}:${source.id}`,
          source: fileNode.id, target: `knowledge:${page.page_id}`, label: "cites" })
      }
    }
    return { nodes: sourceNodes, edges: sourceEdges }
  }, [graph, activeFilter, knowledgePages, focus])

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
      setReply(await ask(text, focus, focus ? undefined : selectedProjects))
    } catch (error) {
      setReply(null)
      setAskError(error instanceof Error ? error.message : "The question could not be answered.")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="view with-ask">
      <div className="viz flow-viz">
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
          <span className="toolbar-gap" />
          <button type="button" className={dimension === "2d" ? "on" : ""} onClick={() => setDimension("2d")}>2D</button>
          <button type="button" className={dimension === "3d" ? "on" : ""} onClick={() => setDimension("3d")}>3D</button>
          {FILTERS.map((item) => (
            <button key={item.id} type="button" className={filter === item.id ? "on" : ""} onClick={() => setFilter(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="flow-canvas">
          {dimension === "3d" ? <Suspense fallback={<p className="quiet">Loading 3D graph...</p>}><Graph3D nodes={flow.nodes} edges={flow.edges} query={query}
            onNodeClick={(node) => node.id.startsWith("knowledge:") && node.project_id ? onOpenKnowledge(node.project_id) : openNode(node, focus, onFocus, onSelect)} /></Suspense> : <FlowGraph
            key={`${focus ?? "corpus"}-${filter}`}
            nodes={flow.nodes}
            edges={flow.edges}
            query={query}
            onNodeClick={(node) => node.id.startsWith("knowledge:") && node.project_id ? onOpenKnowledge(node.project_id) : openNode(node, focus, onFocus, onSelect)}
          />}
        </div>
      </div>
      <h1 className="stage-title">blueprint</h1>
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
              {reply.citations.map((cite) => (
                <button key={cite.id} type="button" onClick={() => onSelect({ kind: "file", id: cite.id })}>
                  {cite.label}
                </button>
              ))}
            </div>
            {reply.incomplete && <p className="quiet">The scan hit its file cap; other files may hold more evidence.</p>}
            {reply.evidence?.length ? <div className="ask-evidence">
              <strong>Evidence from {new Set(reply.evidence.map((item) => item.project_id)).size} project(s)</strong>
              {reply.evidence.map((item) => <button key={item.id} type="button"
                onClick={() => item.kind === "file" ? onSelect({ kind: "file", id: item.id }) : onFocus(item.project_id)}>
                {item.label}{item.stale ? " · needs recheck" : ""} — {item.excerpt}
              </button>)}
            </div> : null}
            {reply.evidence?.some((item) => item.kind === "file") && <button type="button" className="ghost" onClick={async () => {
              const title = window.prompt("Title for this saved answer", draft.slice(0, 80))
              if (!title) return
              const projectId = focus ?? reply.evidence?.find((item) => item.kind === "file")?.project_id
              if (!projectId) return
              const sourceIds = reply.evidence?.filter((item) => item.kind === "file").map((item) => item.id) ?? []
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
