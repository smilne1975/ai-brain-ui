import { useEffect, useMemo, useState } from "react"
import { fetchBrain, fetchCards, fetchChats, fetchStatus, fetchTimeline, rescan } from "./api"
import { Drawer } from "./components/Drawer"
import { formatWhen, matchesQuery, projectName } from "./format"
import type { Brain, BrainStatus, CardBoard, ChatIndex, Selection, Timeline, View } from "./types"
import { BlueprintView } from "./views/BlueprintView"
import { CardsView } from "./views/CardsView"
import { ConnectionsView } from "./views/ConnectionsView"
import { SkillsView } from "./views/SkillsView"
import { SystemView } from "./views/SystemView"
import { TimelineView } from "./views/TimelineView"

const VIEWS: { id: View; label: string; hint: string }[] = [
  { id: "skills", label: "Skills", hint: "1" },
  { id: "blueprint", label: "Blueprint", hint: "2" },
  { id: "system", label: "System", hint: "3" },
  { id: "connections", label: "Connections", hint: "4" },
  { id: "timeline", label: "Timeline", hint: "5" },
  { id: "cards", label: "Cards", hint: "6" },
]

function readView(): View {
  const hash = window.location.hash.replace(/^#\/?/, "")
  return VIEWS.some((view) => view.id === hash) ? (hash as View) : "skills"
}

type Hit = { kind: Selection["kind"]; id: string; label: string; meta: string }

export default function App() {
  const [brain, setBrain] = useState<Brain | null>(null)
  const [status, setStatus] = useState<BrainStatus | null>(null)
  const [error, setError] = useState("")
  const [view, setView] = useState<View>(readView)
  const [query, setQuery] = useState("")
  const [searchOpen, setSearchOpen] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [scanning, setScanning] = useState(true)
  const [pollEpoch, setPollEpoch] = useState(0)
  const [timelineDays, setTimelineDays] = useState<1 | 7 | 30>(7)
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [timelineError, setTimelineError] = useState("")
  const [cards, setCards] = useState<CardBoard | null>(null)
  const [cardsLoading, setCardsLoading] = useState(false)
  const [cardsError, setCardsError] = useState("")
  const [chats, setChats] = useState<ChatIndex | null>(null)

  useEffect(() => {
    if (!window.location.hash) history.replaceState(null, "", "#/skills")
    const onHash = () => setView(readView())
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  useEffect(() => {
    let cancel = false
    let timer = 0
    const pull = () => {
      fetchStatus()
        .then((next) => {
          if (cancel) return
          setStatus(next)
          if (next.phase === "error") {
            setError(next.error || next.message || "The folder could not be scanned.")
            setScanning(false)
            return
          }
          if (next.phase === "ready") {
            fetchBrain()
              .then((mapped) => {
                if (cancel) return
                setBrain(mapped)
                setError("")
                setScanning(false)
              })
              .catch((reason: unknown) => {
                if (!cancel) setError(reason instanceof Error ? reason.message : "The folder could not be scanned.")
              })
            return
          }
          setScanning(true)
          timer = window.setTimeout(pull, 700)
        })
        .catch((reason: unknown) => {
          if (!cancel) setError(reason instanceof Error ? reason.message : "AI Brain is not responding.")
        })
    }
    pull()
    return () => {
      cancel = true
      window.clearTimeout(timer)
    }
  }, [pollEpoch])

  useEffect(() => {
    const source = new EventSource("/api/events")
    source.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as BrainStatus & { type?: string }
        if (message.type === "progress") {
          setStatus((prev) => ({
            ok: false,
            phase: message.phase || prev?.phase || "scanning",
            root: message.root || prev?.root || "",
            root_name: message.root_name || prev?.root_name,
            message: message.message || prev?.message || "Reading folders",
            files: message.files ?? prev?.files ?? 0,
            projects: message.projects ?? prev?.projects ?? 0,
            current: message.current || "",
            generation: message.generation ?? prev?.generation,
          }))
          if (message.phase === "scanning") setScanning(true)
        }
        if (message.type === "updated") {
          fetchBrain()
            .then((mapped) => {
              setBrain(mapped)
              setError("")
              setScanning(false)
            })
            .catch(() => undefined)
          fetchStatus()
            .then(setStatus)
            .catch(() => undefined)
        }
      } catch {
        /* ignore malformed events */
      }
    }
    return () => source.close()
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")
      if (event.key === "/" && !typing) {
        event.preventDefault()
        document.getElementById("system-search")?.focus()
      }
      if (event.key === "Escape") {
        setSearchOpen(false)
        setSelection(null)
      }
      if (typing) return
      const index = VIEWS.findIndex((item) => item.hint === event.key)
      if (index >= 0) go(VIEWS[index].id)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const refreshKey = brain ? `${brain.scanned_at}|${brain.summaries}|${brain.stats.files}|${brain.stats.projects}` : ""

  useEffect(() => {
    if (!refreshKey) return
    let cancel = false
    fetchChats()
      .then((data) => {
        if (!cancel) setChats(data)
      })
      .catch(() => {
        if (!cancel) setChats(null)
      })
    return () => {
      cancel = true
    }
  }, [refreshKey])

  useEffect(() => {
    if (!refreshKey || view !== "timeline") return
    let cancel = false
    setTimelineLoading(true)
    setTimelineError("")
    fetchTimeline(timelineDays)
      .then((data) => {
        if (!cancel) setTimeline(data)
      })
      .catch((reason: unknown) => {
        if (!cancel) setTimelineError(reason instanceof Error ? reason.message : "The timeline is not ready.")
      })
      .finally(() => {
        if (!cancel) setTimelineLoading(false)
      })
    return () => {
      cancel = true
    }
  }, [refreshKey, view, timelineDays])

  useEffect(() => {
    if (!refreshKey || view !== "cards") return
    let cancel = false
    setCardsLoading(true)
    setCardsError("")
    fetchCards()
      .then((data) => {
        if (!cancel) setCards(data)
      })
      .catch((reason: unknown) => {
        if (!cancel) setCardsError(reason instanceof Error ? reason.message : "Project cards are not ready.")
      })
      .finally(() => {
        if (!cancel) setCardsLoading(false)
      })
    return () => {
      cancel = true
    }
  }, [refreshKey, view])

  function go(next: View) {
    if (window.location.hash !== `#/${next}`) window.location.hash = `#/${next}`
    setView(next)
  }

  function openOnMap(projectId: string) {
    setFocus(projectId)
    setSelection({ kind: "project", id: projectId })
    go("blueprint")
  }

  async function runRescan() {
    setScanning(true)
    setError("")
    try {
      setStatus(await rescan())
      setPollEpoch((value) => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Rescan failed.")
      setScanning(false)
    }
  }

  const hits = useMemo(() => (brain ? searchHits(brain, query) : []), [brain, query])
  const focused = brain?.projects.find((project) => project.id === focus) ?? null
  const focusedChat = focused ? chats?.sessions.find((session) => session.project_id === focused.id && session.summary) : undefined
  const rootPath = brain?.root || status?.root || ""
  const rootName = brain?.root_name || status?.root_name || folderName(rootPath)

  if (!brain) {
    return (
      <div className="app">
        <aside className="sidebar">
          <Brand />
          <p className="root-name" title={rootPath}>
            {rootName || "Projects"}
          </p>
          <p className="root-path" title={rootPath}>
            {rootPath || "Waiting for the projects folder"}
          </p>
          <p className="whisper">.env values are never read. Key names only.</p>
        </aside>
        <div className="main">
          <p className="mobile-root" title={rootPath}>
            {rootPath || "Waiting for the projects folder"}
          </p>
          <div className="boot">
            <div className="core-pulse boot-core" />
            {error ? (
              <>
                <h1>Can't read that folder</h1>
                <p>{error}</p>
                {rootPath && <p className="root-path solo">{rootPath}</p>}
                <button type="button" className="primary" onClick={() => void runRescan()}>
                  Try again
                </button>
              </>
            ) : (
              <>
                <h1>Walking the folders</h1>
                <p>{status?.message || "Reading scripts, notes, and key names."}</p>
                <p className="boot-count">
                  {status ? `${status.projects} folders · ${status.files} files` : "Starting the scan"}
                </p>
                {status?.current && (
                  <p className="root-path solo" title={status.current}>
                    {status.current}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <Brand />
        <p className="root-name" title={rootPath}>
          {rootName}
        </p>
        <p className="root-path" title={rootPath}>
          {rootPath}
        </p>
        <nav className="nav">
          {VIEWS.map((item) => (
            <button key={item.id} type="button" className={view === item.id ? "active" : ""} onClick={() => go(item.id)}>
              <Icon name={item.id} />
              <span>{item.label}</span>
              <kbd>{item.hint}</kbd>
            </button>
          ))}
        </nav>
        <div className="side-label">Folders</div>
        <div className="project-list">
          <button type="button" className={!focus ? "active" : ""} onClick={() => setFocus(null)}>
            <i className="dot live" />
            <span>All folders</span>
            <em>{brain.stats.projects}</em>
          </button>
          {brain.projects.map((project) => (
            <button
              key={project.id}
              type="button"
              className={focus === project.id ? "active" : ""}
              onClick={() => {
                setFocus(project.id)
                setSelection({ kind: "project", id: project.id })
              }}
            >
              <i className="dot" />
              <span>{project.name}</span>
              <em>{project.stats.files}</em>
            </button>
          ))}
        </div>
        <div className="side-foot">
          <i className={brain.provider.mode === "heuristic" ? "dot" : "dot live"} />
          <div>
            <strong>{brain.provider.label}</strong>
            <p>
              {brain.provider.mode === "heuristic"
                ? "No model key in the environment."
                : brain.summaries === "model"
                  ? "Folder summaries came from the model."
                  : "Index first. Model summaries land when the call returns."}
            </p>
          </div>
        </div>
        <p className="whisper">.env values are never read. Key names only.</p>
        {brain.truncated && <p className="whisper">File cap reached. Some files were left out.</p>}
      </aside>
      <div className={focused ? "main has-focus" : "main"}>
        <p className="mobile-root" title={rootPath}>
          {rootPath}
        </p>
        <header className="topbar">
          <p className="crumb">
            CORPUS <span>/ {view}</span>
          </p>
          <div className="search">
            <svg viewBox="0 0 24 24" aria-hidden>
              <circle cx="11" cy="11" r="6" />
              <path d="M16 16l4 4" />
            </svg>
            <input
              id="system-search"
              value={query}
              placeholder="Search the system"
              aria-label="Search the system"
              onChange={(event) => {
                setQuery(event.target.value)
                setSearchOpen(true)
              }}
              onFocus={() => setSearchOpen(true)}
            />
            {searchOpen && query.trim() && (
              <div className="search-pop" role="listbox">
                {hits.length === 0 && <p className="quiet">No matches.</p>}
                {hits.map((hit) => (
                  <button
                    key={`${hit.kind}-${hit.id}`}
                    type="button"
                    onClick={() => {
                      chooseHit(hit, go, setFocus, setSelection, setSearchOpen)
                    }}
                  >
                    <span className="kicker">{hit.kind}</span>
                    <strong>{hit.label}</strong>
                    <em>{hit.meta}</em>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="button" className="ghost" onClick={() => void runRescan()} disabled={scanning}>
            {scanning ? "Mapping" : "Rescan"}
          </button>
          <span className="live-pill" title={`Scanned ${formatWhen(brain.scanned_at)}`}>
            <i /> watching
          </span>
        </header>
        {focused && (
          <div className="focusbar">
            <span>
              Focused on <b>{focused.name}</b> · {focused.stats.files} files · {focused.stats.lines} lines
              {focusedChat ? <em className="focus-why">Why · {focusedChat.summary}</em> : null}
            </span>
            <button type="button" onClick={() => go("blueprint")}>
              Blueprint
            </button>
            <button type="button" onClick={() => setFocus(null)}>
              All folders
            </button>
          </div>
        )}
        <div className="stage">
          {view === "skills" && (
            <SkillsView brain={brain} query={query} focus={focus} selection={selection} onSelect={setSelection} />
          )}
          {view === "blueprint" && (
            <BlueprintView brain={brain} query={query} focus={focus} onFocus={setFocus} onSelect={setSelection} />
          )}
          {view === "system" && (
            <SystemView brain={brain} query={query} focus={focus} selection={selection} onSelect={setSelection} />
          )}
          {view === "connections" && (
            <ConnectionsView brain={brain} query={query} focus={focus} selection={selection} onSelect={setSelection} />
          )}
          {view === "timeline" && (
            <TimelineView
              brain={brain}
              data={timeline}
              loading={timelineLoading}
              error={timelineError}
              days={timelineDays}
              query={query}
              focus={focus}
              onDays={setTimelineDays}
              onOpenProject={openOnMap}
            />
          )}
          {view === "cards" && (
            <CardsView
              brain={brain}
              data={cards}
              chats={chats}
              loading={cardsLoading}
              error={cardsError}
              query={query}
              focus={focus}
              onOpenProject={openOnMap}
              onOpenFile={(id) => setSelection({ kind: "file", id })}
            />
          )}
        </div>
      </div>
      <Drawer
        brain={brain}
        chats={chats}
        selection={selection}
        onClose={() => setSelection(null)}
        onOpenFile={(id) => setSelection({ kind: "file", id })}
        onFocus={setFocus}
        onViewBlueprint={() => go("blueprint")}
      />
      <nav className="tabbar">
        {VIEWS.map((item) => (
          <button key={item.id} type="button" className={view === item.id ? "active" : ""} onClick={() => go(item.id)}>
            <Icon name={item.id} />
            {item.label}
          </button>
        ))}
      </nav>
    </div>
  )
}

function folderName(path: string) {
  const parts = path.split(/[/\\]/).filter(Boolean)
  return parts[parts.length - 1] || ""
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark" aria-hidden />
      <div>
        <strong>AI Brain</strong>
        <p>local corpus</p>
      </div>
    </div>
  )
}

function chooseHit(
  hit: Hit,
  go: (view: View) => void,
  setFocus: (id: string | null) => void,
  setSelection: (selection: Selection) => void,
  setSearchOpen: (open: boolean) => void,
) {
  setSelection({ kind: hit.kind, id: hit.id })
  setSearchOpen(false)
  if (hit.kind === "skill") go("skills")
  if (hit.kind === "connection") go("connections")
  if (hit.kind === "file") go("system")
  if (hit.kind === "project") {
    setFocus(hit.id)
    go("blueprint")
  }
}

function searchHits(brain: Brain, query: string): Hit[] {
  const q = query.trim()
  if (!q) return []
  const hits: Hit[] = []
  for (const project of brain.projects) {
    if (matchesQuery(q, `${project.name} ${project.summary}`)) {
      hits.push({ kind: "project", id: project.id, label: project.name, meta: `${project.stats.files} files` })
    }
  }
  for (const skill of brain.skills) {
    if (matchesQuery(q, `${skill.name} ${skill.category} ${skill.blurb}`)) {
      hits.push({ kind: "skill", id: skill.id, label: skill.name, meta: skill.category })
    }
  }
  for (const item of brain.connections) {
    if (item.status === "absent") continue
    if (matchesQuery(q, `${item.name} ${item.description}`)) {
      hits.push({ kind: "connection", id: item.id, label: item.name, meta: item.status })
    }
  }
  for (const file of brain.files) {
    if (matchesQuery(q, `${file.rel} ${file.summary}`)) {
      hits.push({
        kind: "file",
        id: file.id,
        label: file.rel,
        meta: projectName(brain, file.project_id),
      })
    }
  }
  return hits.slice(0, 8)
}

function Icon({ name }: { name: View }) {
  if (name === "skills") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="2.2" />
        <circle cx="5" cy="7" r="1.3" />
        <circle cx="18" cy="6" r="1.3" />
        <circle cx="19" cy="16" r="1.3" />
        <circle cx="7" cy="18" r="1.3" />
        <path d="M12 12L5 7M12 12l6-6M12 12l7 4M12 12L7 18" />
      </svg>
    )
  }
  if (name === "blueprint") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <rect x="4" y="3" width="10" height="6" rx="1" />
        <rect x="10" y="15" width="10" height="6" rx="1" />
        <path d="M9 9v3h6v3" />
      </svg>
    )
  }
  if (name === "system") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      </svg>
    )
  }
  if (name === "timeline") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="7" />
        <path d="M12 8v5l3 2" />
      </svg>
    )
  }
  if (name === "cards") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <rect x="4" y="6" width="8" height="12" rx="1.2" />
        <rect x="12" y="6" width="8" height="12" rx="1.2" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <rect x="3" y="4" width="8" height="6" rx="1" />
      <rect x="13" y="4" width="8" height="6" rx="1" />
      <rect x="3" y="14" width="8" height="6" rx="1" />
      <rect x="13" y="14" width="8" height="6" rx="1" />
    </svg>
  )
}
