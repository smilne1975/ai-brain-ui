import { useEffect, useMemo, useRef, useState } from "react"
import ForceGraph3D from "react-force-graph-3d"
import type { GraphEdge, GraphNode } from "../types"

type Node3D = GraphNode & { x: number; y: number; z: number; val: number; color: string }
type Link3D = { source: string; target: string; label: string }

function seed(id: string, n: number) {
  let value = 2166136261
  for (const char of id) value = Math.imul(value ^ char.charCodeAt(0), 16777619)
  return ((value >>> (n * 7)) & 1023) / 1023
}

function escapeHtml(text: string) {
  return text.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char)
}

export function Graph3D({ nodes, edges, query, onNodeClick }: {
  nodes: GraphNode[]; edges: GraphEdge[]; query: string; onNodeClick: (node: GraphNode) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 900, height: 500 })
  useEffect(() => {
    const element = box.current
    if (!element) return
    const observer = new ResizeObserver(() => setSize({ width: element.clientWidth, height: element.clientHeight }))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const data = useMemo(() => {
    const visible = nodes.slice(0, 180)
    const q = query.trim().toLowerCase()
    const ids = new Set(visible.map((node) => node.id))
    return {
      nodes: visible.map((node): Node3D => ({ ...node, x: (seed(node.id, 0) - 0.5) * 360,
        y: (seed(node.id, 1) - 0.5) * 360, z: (seed(node.id, 2) - 0.5) * 360,
        val: node.kind === "project" ? 12 : 4,
        color: q && !`${node.label} ${node.sub}`.toLowerCase().includes(q) ? "#35473b"
          : node.kind === "project" ? "#3dff9a" : node.kind === "decision" ? "#f0c14a"
            : node.kind === "service" ? "#7fd6ff" : "#8ee4b5" })),
      links: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).slice(0, 400)
        .map((edge): Link3D => ({ source: edge.source, target: edge.target, label: edge.label })),
    }
  }, [nodes, edges, query])
  return (
    <div ref={box} className="graph-3d" aria-label="Interactive 3D project graph">
      <ForceGraph3D
        graphData={data} width={size.width} height={size.height}
        backgroundColor="#070e0a" nodeRelSize={5} nodeOpacity={0.92}
        nodeLabel={(node) => `<strong>${escapeHtml(String(node.label || ""))}</strong><br>${escapeHtml(String(node.kind || ""))}`}
        nodeColor={(node) => String(node.color)} nodeVal={(node) => Number(node.val)}
        linkColor={() => "rgba(61,255,154,0.28)"} linkOpacity={0.35}
        linkWidth={0.7} showNavInfo={false} warmupTicks={35}
        onNodeClick={(node) => onNodeClick(node as Node3D)}
      />
      <div className="graph-3d-legend">Drag to orbit · Scroll to zoom · Click a node to inspect
        {nodes.length > 180 || edges.length > 400 ? ` · showing ${data.nodes.length}/${nodes.length} nodes, ${data.links.length}/${edges.length} links` : ""}
      </div>
    </div>
  )
}
