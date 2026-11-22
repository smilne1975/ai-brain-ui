import { Component, useEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode } from "react"
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d"
import { MAP_LINK_BUDGET, MAP_NODE_BUDGET } from "../graphInventory"
import type { GraphEdge, GraphNode } from "../types"

type Node3D = GraphNode & { x: number; y: number; z: number; val: number; color: string }
type Link3D = { source: string | Node3D; target: string | Node3D; label: string; inferred: boolean }

const endpoint = (node: string | Node3D) => typeof node === "string" ? node : node.id
const PALETTE = ["#45ffac", "#6cd5ff", "#c7abff", "#f0c14a", "#ff9b91"]

function seed(id: string, n: number) {
  let value = 2166136261
  for (const char of id) value = Math.imul(value ^ char.charCodeAt(0), 16777619)
  return ((value >>> (n * 7)) & 1023) / 1023
}

function escapeHtml(text: string) {
  return text.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char)
}

class Graph3DFallback extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

export function SafeGraph3D({ fallback, ...props }: ComponentProps<typeof Graph3D> & { fallback: ReactNode }) {
  return <Graph3DFallback fallback={fallback}><Graph3D {...props} /></Graph3DFallback>
}

export function Graph3D({ nodes, edges, query, selectedId, fitNodeId, scope, onNodeClick, onClear }: {
  nodes: GraphNode[]; edges: GraphEdge[]; query: string; selectedId: string | null; scope: string | null;
  fitNodeId?: string;
  onNodeClick: (node: GraphNode) => void; onClear: () => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const graph = useRef<ForceGraphMethods<Node3D, Link3D> | undefined>(undefined)
  const [size, setSize] = useState({ width: 900, height: 500 })
  useEffect(() => {
    const element = box.current
    if (!element) return
    const observer = new ResizeObserver(() => setSize({ width: element.clientWidth, height: element.clientHeight }))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const data = useMemo(() => {
    const visible = (scope ? nodes : [...nodes].sort((a, b) => Number(b.kind === "project") - Number(a.kind === "project"))).slice(0, MAP_NODE_BUDGET)
    const ids = new Set(visible.map((node) => node.id))
    const roots = visible.filter((node) => node.kind === "project")
    return {
      nodes: visible.map((node): Node3D => {
        const hub = node.kind === "project"
        const i = Math.max(0, roots.indexOf(node))
        const angle = i * 2.39996323
        const radius = !scope && hub && roots.length > 1 ? 44 * Math.sqrt(i + 1) : 0
        return { ...node, x: hub ? Math.cos(angle) * radius : (seed(node.id, 0) - 0.5) * 180,
          y: hub ? Math.sin(angle) * radius : (seed(node.id, 1) - 0.5) * 180,
          z: hub ? 0 : (seed(node.id, 2) - 0.5) * 180,
          val: hub ? 18 : node.kind === "decision" || node.kind === "question" ? 6 : 3,
          color: hub ? PALETTE[i % PALETTE.length] : node.kind === "decision" ? "#f0c14a"
            : node.kind === "question" ? "#c7abff" : node.kind === "service" ? "#7fd6ff"
              : node.kind === "note" ? "#d8ffeb" : "#68dca0" }
      }),
      links: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).slice(0, MAP_LINK_BUDGET)
        .map((edge): Link3D => ({ source: edge.source, target: edge.target, label: edge.label,
          inferred: /^(e:svc:|e:svcroot:|workflow:)/.test(edge.id) || edge.label === "mentions" })),
    }
  }, [nodes, edges, scope])
  const neighborhood = useMemo(() => {
    const ids = new Set<string>()
    if (!selectedId) return ids
    ids.add(selectedId)
    for (const edge of edges) {
      if (edge.source === selectedId) ids.add(edge.target)
      if (edge.target === selectedId) ids.add(edge.source)
    }
    return ids
  }, [edges, selectedId])
  const selection = data.nodes.find((node) => node.id === selectedId)
  function duration() { return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650 }
  useEffect(() => {
    // Let the new cluster settle before fitting its bounds; dispose on fast switches.
    const subset = new Set(fitNodeId ? [fitNodeId, ...edges.flatMap((edge) => edge.source === fitNodeId ? [edge.target] :
      edge.target === fitNodeId ? [edge.source] : [])].slice(0, 9) : [])
    const ticket = window.setTimeout(() => graph.current?.zoomToFit(duration(), 75,
      fitNodeId ? (node) => subset.has(node.id) : undefined), 280)
    return () => window.clearTimeout(ticket)
  }, [scope, data, edges, fitNodeId])
  const q = query.trim().toLowerCase()
  const isDirect = (link: Link3D) => !!selectedId && [endpoint(link.source), endpoint(link.target)].includes(selectedId)
  return (
    <div ref={box} className="graph-3d" aria-label="Interactive 3D project graph">
      <ForceGraph3D<Node3D, Link3D> ref={graph}
        graphData={data} width={size.width} height={size.height}
        backgroundColor="#070e0a" nodeRelSize={5} nodeOpacity={0.92}
        nodeLabel={(node) => `<strong>${escapeHtml(String(node.label || ""))}</strong><br>${escapeHtml(String(node.kind || ""))}`}
        nodeColor={(node) => node.id === selectedId ? "#ffffff" : (selectedId ? !neighborhood.has(node.id) :
          q && !`${node.label} ${node.sub}`.toLowerCase().includes(q)) ? "#293e35" : node.color}
        nodeVal={(node) => node.val}
        linkColor={(link) => selectedId && !isDirect(link) ? "#1c3229" : link.inferred ? "#f0c14a" : "#3dff9a"} linkOpacity={0.5}
        linkLabel={(link) => escapeHtml(link.inferred ? `Inferred · ${link.label || "service reference"}` : String(link.label || "Indexed relationship"))}
        linkWidth={(link) => isDirect(link) ? 1.8 : 0.65} showNavInfo={false} warmupTicks={35} cooldownTicks={100}
        onNodeClick={(node) => onNodeClick(node as Node3D)}
        onBackgroundClick={onClear}
      />
      <div className="brain-orbit-controls">
        <button type="button" className="ghost" onClick={() => graph.current?.zoomToFit(duration(), 75)}>Fit map</button>
        {selection && <button type="button" className="ghost" onClick={onClear}>Clear highlight</button>}
      </div>
      <div className="graph-3d-legend">{selection ? `${selection.label} · ${Math.max(0, neighborhood.size - 1)} direct ${neighborhood.size === 2 ? "connection" : "connections"}` : "Drag to orbit · Scroll to zoom · Gold links are inferred"}
        {data.nodes.length !== nodes.length || data.links.length !== edges.length ? ` · showing ${data.nodes.length}/${nodes.length} nodes, ${data.links.length}/${edges.length} links` : ""}
      </div>
    </div>
  )
}
