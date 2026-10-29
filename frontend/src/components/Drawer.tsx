import { saveHandoff } from "../api"
import { BriefBlock, briefFor } from "./BriefBlock"
import { Keyins } from "./Keyins"
import { ChatHistory, sessionsFor } from "./ChatHistory"
import type { Brain, BriefBoard, ChatIndex, Selection } from "../types"
import { connectionById, fileById, projectName, skillById, statusLabel } from "../format"

type Props = {
  brain: Brain
  chats: ChatIndex | null
  briefs: BriefBoard | null
  selection: Selection | null
  onClose: () => void
  onOpenFile: (id: string) => void
  onFocus: (id: string | null) => void
  onViewBlueprint: () => void
}

export function Drawer({ brain, chats, briefs, selection, onClose, onOpenFile, onFocus, onViewBlueprint }: Props) {
  if (!selection) return null
  return (
    <aside className="drawer" role="dialog" aria-label="Detail">
      <button type="button" className="drawer-close" onClick={onClose} aria-label="Close detail">
        Close
      </button>
      {selection.kind === "project" && (
        <ProjectBody
          brain={brain}
          chats={chats}
          briefs={briefs}
          id={selection.id}
          onFocus={onFocus}
          onViewBlueprint={onViewBlueprint}
          onOpenFile={onOpenFile}
        />
      )}
      {selection.kind === "file" && <FileBody brain={brain} id={selection.id} onFocus={onFocus} />}
      {selection.kind === "skill" && <SkillBody brain={brain} id={selection.id} onOpenFile={onOpenFile} onFocus={onFocus} />}
      {selection.kind === "connection" && <ConnectionBody brain={brain} id={selection.id} onOpenFile={onOpenFile} onFocus={onFocus} />}
    </aside>
  )
}

function ProjectBody({
  brain,
  chats,
  briefs,
  id,
  onFocus,
  onViewBlueprint,
  onOpenFile,
}: {
  brain: Brain
  chats: ChatIndex | null
  briefs: BriefBoard | null
  id: string
  onFocus: (id: string | null) => void
  onViewBlueprint: () => void
  onOpenFile: (id: string) => void
}) {
  const project = brain.projects.find((item) => item.id === id)
  if (!project) return <p>That folder is no longer in the scan.</p>
  const files = brain.files.filter((file) => file.project_id === id)
  return (
    <>
      <p className="eyebrow">Folder</p>
      <h2>{project.name}</h2>
      <p className="lede">{project.summary}</p>
      {project.microstation ? <p className="quiet">MicroStation Python · MSPy</p> : null}
      <Keyins report={project.microstation} onOpenFile={onOpenFile} />
      <p className="quiet">Summary from {project.summary_source === "model" ? "the model" : "the local index"}.</p>
      <div className="stat-row">
        <Stat n={project.stats.files} label="files" />
        <Stat n={project.stats.lines} label="lines" />
        <Stat n={project.stats.todos} label="todos" />
      </div>
      {briefFor(briefs?.briefs, id) && (
        <BriefBlock
          brief={briefFor(briefs?.briefs, id)!}
          onOpenFile={onOpenFile}
          onSave={async () => {
            await saveHandoff(id)
          }}
        />
      )}
      <ChatHistory enabled={Boolean(chats?.enabled)} sessions={sessionsFor(chats?.sessions, id)} onOpenFile={onOpenFile} />
      {!chats?.enabled && <p className="quiet">Copilot chat history is off. Set BRAIN_COPILOT_CHATS=1 to read local logs.</p>}
      <div className="drawer-actions">
        <button
          type="button"
          className="primary"
          onClick={() => {
            onFocus(id)
            onViewBlueprint()
          }}
        >
          Open blueprint
        </button>
      </div>
      {project.stats.env_keys.length > 0 && (
        <>
          <h3>Env key names</h3>
          <div className="chips">
            {project.stats.env_keys.map((key) => (
              <span key={key} className="chip">
                {key}
              </span>
            ))}
          </div>
          <p className="quiet">Values are not loaded.</p>
        </>
      )}
      <h3>Files</h3>
      <ul className="link-list">
        {files.map((file) => (
          <li key={file.id}>
            <button type="button" onClick={() => onOpenFile(file.id)}>
              <strong>{file.rel}</strong>
              <span>{file.summary}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

function FileBody({ brain, id, onFocus }: { brain: Brain; id: string; onFocus: (id: string | null) => void }) {
  const file = fileById(brain, id)
  if (!file) return <p>That file is no longer in the scan.</p>
  return (
    <>
      <p className="eyebrow">{file.kind}</p>
      <h2>{file.rel}</h2>
      <p className="quiet">{projectName(brain, file.project_id)} · {file.lines} lines</p>
      <p className="lede">{file.summary}</p>
      <div className="drawer-actions">
        <button type="button" onClick={() => onFocus(file.project_id)}>
          Focus folder
        </button>
      </div>
      {file.env_keys.length > 0 && (
        <>
          <h3>Key names</h3>
          <div className="chips">
            {file.env_keys.map((key) => (
              <span key={key} className="chip">
                {key}
              </span>
            ))}
          </div>
          <p className="quiet">Values from env files are never stored or shown.</p>
        </>
      )}
      {file.skills.length > 0 && (
        <>
          <h3>Skills</h3>
          <div className="chips">
            {file.skills.map((skill) => (
              <span key={skill} className="chip">
                {skillById(brain, skill)?.name ?? skill}
              </span>
            ))}
          </div>
        </>
      )}
      {file.todos.length > 0 && (
        <>
          <h3>Unfinished</h3>
          <ul className="todo-list">
            {file.todos.map((todo) => (
              <li key={`${todo.line}-${todo.text}`}>
                <span>L{todo.line}</span>
                {todo.text}
              </li>
            ))}
          </ul>
        </>
      )}
      {file.excerpt && (
        <>
          <h3>Excerpt</h3>
          <pre>{file.excerpt}</pre>
        </>
      )}
    </>
  )
}

function SkillBody({
  brain,
  id,
  onOpenFile,
  onFocus,
}: {
  brain: Brain
  id: string
  onOpenFile: (id: string) => void
  onFocus: (id: string | null) => void
}) {
  const skill = skillById(brain, id)
  if (!skill) return <p>That skill is no longer in the scan.</p>
  return (
    <>
      <p className="eyebrow">{skill.category}</p>
      <h2>{skill.name}</h2>
      <p className="lede">{skill.blurb}</p>
      <p className="quiet">{skill.score} matching files</p>
      <h3>Folders</h3>
      <div className="chips">
        {skill.projects.map((projectId) => (
          <button key={projectId} type="button" className="chip" onClick={() => onFocus(projectId)}>
            {projectName(brain, projectId)}
          </button>
        ))}
      </div>
      <h3>Evidence</h3>
      <ul className="link-list">
        {skill.files.map((file) => (
          <li key={file.file_id}>
            <button type="button" onClick={() => onOpenFile(file.file_id)}>
              <strong>
                {projectName(brain, file.project_id)}/{file.rel}
              </strong>
              <span>{file.line || "Matched in this file"}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

function ConnectionBody({
  brain,
  id,
  onOpenFile,
  onFocus,
}: {
  brain: Brain
  id: string
  onOpenFile: (id: string) => void
  onFocus: (id: string | null) => void
}) {
  const item = connectionById(brain, id)
  if (!item) return <p>That service is no longer in the scan.</p>
  return (
    <>
      <p className="eyebrow">{item.category}</p>
      <h2>{item.name}</h2>
      <p className="lede">{item.description}</p>
      <span className={`pill pill-${item.status}`}>{statusLabel(item.status)}</span>
      {item.evidence.length > 0 && (
        <>
          <h3>Where it showed up</h3>
          <ul className="link-list">
            {item.evidence.map((hit) => (
              <li key={`${hit.file_id}-${hit.how}`}>
                <button type="button" onClick={() => onOpenFile(hit.file_id)}>
                  <strong>
                    {projectName(brain, hit.project_id)}/{hit.rel}
                  </strong>
                  <span>{hit.how}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {item.projects.length > 0 && (
        <div className="drawer-actions">
          {item.projects.map((projectId) => (
            <button key={projectId} type="button" onClick={() => onFocus(projectId)}>
              Focus {projectName(brain, projectId)}
            </button>
          ))}
        </div>
      )}
    </>
  )
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div className="stat">
      <strong>{n}</strong>
      <span>{label}</span>
    </div>
  )
}
