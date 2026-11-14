import { useMemo, useState } from "react"
import { ask } from "../api"
import { FlowGraph } from "../components/FlowGraph"
import type { AskResponse, Brain, Selection } from "../types"

type Props = {
  brain: Brain
  query: string
  focus: string | null
  onFocus: (id: string | null) => void
  onSelect: (selection: Selection) => void
}

const FILTERS: { id: string; label: string; kinds: Set<string> | null }[] = [
  { id: "all", label: "All", kinds: null },
  { id: "scripts", label: "Scripts", kinds: new Set(["project", "entry", "script", "tool", "store", "keyin", "function"]) },
  { id: "notes", label: "Notes", kinds: new Set(["project", "note", "model"]) },
  { id: "decisions", label: "Decisions", kinds: new Set(["project", "decision", "entry", "script"]) },
  { id: "services", label: "Services", kinds: new Set(["project", "service"]) },
  { id: "config", label: "Config", kinds: new Set(["project", "workspace", "workset", "pcf", "variable", "cfg", "script"]) },
]

export function BlueprintView({ brain, query, focus, onFocus, onSelect }: Props) {
  const [filter, setFilter] = useState("all")
  const [draft, setDraft] = useState("")
  const [pending, setPending] = useState(false)
  const [reply, setReply] = useState<AskResponse | null>(null)
  const [askError, setAskError] = useState("")

  const graph = focus ? brain.architecture.projects[focus] : brain.architecture.corpus
  const activeFilter = FILTERS.find((item) => item.id === filter) ?? FILTERS[0]

  const flow = useMemo(() => {
    const sourceNodes = (graph?.nodes ?? []).filter((node) => !activeFilter.kinds || activeFilter.kinds.has(node.kind))
    const ids = new Set(sourceNodes.map((node) => node.id))
    const sourceEdges = (graph?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    return { nodes: sourceNodes, edges: sourceEdges }
  }, [graph, activeFilter])

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
    try {
      setReply(await ask(text, focus))
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
          {FILTERS.map((item) => (
            <button key={item.id} type="button" className={filter === item.id ? "on" : ""} onClick={() => setFilter(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="flow-canvas">
          <FlowGraph
            key={`${focus ?? "corpus"}-${filter}`}
            nodes={flow.nodes}
            edges={flow.edges}
            query={query}
            onNodeClick={(node) => openNode(node, focus, onFocus, onSelect)}
          />
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
