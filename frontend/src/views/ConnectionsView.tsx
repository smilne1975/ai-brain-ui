import { useMemo, useState } from "react"
import type { Brain, Connection, Selection } from "../types"
import { matchesQuery, projectName, statusLabel } from "../format"

type Props = {
  brain: Brain
  query: string
  focus: string | null
  selection: Selection | null
  onSelect: (selection: Selection) => void
}

export function ConnectionsView({ brain, query, focus, selection, onSelect }: Props) {
  const [category, setCategory] = useState("All")
  const categories = ["All", ...Array.from(new Set(brain.connections.map((item) => item.category)))]

  const visible = useMemo(() => {
    return brain.connections.filter((item) => {
      if (category !== "All" && item.category !== category) return false
      if (focus && item.status !== "absent" && !item.projects.includes(focus)) return false
      if (focus && item.status === "absent") return false
      return matchesQuery(query, `${item.name} ${item.category} ${item.description}`)
    })
  }, [brain.connections, category, focus, query])

  const seen = visible.filter((item) => item.status !== "absent")
  const absent = visible.filter((item) => item.status === "absent")
  const live = brain.connections.filter((item) => item.status === "connected").length
  const referenced = brain.connections.filter((item) => item.status === "referenced").length

  return (
    <div className="conn-page">
      <header className="conn-head">
        <div>
          <p className="eyebrow">Services and APIs</p>
          <h1>connections</h1>
        </div>
        <p className="conn-count">
          {live} connected · {referenced} referenced
          {focus ? ` · focused on ${projectName(brain, focus)}` : ""}
        </p>
      </header>
      <div className="chips">
        {categories.map((item) => (
          <button key={item} type="button" className={category === item ? "on" : ""} onClick={() => setCategory(item)}>
            {item}
          </button>
        ))}
      </div>
      <Section title="Seen in your folders" items={seen} brain={brain} selection={selection} onSelect={onSelect} />
      {!focus && <Section title="Not seen here" items={absent} brain={brain} selection={selection} onSelect={onSelect} />}
      {focus && (
        <p className="quiet conn-note">
          {brain.connections.filter((item) => item.status === "absent").length} catalog services are not used in this folder.
        </p>
      )}
      {seen.length === 0 && absent.length === 0 && <p className="empty-copy">Nothing in the catalog matches that filter.</p>}
    </div>
  )
}

function Section({
  title,
  items,
  brain,
  selection,
  onSelect,
}: {
  title: string
  items: Connection[]
  brain: Brain
  selection: Selection | null
  onSelect: (selection: Selection) => void
}) {
  if (!items.length) return null
  return (
    <section className="conn-section">
      <h2>{title}</h2>
      <div className="conn-grid">
        {items.map((item) => {
          const selected = selection?.kind === "connection" && selection.id === item.id
          const live = item.live_projects.map((id) => projectName(brain, id))
          const mentioned = item.projects.filter((id) => !item.live_projects.includes(id)).map((id) => projectName(brain, id))
          return (
            <button
              key={item.id}
              id={`conn-${item.id}`}
              type="button"
              className={`conn-card status-${item.status}${selected ? " selected" : ""}`}
              onClick={() => onSelect({ kind: "connection", id: item.id })}
            >
              <div className="conn-top">
                <span className="monogram" aria-hidden>
                  {item.name.slice(0, 2).toUpperCase()}
                </span>
                <div>
                  <h3>{item.name}</h3>
                  <p>{item.description}</p>
                </div>
              </div>
              <div className="conn-meta">
                <span className={`pill pill-${item.status}`}>{statusLabel(item.status)}</span>
                <span className="quiet">{whereLine(item, live, mentioned)}</span>
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function whereLine(item: Connection, live: string[], mentioned: string[]): string {
  if (item.status === "absent") return item.category
  if (live.length && mentioned.length) return `Key in ${live.join(", ")} · mentioned in ${mentioned.join(", ")}`
  if (live.length) return `Key in ${live.join(", ")}`
  if (mentioned.length) return `Mentioned in ${mentioned.join(", ")}`
  return item.category
}
