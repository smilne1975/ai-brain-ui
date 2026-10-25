import type { ChatSession } from "../types"
import { formatWhen } from "../format"

type Props = {
  sessions: ChatSession[]
  enabled: boolean
  onOpenFile?: (id: string) => void
}

export function sessionsFor(sessions: ChatSession[] | undefined, projectId: string): ChatSession[] {
  return (sessions ?? []).filter((session) => session.project_id === projectId)
}

export function ChatHistory({ sessions, enabled, onOpenFile }: Props) {
  if (!enabled) return null
  return (
    <section className="why">
      <span>Why / Chat history</span>
      {sessions.length === 0 && <p className="quiet">No Copilot chat matched this folder.</p>}
      {sessions.map((session) => (
        <article key={session.id} className="chat-session">
          <p className="chat-when">
            <time dateTime={session.when ?? undefined}>{session.when ? formatWhen(session.when) : "Undated"}</time>
            <em>{session.title}</em>
          </p>
          {session.prompt ? <p className="chat-prompt">{session.prompt}</p> : <p className="chat-prompt quiet">No user prompt was stored in this log.</p>}
          <p className="chat-summary">{session.summary}</p>
          {session.files.length > 0 && (
            <div className="chat-files">
              {session.files.map((file) =>
                file.file_id && onOpenFile ? (
                  <button key={`${file.file_id}-${file.rel}`} type="button" onClick={() => onOpenFile(file.file_id as string)}>
                    {file.rel}
                  </button>
                ) : (
                  <code key={file.rel}>{file.rel}</code>
                ),
              )}
            </div>
          )}
          <p className="chat-meta">
            {session.summary_source === "model" ? "Model summary" : "Local summary"} · {sourceLabel(session.source)}
          </p>
        </article>
      ))}
    </section>
  )
}

function sourceLabel(source: string): string {
  if (source === "chatSessions") return "chat session"
  if (source === "transcript") return "transcript"
  if (source === "state.vscdb") return "VS Code state"
  if (source === "chatEditingSessions") return "edit session"
  if (source === "globalStorage") return "global storage"
  return source || "Copilot log"
}
