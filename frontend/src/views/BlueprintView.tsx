import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react"
import * as dagre from "dagre"
import { useMemo, useState } from "react"
import "@xyflow/react/dist/style.css"
import { ask } from "../api"
import type { AskResponse, Brain, GraphEdge, GraphNode, Selection } from "../types"
import { matchesQuery } from "../format"

type CardData = {
  label: string
  sub: string
  kind: string
  dim: boolean
  fileId: string | null
  projectId: string | null
  serviceId: string | null
}

type FlowNode = Node<CardData, "card" | "diamond">

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
    return layout(sourceNodes, sourceEdges)
  }, [graph, activeFilter])

  const nodes = flow.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      dim: !matchesQuery(query, `${node.data.label} ${node.data.sub} ${node.data.kind}`),
    },
  }))

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
        <ReactFlow
          key={`${focus ?? "corpus"}-${filter}`}
          nodes={nodes}
          edges={flow.edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          minZoom={0.2}
          maxZoom={1.7}
          nodesConnectable={false}
          proOptions={{ hideAttribution: false }}
          onNodeClick={(_, node) => openNode(node.data, focus, onFocus, onSelect)}
        >
          <Background color="rgba(61,255,154,0.16)" gap={22} size={1} />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            maskColor="rgba(0,0,0,0.72)"
            nodeColor={(node) => (node.type === "diamond" ? "#f0c14a" : "#1bd67a")}
            style={{ background: "#0c100e" }}
          />
        </ReactFlow>
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
  data: CardData,
  focus: string | null,
  onFocus: (id: string | null) => void,
  onSelect: (selection: Selection) => void,
) {
  if (data.kind === "project" && data.projectId) {
    onSelect({ kind: "project", id: data.projectId })
    if (focus !== data.projectId) onFocus(data.projectId)
    return
  }
  if (data.fileId) {
    onSelect({ kind: "file", id: data.fileId })
    return
  }
  if (data.serviceId) onSelect({ kind: "connection", id: data.serviceId })
}

const nodeTypes = {
  card: CardNode,
  diamond: DiamondNode,
}

function CardNode({ data }: NodeProps<Node<CardData, "card">>) {
  return (
    <div className={`rf-card kind-${data.kind}${data.dim ? " dim" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="rf-kicker">{data.kind}</div>
      <div className="rf-label">{data.label}</div>
      <div className="rf-sub">{data.sub}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

function DiamondNode({ data }: NodeProps<Node<CardData, "diamond">>) {
  return (
    <div className={`rf-diamond${data.dim ? " dim" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="rf-diamond-shape">
        <span>{data.label}</span>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

function layout(nodes: GraphNode[], edges: GraphEdge[]): {
  nodes: FlowNode[]
  edges: Edge[]
} {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: "TB", nodesep: 34, ranksep: 62, marginx: 16, marginy: 28 })
  for (const node of nodes) {
    const diamond = node.kind === "decision"
    g.setNode(node.id, { width: diamond ? 150 : 220, height: diamond ? 118 : 84 })
  }
  for (const edge of edges) g.setEdge(edge.source, edge.target)
  dagre.layout(g)
  const flowNodes: FlowNode[] = nodes.map((node) => {
    const diamond = node.kind === "decision"
    const width = diamond ? 150 : 220
    const height = diamond ? 118 : 84
    const point = g.node(node.id)
    return {
      id: node.id,
      type: diamond ? "diamond" : "card",
      position: { x: point.x - width / 2, y: point.y - height / 2 },
      width,
      height,
      data: {
        label: node.label,
        sub: node.sub,
        kind: node.kind,
        dim: false,
        fileId: node.file_id,
        projectId: node.project_id,
        serviceId: node.service_id,
      },
    }
  })
  const flowEdges: Edge[] = edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label || undefined,
    type: "smoothstep",
    style: {
      stroke: edge.label === "mentions" ? "rgba(240,193,74,0.75)" : "rgba(61,255,154,0.5)",
      strokeWidth: 1.25,
    },
    labelStyle: { fill: "#c5d7cc", fontSize: 10 },
    labelBgStyle: { fill: "#0b100e", fillOpacity: 0.9 },
    labelBgPadding: [4, 2] as [number, number],
    labelBgBorderRadius: 4,
  }))
  return { nodes: flowNodes, edges: flowEdges }
}
