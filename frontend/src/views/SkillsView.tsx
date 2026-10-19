import * as d3 from "d3"
import { useEffect, useMemo, useRef, useState } from "react"
import { CATEGORY_COLOR, type Brain, type Selection } from "../types"
import { matchesQuery } from "../format"

type Props = {
  brain: Brain
  query: string
  focus: string | null
  selection: Selection | null
  onSelect: (selection: Selection) => void
}

type Datum = {
  name: string
  kind: "root" | "category" | "skill"
  id?: string
  blurb?: string
  score?: number
  color: string
  dim: boolean
  children?: Datum[]
}

type Tip = { x: number; y: number; title: string; body: string }

export function SkillsView({ brain, query, focus, selection, onSelect }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 900, h: 640 })
  const [tip, setTip] = useState<Tip | null>(null)
  const focusName = brain.projects.find((project) => project.id === focus)?.name

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setSize({ w: Math.max(320, el.clientWidth), h: Math.max(320, el.clientHeight) })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const model = useMemo(() => {
    const skills = Object.fromEntries(brain.skills.map((skill) => [skill.id, skill]))
    const data: Datum = {
      name: focusName ?? brain.root_name,
      kind: "root",
      color: "#3dff9a",
      dim: false,
      children: brain.categories.map((category) => {
        const color = CATEGORY_COLOR[category.name] ?? "#3dff9a"
        const children = category.skills.map((id) => {
          const skill = skills[id]
          const focused = !focus || skill.projects.includes(focus)
          const hit = matchesQuery(query, `${skill.name} ${skill.category} ${skill.blurb}`)
          return {
            name: skill.name,
            kind: "skill" as const,
            id: skill.id,
            blurb: skill.blurb,
            score: skill.score,
            color,
            dim: !(focused && hit),
          }
        })
        return {
          name: category.name,
          kind: "category" as const,
          id: category.id,
          color,
          dim: children.every((child) => child.dim),
          children,
        }
      }),
    }
    const root = d3.hierarchy(data)
    const radius = Math.max(150, Math.min(size.w, size.h) / 2 - 78)
    const tree = d3
      .tree<Datum>()
      .size([2 * Math.PI, radius])
      .separation((a, b) => (a.parent === b.parent ? 1.15 : 2.1) / Math.max(a.depth, 1))
    return { laid: tree(root), radius }
  }, [brain, focus, focusName, query, size.w, size.h])

  const selectedId = selection?.kind === "skill" ? selection.id : null

  return (
    <div className="view">
      <div className="viz" ref={ref}>
        <div className="viz-caption">
          <p className="eyebrow">Capability library</p>
          <h2>{focusName ? focusName : "Every folder"}</h2>
          <p className="quiet">
            {brain.skills.length} skills · {brain.categories.length} branches
          </p>
        </div>
        <svg className="scene" width={size.w} height={size.h} role="img" aria-label="Radial skill map">
          <defs>
            <filter id="glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <radialGradient id="core" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#b8ffd8" />
              <stop offset="45%" stopColor="#3dff9a" />
              <stop offset="100%" stopColor="#0c3d24" />
            </radialGradient>
          </defs>
          <g transform={`translate(${size.w / 2} ${size.h / 2 + 6})`}>
            <circle r={model.radius * 0.55} className="guide" />
            <circle r={model.radius} className="guide" />
            {model.laid.links().map((link, index) => {
              const dim = link.target.data.dim
              const path = branch(link.source.x, link.source.y, link.target.x, link.target.y)
              return (
                <path
                  key={index}
                  d={path}
                  fill="none"
                  stroke={link.target.data.color}
                  strokeOpacity={dim ? 0.08 : 0.55}
                  strokeWidth={link.target.data.kind === "category" ? 1.4 : 1}
                />
              )
            })}
            {model.laid.descendants().map((node) => {
              const [x, y] = d3.pointRadial(node.x, node.y)
              if (node.data.kind === "root") {
                return (
                  <g key="root" filter="url(#glow)">
                    <circle r="34" fill="url(#core)" />
                    <circle r="34" fill="none" stroke="#d8ffe9" strokeOpacity="0.45" />
                    <text className="core-label" textAnchor="middle" dy="4">
                      core
                    </text>
                  </g>
                )
              }
              if (node.data.kind === "category") {
                return (
                  <g key={node.data.id} opacity={node.data.dim ? 0.2 : 1}>
                    <circle cx={x} cy={y} r="8" fill={node.data.color} />
                    <text
                      x={x}
                      y={y}
                      dy={node.x > Math.PI ? 22 : -14}
                      textAnchor="middle"
                      className="cat-label"
                      fill={node.data.color}
                    >
                      {node.data.name}
                    </text>
                  </g>
                )
              }
              const selected = node.data.id === selectedId
              const anchor = labelAnchor(node.x)
              const [lx, ly] = d3.pointRadial(node.x, node.y + 16)
              return (
                <g
                  key={node.data.id}
                  opacity={node.data.dim ? 0.16 : 1}
                  className="skill-node"
                  onClick={() => node.data.id && onSelect({ kind: "skill", id: node.data.id })}
                  onMouseEnter={(event) =>
                    setTip({
                      x: event.clientX,
                      y: event.clientY,
                      title: node.data.name,
                      body: `${node.data.blurb ?? ""} · ${node.data.score ?? 0} files`,
                    })
                  }
                  onMouseLeave={() => setTip(null)}
                >
                  <circle cx={x} cy={y} r={selected ? 7 : 4.5} fill={node.data.color} stroke="#f4fff8" strokeOpacity={selected ? 0.9 : 0.25} />
                  <text x={lx} y={ly} dy="4" textAnchor={anchor} className="skill-label" fill={node.data.dim ? "#6d7f74" : "#e7f6ee"}>
                    {node.data.name}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
        {tip && (
          <div className="tip" style={{ left: tip.x, top: tip.y }}>
            <strong>{tip.title}</strong>
            <span>{tip.body}</span>
          </div>
        )}
      </div>
      <h1 className="stage-title">skills</h1>
    </div>
  )
}

function branch(aAngle: number, aRadius: number, bAngle: number, bRadius: number): string {
  const [x1, y1] = d3.pointRadial(aAngle, aRadius)
  const [x2, y2] = d3.pointRadial(bAngle, bRadius)
  const [cx, cy] = d3.pointRadial(bAngle, (aRadius + bRadius) / 2)
  return `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`
}

function labelAnchor(angle: number): "start" | "end" | "middle" {
  const deg = (angle * 180) / Math.PI
  if (deg > 25 && deg < 155) return "start"
  if (deg > 205 && deg < 335) return "end"
  return "middle"
}
