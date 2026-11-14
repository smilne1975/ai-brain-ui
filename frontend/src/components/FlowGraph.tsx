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
import "@xyflow/react/dist/style.css"
import type { GraphEdge, GraphNode } from "../types"
import { matchesQuery } from "../format"

type CardData = {
  label: string
  sub: string
  kind: string
  dim: boolean
  badge: string
  severity: string
  fileId: string | null
  projectId: string | null
  serviceId: string | null
}

type FlowNode = Node<CardData, "card" | "diamond">

type Props = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  query?: string
  onNodeClick?: (node: GraphNode) => void
}

export function FlowGraph({ nodes, edges, query = "", onNodeClick }: Props) {
  const flow = layout(nodes, edges)
  const drawn = flow.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      dim: !matchesQuery(query, `${node.data.label} ${node.data.sub} ${node.data.kind} ${node.data.badge}`),
    },
  }))
  return (
    <ReactFlow
      nodes={drawn}
      edges={flow.edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.18 }}
      minZoom={0.2}
      maxZoom={1.7}
      nodesConnectable={false}
      proOptions={{ hideAttribution: false }}
      onNodeClick={(_, node) => {
        const source = nodes.find((item) => item.id === node.id)
        if (source && onNodeClick) onNodeClick(source)
      }}
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
  )
}

const nodeTypes = {
  card: CardNode,
  diamond: DiamondNode,
}

function CardNode({ data }: NodeProps<Node<CardData, "card">>) {
  return (
    <div className={`rf-card kind-${data.kind}${data.severity ? ` sev-${data.severity}` : ""}${data.dim ? " dim" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="rf-kicker">
        {data.kind}
        {data.badge ? <em className={`rf-badge sev-${data.severity || "amber"}`}>{data.badge}</em> : null}
      </div>
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

function layout(nodes: GraphNode[], edges: GraphEdge[]): { nodes: FlowNode[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: "TB", nodesep: 34, ranksep: 62, marginx: 16, marginy: 28 })
  for (const node of nodes) {
    const diamond = node.kind === "decision"
    g.setNode(node.id, { width: diamond ? 150 : 220, height: diamond ? 118 : 84 })
  }
  const ids = new Set(nodes.map((node) => node.id))
  for (const edge of edges) {
    if (ids.has(edge.source) && ids.has(edge.target)) g.setEdge(edge.source, edge.target)
  }
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
        badge: node.badge || "",
        severity: node.severity || "",
        fileId: node.file_id,
        projectId: node.project_id,
        serviceId: node.service_id,
      },
    }
  })
  const hot = new Set(["mentions", "overrides", "blocked", "includes"])
  const flowEdges: Edge[] = edges
    .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label || undefined,
      type: "smoothstep",
      style: {
        stroke: hot.has(edge.label) ? "rgba(240,193,74,0.75)" : "rgba(61,255,154,0.5)",
        strokeWidth: 1.25,
      },
      labelStyle: { fill: "#c5d7cc", fontSize: 10 },
      labelBgStyle: { fill: "#0b100e", fillOpacity: 0.9 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
    }))
  return { nodes: flowNodes, edges: flowEdges }
}
