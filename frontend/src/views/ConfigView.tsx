import { useMemo, useState } from "react"
import { FlowGraph } from "../components/FlowGraph"
import type { Brain, ConfigBoard, ConfigFault, ConfigUnit, ConfigVariable, GraphEdge, GraphNode } from "../types"
import { matchesQuery, projectName } from "../format"

type Props = {
  brain: Brain
  data: ConfigBoard | null
  loading: boolean
  error: string
  query: string
  focus: string | null
  onOpenProject: (id: string) => void
  onOpenFile: (id: string) => void
}

const KIND: Record<ConfigUnit["kind"], string> = {
  workset: "WorkSet",
  workspace: "WorkSpace",
  pcf: "Legacy .pcf",
  config: "Config",
  user: "User",
}

export function ConfigView({ brain, data, loading, error, query, focus, onOpenProject, onOpenFile }: Props) {
  const [mode, setMode] = useState<"graph" | "cards">("graph")
  const [showVariables, setShowVariables] = useState(true)
  const units = (data?.projects ?? [])
    .filter((project) => !focus || project.project_id === focus)
    .flatMap((project) => project.units.map((unit) => ({ project: project.name, unit })))
    .filter(({ project, unit }) => {
      const vars = unit.variables.map((item) => `${item.name} ${item.value} ${item.level} ${item.file}`).join(" ")
      const faults = unit.faults.map((item) => `${item.title} ${item.detail}`).join(" ")
      const refs = unit.variables.flatMap((item) => item.references.map((ref) => `${ref.rel} ${ref.kind}`)).join(" ")
      return matchesQuery(query, `${project} ${unit.name} ${unit.workspace} ${unit.file} ${vars} ${faults} ${refs}`)
    })
  const faults = units.reduce((count, item) => count + item.unit.faults.length, 0)
  const graph = useMemo(() => mergeGraphs(data, focus, showVariables), [data, focus, showVariables])

  return (
    <div className={mode === "graph" ? "view cfg-graph-view" : "conn-page"}>
      <div className={mode === "graph" ? "viz flow-viz" : "cfg-list"}>
      <div className="bp-toolbar">
        <button type="button" className={mode === "graph" ? "on" : ""} onClick={() => setMode("graph")}>
          Graph
        </button>
        <button type="button" className={mode === "cards" ? "on" : ""} onClick={() => setMode("cards")}>
          Cards
        </button>
        {mode === "graph" ? (
          <button type="button" className={showVariables ? "on" : ""} onClick={() => setShowVariables((value) => !value)}>
            Variables
          </button>
        ) : null}
      </div>
      {mode === "graph" ? (
        <div className="flow-canvas">
          {loading && !data ? (
            <p className="empty-copy">Reading configuration files…</p>
          ) : graph.nodes.length === 0 ? (
            <p className="empty-copy">No MicroStation .cfg, .ucf, or .pcf files in this scan.</p>
          ) : (
            <FlowGraph
              nodes={graph.nodes}
              edges={graph.edges}
              query={query}
              onNodeClick={(node) => {
                if (node.file_id) onOpenFile(node.file_id)
                else if (node.project_id) onOpenProject(node.project_id)
              }}
            />
          )}
        </div>
      ) : null}
      {mode === "cards" ? (
        <>
      <header className="conn-head">
        <div>
          <p className="eyebrow">MicroStation</p>
          <h1>configuration</h1>
        </div>
        <p className="conn-count">
          {units.length} card{units.length === 1 ? "" : "s"}
          {faults ? ` · ${faults} fault${faults === 1 ? "" : "s"}` : ""}
          {focus ? ` · ${projectName(brain, focus)}` : ""}
        </p>
      </header>
      <p className="quiet tl-note">
        Read-only. Each card is one WorkSpace, WorkSet, or legacy .pcf. The level is the one that set the resolved value, from System up to User. Folder values should end with /.
      </p>
      {error && <p className="ask-error">{error}</p>}
      {loading && !data && <p className="empty-copy">Reading configuration files…</p>}
      {!loading && !error && units.length === 0 && (
        <p className="empty-copy">No MicroStation .cfg, .ucf, or .pcf files in this scan.</p>
      )}
      <div className="cfg-grid">
        {units.map(({ project, unit }) => (
          <ConfigCard key={unit.id} project={project} unit={unit} onOpenProject={onOpenProject} onOpenFile={onOpenFile} />
        ))}
      </div>
        </>
      ) : null}
      </div>
    </div>
  )
}

function mergeGraphs(data: ConfigBoard | null, focus: string | null, showVariables: boolean): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const projects = (data?.projects ?? []).filter((project) => !focus || project.project_id === focus)
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  for (const project of projects) {
    for (const node of project.graph?.nodes ?? []) {
      if (!showVariables && node.kind === "variable") continue
      nodes.push(node)
    }
    const ids = new Set(nodes.map((node) => node.id))
    for (const edge of project.graph?.edges ?? []) {
      if (ids.has(edge.source) && ids.has(edge.target)) edges.push(edge)
    }
  }
  return { nodes, edges }
}

function ConfigCard({
  project,
  unit,
  onOpenProject,
  onOpenFile,
}: {
  project: string
  unit: ConfigUnit
  onOpenProject: (id: string) => void
  onOpenFile: (id: string) => void
}) {
  return (
    <article className={`cfg-card cfg-${unit.kind}`}>
      <div className="status-top">
        <button type="button" className="tl-jump" onClick={() => onOpenProject(unit.project_id)}>
          {unit.name}
          <span>map</span>
        </button>
        <div className="status-pills">
          <em className="pill pill-mspy">{KIND[unit.kind] || unit.kind}</em>
          {unit.faults.length > 0 ? <em className="pill pill-stale">{unit.faults.length}</em> : null}
        </div>
      </div>
      <p className="cfg-where">
        {project}
        {unit.workspace && unit.kind === "workset" ? ` · ${unit.workspace}` : ""}
        {unit.file ? ` · ${unit.file}` : ""}
      </p>
      <div className="cfg-table-wrap">
        <table className="cfg-table">
          <thead>
            <tr>
              <th>Variable</th>
              <th>Resolved</th>
              <th>Level</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {unit.variables.map((item) => (
              <VariableRows key={item.name} item={item} onOpenFile={onOpenFile} />
            ))}
          </tbody>
        </table>
      </div>
      {unit.faults.length > 0 ? (
        <div className="pitfalls">
          {unit.faults.map((fault) => (
            <FaultButton key={`${fault.id}-${fault.file}-${fault.line}-${fault.variable}`} fault={fault} />
          ))}
        </div>
      ) : (
        <p className="quiet">No configuration faults.</p>
      )}
    </article>
  )
}

function VariableRows({ item, onOpenFile }: { item: ConfigVariable; onOpenFile: (id: string) => void }) {
  const source = item.file ? `${item.file}:${item.line ?? ""}` : ""
  return (
    <>
      <tr>
        <th scope="row">
          {item.name}
          {item.locked ? <em className="cfg-lock">locked</em> : null}
        </th>
        <td>
          <code>{item.value || "not set"}</code>
        </td>
        <td>{item.level || "unset"}</td>
        <td>
          {item.file_id ? (
            <button type="button" onClick={() => onOpenFile(item.file_id as string)}>
              {source}
            </button>
          ) : (
            source
          )}
        </td>
      </tr>
      {item.references.length > 0 && (
        <tr className="cfg-ref-row">
          <td colSpan={4}>
            {item.references.map((ref) => {
              const label = `${ref.kind} ${ref.rel}${ref.line ? `:${ref.line}` : ""}`
              return ref.file_id ? (
                <button key={`${ref.rel}-${ref.line}-${ref.how}`} type="button" onClick={() => onOpenFile(ref.file_id as string)}>
                  {label}
                </button>
              ) : (
                <span key={`${ref.rel}-${ref.line}-${ref.how}`}>{label}</span>
              )
            })}
          </td>
        </tr>
      )}
    </>
  )
}

function FaultButton({ fault }: { fault: ConfigFault }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      className={`pitfall pitfall-${fault.severity}`}
      onClick={() => {
        void writeClipboard(fault.prompt).then((ok) => {
          if (!ok) return
          setCopied(true)
          window.setTimeout(() => setCopied(false), 2500)
        })
      }}
    >
      <strong>{fault.title}</strong>
      <span>{fault.detail}</span>
      <em>{copied ? "Copied" : "Copy fix prompt"}</em>
    </button>
  )
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through */
  }
  try {
    const area = document.createElement("textarea")
    area.value = text
    area.setAttribute("readonly", "")
    area.style.position = "fixed"
    area.style.left = "0"
    area.style.top = "0"
    area.style.opacity = "0"
    document.body.appendChild(area)
    area.focus()
    area.select()
    const ok = document.execCommand("copy")
    area.remove()
    return ok
  } catch {
    return false
  }
}
