import type { Brain, Timeline } from "../types"
import { matchesQuery, projectName } from "../format"

type WindowDays = 1 | 7 | 30

type Props = {
  brain: Brain
  data: Timeline | null
  loading: boolean
  error: string
  days: WindowDays
  query: string
  focus: string | null
  onDays: (days: WindowDays) => void
  onOpenProject: (id: string) => void
}

const WINDOWS: { id: WindowDays; label: string }[] = [
  { id: 1, label: "Today" },
  { id: 7, label: "7 days" },
  { id: 30, label: "30 days" },
]

export function TimelineView({ brain, data, loading, error, days, query, focus, onDays, onOpenProject }: Props) {
  const weeks = (data?.weeks ?? [])
    .map((week) => ({
      ...week,
      days: week.days
        .map((day) => ({
          ...day,
          projects: day.projects.filter((project) => {
            if (focus && project.project_id !== focus) return false
            const fileText = project.files.map((file) => `${file.rel} ${file.note}`).join(" ")
            return matchesQuery(query, `${project.name} ${project.summary} ${fileText}`)
          }),
        }))
        .filter((day) => day.projects.length > 0),
    }))
    .filter((week) => week.days.length > 0)

  const fileCount = weeks.reduce(
    (sum, week) => sum + week.days.reduce((inner, day) => inner + day.projects.reduce((n, project) => n + project.files.length, 0), 0),
    0,
  )
  const folderCount = new Set(weeks.flatMap((week) => week.days.flatMap((day) => day.projects.map((project) => project.project_id)))).size

  return (
    <div className="conn-page">
      <header className="conn-head">
        <div>
          <p className="eyebrow">Recent work</p>
          <h1>what was I doing?</h1>
        </div>
        <p className="conn-count">
          {data ? `${fileCount} files · ${folderCount} folders` : loading ? "Reading recent files" : "No timeline yet"}
          {focus ? ` · ${projectName(brain, focus)}` : ""}
          {data?.source === "model" ? " · model" : ""}
        </p>
      </header>
      <div className="chips" role="tablist" aria-label="Timeline window">
        {WINDOWS.map((item) => (
          <button key={item.id} type="button" className={days === item.id ? "on" : ""} onClick={() => onDays(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <p className="quiet tl-note">File dates come from save times. A folder that is its own git repo also shows commit subjects. Values in .env files are never read.</p>
      {error && <p className="ask-error">{error}</p>}
      {loading && !data && <p className="empty-copy">Reading recent files…</p>}
      {!loading && !error && weeks.length === 0 && (
        <p className="empty-copy">Nothing changed in this window. Try 30 days, or save a file and rescan.</p>
      )}
      {weeks.map((week) => (
        <section key={week.id} className="tl-week">
          <header className="tl-week-head">
            <h2>{week.label}</h2>
            <span>
              {week.start} – {week.end}
            </span>
          </header>
          {week.days.map((day) => (
            <div key={day.date} className="tl-day">
              <p className="tl-date">{day.label}</p>
              <div className="tl-projects">
                {day.projects.map((project) => (
                  <article key={project.project_id} className="tl-project">
                    <div className="tl-project-top">
                      <button type="button" className="tl-jump" onClick={() => onOpenProject(project.project_id)}>
                        {project.name}
                        <span>map</span>
                      </button>
                      {project.commits[0] && <em>{project.commits[0].subject}</em>}
                    </div>
                    <p className="tl-summary">{project.summary}</p>
                    <ul className="tl-files">
                      {project.files.map((file) => (
                        <li key={`${file.rel}-${file.when}`}>
                          <code>{file.rel}</code>
                          <span>{file.note}</span>
                          <i>{file.via === "both" ? "saved + git" : file.via === "git" ? "git" : "saved"}</i>
                        </li>
                      ))}
                    </ul>
                    {project.more ? <p className="quiet">+{project.more} more files</p> : null}
                  </article>
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
