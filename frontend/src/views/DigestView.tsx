import { useEffect, useState } from "react"
import { exportDigest, fetchDigest } from "../api"
import type { Brain, Digest, DigestProject } from "../types"
import { formatWhen, projectName } from "../format"

type Period = "day" | "week"

type Props = {
  brain: Brain
  focus: string | null
  onOpenProject: (id: string) => void
}

export function DigestView({ brain, focus, onOpenProject }: Props) {
  const [period, setPeriod] = useState<Period>("week")
  const [data, setData] = useState<Digest | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [exportNote, setExportNote] = useState("")
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    setError("")
    fetchDigest(period)
      .then((next) => {
        if (!cancel) setData(next)
      })
      .catch((reason: unknown) => {
        if (!cancel) setError(reason instanceof Error ? reason.message : "The digest is not ready.")
      })
      .finally(() => {
        if (!cancel) setLoading(false)
      })
    return () => {
      cancel = true
    }
  }, [period, brain.scanned_at])

  async function saveAndDownload() {
    setExporting(true)
    setExportNote("")
    try {
      const saved = await exportDigest(period)
      setData(saved)
      downloadMarkdown(saved.markdown, period)
      setExportNote(saved.saved_path ? `Saved ${saved.saved_path}` : "Downloaded the markdown.")
    } catch (reason) {
      if (data?.markdown) {
        downloadMarkdown(data.markdown, period)
        setExportNote("Downloaded the markdown. The server could not write .brain/digests.")
      } else {
        setError(reason instanceof Error ? reason.message : "Could not save the digest.")
      }
    } finally {
      setExporting(false)
    }
  }

  const visible = data
    ? {
        ...data,
        touched: filterProjects(data.touched, focus),
        newly_stale: filterProjects(data.newly_stale, focus),
        newly_abandoned: filterProjects(data.newly_abandoned, focus),
        chats: focus ? data.chats.filter((chat) => chat.project_id === focus) : data.chats,
        focus: focus ? data.focus.filter((item) => item.project_id === focus) : data.focus,
        todos: {
          ...data.todos,
          top: focus ? data.todos.top.filter((item) => item.project_id === focus) : data.todos.top,
        },
      }
    : null

  return (
    <div className="conn-page">
      <header className="conn-head">
        <div>
          <p className="eyebrow">Catch up</p>
          <h1>digest</h1>
        </div>
        <p className="conn-count">
          {visible ? visible.label : loading ? "Reading the window" : "No digest yet"}
          {focus ? ` · ${projectName(brain, focus)}` : ""}
          {data?.source === "model" ? " · model" : ""}
        </p>
      </header>
      <div className="chips" role="tablist" aria-label="Digest period">
        <button type="button" className={period === "day" ? "on" : ""} onClick={() => setPeriod("day")}>
          Today
        </button>
        <button type="button" className={period === "week" ? "on" : ""} onClick={() => setPeriod("week")}>
          This week
        </button>
        <button type="button" onClick={() => void saveAndDownload()} disabled={exporting || !data}>
          {exporting ? "Saving" : "Export markdown"}
        </button>
      </div>
      <p className="quiet tl-note">
        Touched folders come from save times. Stale means the last save crossed 7 days in this window, abandoned means 30. Copilot chats stay on this machine. .env values are never read.
      </p>
      {exportNote && <p className="quiet">{exportNote}</p>}
      {error && <p className="ask-error">{error}</p>}
      {loading && !data && <p className="empty-copy">Reading the digest…</p>}
      {visible && (
        <div className="digest">
          {visible.summary && <p className="brief-doing">{visible.summary}</p>}
          <DigestList title="Projects touched" items={visible.touched} onOpen={onOpenProject} empty="No folder was saved in this window." />
          <DigestList title="Newly stale" items={visible.newly_stale} onOpen={onOpenProject} empty="No folder slipped from active to stale." />
          <DigestList title="Newly abandoned" items={visible.newly_abandoned} onOpen={onOpenProject} empty="No folder slipped to abandoned." />
          <section className="digest-block">
            <h2>
              Open TODOs <em>{visible.todos.open} open · {visible.todos.fixmes} FIXME</em>
            </h2>
            {visible.todos.top.length === 0 && <p className="quiet">None in the scan.</p>}
            <ul className="brief-todos">
              {visible.todos.top.map((item) => (
                <li key={`${item.project_id}-${item.rel}-${item.text}`}>
                  <button type="button" className="tl-jump" onClick={() => onOpenProject(item.project_id)}>
                    {item.project}
                  </button>
                  <i>{item.kind}</i> {item.text}
                  <code>{item.rel}</code>
                </li>
              ))}
            </ul>
          </section>
          <section className="digest-block">
            <h2>Copilot chats</h2>
            {visible.chats.length === 0 && <p className="quiet">No Copilot session in this window.</p>}
            <ul className="tl-chats">
              {visible.chats.map((chat) => (
                <li key={chat.id ?? `${chat.project}-${chat.when}`}>
                  <i>chat</i>
                  <button type="button" className="tl-jump" onClick={() => chat.project_id && onOpenProject(chat.project_id)}>
                    {chat.project}
                    <span>{chat.when ? formatWhen(chat.when) : "undated"}</span>
                  </button>
                  <strong>{chat.prompt || chat.summary}</strong>
                </li>
              ))}
            </ul>
          </section>
          <section className="digest-block">
            <h2>Suggested focus</h2>
            {visible.focus.length === 0 && <p className="quiet">Nothing is asking for attention.</p>}
            <ol className="digest-focus">
              {visible.focus.map((item) => (
                <li key={item.project_id}>
                  <button type="button" className="tl-jump" onClick={() => onOpenProject(item.project_id)}>
                    {item.name}
                    <span>map</span>
                  </button>
                  <p>{item.why}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </div>
  )
}

function DigestList({
  title,
  items,
  empty,
  onOpen,
}: {
  title: string
  items: DigestProject[]
  empty: string
  onOpen: (id: string) => void
}) {
  return (
    <section className="digest-block">
      <h2>
        {title} <em>{items.length}</em>
      </h2>
      {items.length === 0 && <p className="quiet">{empty}</p>}
      <ul className="digest-projects">
        {items.map((item) => (
          <li key={item.project_id}>
            <button type="button" className="tl-jump" onClick={() => onOpen(item.project_id)}>
              {item.name}
              <span>map</span>
            </button>
            {item.detail && <p>{item.detail}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function filterProjects(items: DigestProject[], focus: string | null): DigestProject[] {
  if (!focus) return items
  return items.filter((item) => item.project_id === focus)
}

function downloadMarkdown(markdown: string, period: Period) {
  const blob = new Blob([markdown], { type: "text/markdown" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = period === "day" ? "ai-brain-digest-day.md" : "ai-brain-digest-week.md"
  link.click()
  URL.revokeObjectURL(url)
}
