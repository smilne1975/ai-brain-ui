import * as d3 from "d3"
import { useEffect, useMemo, useRef, useState } from "react"
import type { Brain, FileRec, Selection } from "../types"
import { matchesQuery, projectName } from "../format"

type Props = {
  brain: Brain
  query: string
  focus: string | null
  selection: Selection | null
  onSelect: (selection: Selection) => void
}

type Ray = { file: FileRec; angle: number; len: number; dim: boolean }

const KIND_COLOR: Record<string, string> = {
  python: "#3dff9a",
  markdown: "#e7fff3",
  config: "#8ecbff",
  env: "#8ecbff",
  shell: "#d2b4ff",
  notebook: "#ffb086",
  other: "#9ad7ff",
  binary: "#5c6b63",
}

export function SystemView({ brain, query, focus, selection, onSelect }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 900, h: 640 })
  const [tip, setTip] = useState<{ x: number; y: number; file: FileRec } | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setSize({ w: Math.max(320, el.clientWidth), h: Math.max(320, el.clientHeight) })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const model = useMemo(() => buildRing(brain, query, focus), [brain, query, focus])
  const selectedFile = selection?.kind === "file" ? selection.id : null
  const arc = d3.arc<{ start: number; end: number }>().innerRadius(126).outerRadius(148).padAngle(0.012)
  const center = focus ? projectName(brain, focus) : brain.root_name

  return (
    <div className="view">
      <div className="viz" ref={ref}>
        <div className="viz-caption">
          <p className="eyebrow">Corpus meters</p>
          <h2>{center}</h2>
          <p className="quiet">Bar length follows file size. Gold means an unfinished marker.</p>
        </div>
        <svg className="scene" width={size.w} height={size.h} role="img" aria-label="Circular system meters">
          <defs>
            <filter id="sysglow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <g transform={`translate(${size.w / 2} ${size.h / 2 + 4})`}>
            <circle r="210" className="guide" />
            <circle r="168" className="guide" />
            {model.arcs.map((band) => (
              <path key={band.id} d={arc({ start: band.start, end: band.end }) ?? ""} fill={band.color} opacity="0.28" />
            ))}
            {model.rays.map((ray, index) => {
              const inner = 164
              const outer = inner + ray.len
              const [x1, y1] = d3.pointRadial(ray.angle, inner)
              const [x2, y2] = d3.pointRadial(ray.angle, outer)
              const selected = ray.file.id === selectedFile
              const color = ray.file.todos.length ? "#f0c14a" : (KIND_COLOR[ray.file.kind] ?? "#9ad7ff")
              return (
                <line
                  key={`${ray.file.id}-${index}`}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={color}
                  strokeWidth={selected ? 3.2 : 1.7}
                  strokeLinecap="round"
                  opacity={ray.dim ? 0.12 : selected ? 1 : 0.82}
                  onClick={() => onSelect({ kind: "file", id: ray.file.id })}
                  onMouseEnter={(event) => setTip({ x: event.clientX, y: event.clientY, file: ray.file })}
                  onMouseLeave={() => setTip(null)}
                />
              )
            })}
            <g filter="url(#sysglow)">
              <circle r="54" fill="#07140e" stroke="#3dff9a" strokeWidth="1.4" />
              <circle r="7" fill="#3dff9a" className="core-pulse" />
            </g>
            <text className="meter-count" textAnchor="middle" y="-2">
              {model.fileCount}
            </text>
            <text className="meter-unit" textAnchor="middle" y="16">
              files
            </text>
          </g>
        </svg>
        <ul className="legend">
          <li><i style={{ background: "#3dff9a" }} /> Python</li>
          <li><i style={{ background: "#e7fff3" }} /> Notes</li>
          <li><i style={{ background: "#8ecbff" }} /> Config</li>
          <li><i style={{ background: "#f0c14a" }} /> TODO</li>
        </ul>
        {tip && (
          <div className="tip" style={{ left: tip.x, top: tip.y }}>
            <strong>{projectName(brain, tip.file.project_id)}/{tip.file.rel}</strong>
            <span>
              {tip.file.lines} lines · {tip.file.kind}
              {tip.file.todos.length ? ` · ${tip.file.todos.length} unfinished` : ""}
            </span>
          </div>
        )}
      </div>
      <h1 className="stage-title">system</h1>
    </div>
  )
}

function buildRing(brain: Brain, query: string, focus: string | null) {
  const projects = focus ? brain.projects.filter((project) => project.id === focus) : brain.projects
  const files = brain.files.filter((file) => !focus || file.project_id === focus)
  const rays: { file: FileRec }[] = []
  for (const file of files) {
    const copies = 1 + Math.min(3, Math.floor(file.lines / 28))
    for (let i = 0; i < copies; i += 1) rays.push({ file })
  }
  const groups = projects
    .map((project) => ({ project, rays: rays.filter((ray) => ray.file.project_id === project.id) }))
    .filter((group) => group.rays.length)
  const gap = groups.length > 1 ? 0.05 : 0
  const usable = Math.PI * 2 - gap * groups.length
  const step = rays.length ? usable / rays.length : 0
  let cursor = 0
  const placed: Ray[] = []
  const arcs: { id: string; name: string; start: number; end: number; color: string }[] = []
  const palette = ["#3dff9a", "#f0c14a", "#7fd6ff", "#d2b4ff", "#ffb086", "#ff8ad4"]
  groups.forEach((group, index) => {
    const start = cursor
    for (const ray of group.rays) {
      const len = Math.max(18, Math.min(150, 16 + ray.file.lines * 0.85))
      const dim = !matchesQuery(query, `${ray.file.rel} ${ray.file.summary} ${ray.file.kind}`)
      placed.push({ file: ray.file, angle: cursor + step / 2, len, dim })
      cursor += step
    }
    arcs.push({
      id: group.project.id,
      name: group.project.name,
      start,
      end: cursor,
      color: palette[index % palette.length],
    })
    cursor += gap
  })
  return { rays: placed, arcs, fileCount: files.length }
}
