import { useState } from "react"
import { ChatHistory, sessionsFor } from "../components/ChatHistory"
import type { Brain, CardBoard, ChatIndex, ProjectCard } from "../types"
import { formatWhen, matchesQuery, projectName } from "../format"

type Filter = "all" | "active" | "stale" | "abandoned"

type Props = {
  brain: Brain
  data: CardBoard | null
  chats: ChatIndex | null
  loading: boolean
  error: string
  query: string
  focus: string | null
  onOpenProject: (id: string) => void
  onOpenFile: (id: string) => void
}

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "stale", label: "Stale" },
  { id: "abandoned", label: "Abandoned" },
]

export function CardsView({ brain, data, chats, loading, error, query, focus, onOpenProject, onOpenFile }: Props) {
  const [filter, setFilter] = useState<Filter>("all")
  const cards = (data?.cards ?? []).filter((card) => {
    if (focus && card.project_id !== focus) return false
    if (filter !== "all" && card.activity !== filter) return false
    const langs = card.languages.map((item) => item.name).join(" ")
    const unfinished = [
      ...card.unfinished.stubs,
      ...card.unfinished.empty,
      ...card.unfinished.missing_requirements,
    ].join(" ")
    const chatText = sessionsFor(chats?.sessions, card.project_id)
      .map((session) => `${session.title} ${session.prompt} ${session.summary}`)
      .join(" ")
    return matchesQuery(query, `${card.name} ${card.blurb} ${card.entry?.how ?? ""} ${langs} ${unfinished} ${chatText}`)
  })

  return (
    <div className="conn-page">
      <header className="conn-head">
        <div>
          <p className="eyebrow">Plain English</p>
          <h1>project status</h1>
        </div>
        <p className="conn-count">
          {cards.length} folder{cards.length === 1 ? "" : "s"}
          {focus ? ` · ${projectName(brain, focus)}` : ""}
          {data?.source === "model" ? " · model" : data?.source === "mixed" ? " · mixed" : ""}
        </p>
      </header>
      <div className="chips" role="tablist" aria-label="Activity filter">
        {FILTERS.map((item) => (
          <button key={item.id} type="button" className={filter === item.id ? "on" : ""} onClick={() => setFilter(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <p className="quiet tl-note">
        Active is the last 7 days, stale is 30, and older than that is abandoned. Runs means a way to start it was found. Copilot chat stays on this machine.
        {chats && !chats.enabled ? " Chat history is off (BRAIN_COPILOT_CHATS=0)." : ""} .env values are never read.
      </p>
      {error && <p className="ask-error">{error}</p>}
      {loading && !data && <p className="empty-copy">Reading project cards…</p>}
      {!loading && !error && cards.length === 0 && <p className="empty-copy">No folder matches that filter.</p>}
      <div className="card-grid">
        {cards.map((card) => (
          <article key={card.project_id} className={`status-card activity-${card.activity}`}>
            <div className="status-top">
              <button type="button" className="tl-jump" onClick={() => onOpenProject(card.project_id)}>
                {card.name}
                <span>map</span>
              </button>
              <div className="status-pills">
                <em className={`pill pill-${card.activity}`}>{labelFor(card.activity)}</em>
                <em className={`pill pill-${card.run}`}>{card.run === "runs" ? "Runs" : "Unknown"}</em>
              </div>
            </div>
            <p className="status-blurb">{card.blurb}</p>
            <ChatHistory
              enabled={Boolean(chats?.enabled)}
              sessions={sessionsFor(chats?.sessions, card.project_id)}
              onOpenFile={onOpenFile}
            />
            <div className="status-run">
              <span>Run</span>
              {card.entry ? <code>{card.entry.how}</code> : <em>No entry point found</em>}
            </div>
            <HalfFinished card={card} />
            <footer className="status-foot">
              <span>{card.last_touched ? `Touched ${formatWhen(card.last_touched)}` : "No save time"}</span>
              <span>
                {card.files} file{card.files === 1 ? "" : "s"}
                {card.languages.length ? ` · ${card.languages.map((item) => `${item.name} ${item.count}`).join(" · ")}` : ""}
              </span>
            </footer>
          </article>
        ))}
      </div>
    </div>
  )
}

function HalfFinished({ card }: { card: ProjectCard }) {
  const { todos, fixmes, stubs, empty, missing_requirements: missing } = card.unfinished
  const quiet = todos + fixmes + stubs.length + empty.length + missing.length === 0
  if (quiet) return <p className="status-half quiet">Nothing obvious left unfinished.</p>
  return (
    <div className="status-half">
      <span>Half-finished</span>
      <ul>
        {todos > 0 && (
          <li>
            {todos} TODO{todos === 1 ? "" : "s"}
          </li>
        )}
        {fixmes > 0 && (
          <li>
            {fixmes} FIXME{fixmes === 1 ? "" : "s"}
          </li>
        )}
        {stubs.map((rel) => (
          <li key={rel}>Stub {rel}</li>
        ))}
        {empty.map((rel) => (
          <li key={rel}>Empty {rel}</li>
        ))}
        {missing.length > 0 && <li>Missing requirements: {missing.join(", ")}</li>}
      </ul>
    </div>
  )
}

function labelFor(activity: ProjectCard["activity"]) {
  if (activity === "active") return "Active"
  if (activity === "stale") return "Stale"
  return "Abandoned"
}
