import { useEffect, useState } from "react"
import { approveKnowledge, fetchKnowledge, previewKnowledge, reviewKnowledge, saveReviewedSkill } from "../api"
import type { Brain, KnowledgeIndex, KnowledgePreview } from "../types"
import { MeetingInbox } from "../components/MeetingInbox"
import { WebClipInbox } from "../components/WebClipInbox"
import { Deliverables } from "../components/Deliverables"
import { WorkflowEvents } from "../components/WorkflowEvents"
import { VoiceInbox } from "../components/VoiceInbox"
import { ObsidianExport } from "../components/ObsidianExport"
import { ProjectRecords } from "../components/ProjectRecords"
import { SourceReview } from "../components/SourceReview"
import { CaptureInbox } from "../components/CaptureInbox"

export function KnowledgeView({ brain, focus }: { brain: Brain; focus: string | null }) {
  const [index, setIndex] = useState<KnowledgeIndex | null>(null)
  const [draft, setDraft] = useState<KnowledgePreview | null>(null)
  const [content, setContent] = useState("")
  const [checked, setChecked] = useState<({ draft: KnowledgePreview; content: string } & Awaited<ReturnType<typeof reviewKnowledge>>) | null>(null)
  const [message, setMessage] = useState("")
  const [skill, setSkill] = useState({ project_id: "", name: "", description: "", steps: "" })
  const [topicProject, setTopicProject] = useState("")
  const [topic, setTopic] = useState("")
  const [topicSources, setTopicSources] = useState<string[]>([])
  const [meetingProject, setMeetingProject] = useState("")
  const [clipRevision, setClipRevision] = useState(0)
  useEffect(() => { void fetchKnowledge().then(setIndex).catch((err: Error) => setMessage(err.message)) }, [brain.scanned_at])

  const visible = brain.projects.filter((project) => !focus || project.id === focus)
  const currentReview = checked?.draft === draft && checked?.content === content ? checked : null
  const findings = currentReview?.findings ?? null
  const unavailableSources = draft?.source_ids?.filter((id) => !draft.sources.some((source) => source.id === id)) ?? []
  async function load(id: string, pageTopic?: string | null, sourceIds?: string[]) {
    try { const next = await previewKnowledge(id, pageTopic ?? undefined, sourceIds); setDraft(next); setContent(next.content); setMessage("") }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not preview") }
  }
  async function approve() {
    if (!draft || !findings || findings.some((item) => item.blocking)) return
    const warnings = findings.length ? ` Accept ${findings.length} non-blocking warning(s).` : ""
    if (!window.confirm(`Save reviewed knowledge for ${draft.title}? Source files will not change.${warnings}`)) return
    try {
      await approveKnowledge(draft.project_id, content, draft.current_revision,
        Object.fromEntries(draft.sources.map((source) => [source.id, source.sha256])), draft.topic, draft.source_ids)
      setIndex(await fetchKnowledge()); setDraft(null); setMessage("Reviewed page saved as a new immutable revision.")
    } catch (err) { setMessage(err instanceof Error ? err.message : "Could not save") }
  }

  return <div className="view knowledge-view">
    <h1>Project knowledge</h1>
    <p className="quiet">Local, source-backed drafts. Nothing is written to a project file; you review each page before it becomes available to Ask.</p>
    {message && <p role="status">{message}</p>}
    <div className="knowledge-grid">
      <section><h2>Project pages</h2>
        {visible.map((project) => {
          const page = index?.pages.find((item) => item.project_id === project.id && !item.topic)
          const topics = index?.pages.filter((item) => item.project_id === project.id && item.topic) ?? []
          return <div key={project.id} className="knowledge-card">
            <strong>{project.name}</strong> <span className="quiet">{page ? `${page.revisions.length} version(s)` : "not created"}</span>
            {page?.stale_sources.length ? <p className="knowledge-warning">{page.stale_sources.length} source(s) changed or missing</p> : null}
            <p>{page?.content.slice(0, 220) || project.summary}</p>
            <button type="button" className="ghost" onClick={() => void load(project.id)}>{page ? "Review update" : "Preview page"}</button>
            {topics.map((item) => <div key={item.page_id}><button type="button" className="ghost"
              onClick={() => void load(project.id, item.topic, item.sources.map((source) => source.id))}>
              {item.title}{item.stale_sources.length ? " · needs recheck" : ""}</button></div>)}
            <button type="button" className="ghost" onClick={() => { setTopicProject(project.id); setTopic(""); setTopicSources([]) }}>New topic page</button>
            {topicProject === project.id && <div className="knowledge-topic">
              <input aria-label="Topic title" placeholder="Topic, e.g. level export" value={topic} onChange={(e) => setTopic(e.target.value)} />
               <p className="quiet">Choose project files and approved web clips for this topic (up to 20):</p>
               <div className="knowledge-source-list">{[
                 ...brain.files.filter((file) => file.project_id === project.id && !file.env_class).map((file) => ({ id: file.id, label: file.rel })),
                 ...(index?.available_clips ?? []).filter((clip) => clip.project_id === project.id).map((clip) => ({ id: clip.id, label: `Web clip: ${clip.title}` })),
               ].map((source) => <label key={source.id}><input type="checkbox" checked={topicSources.includes(source.id)}
                 disabled={topicSources.length >= 20 && !topicSources.includes(source.id)} onChange={(e) =>
                   setTopicSources((before) => e.target.checked ? [...before, source.id] : before.filter((id) => id !== source.id))} />{source.label}</label>)}</div>
              <button type="button" className="primary" disabled={!topic.trim() || !topicSources.length}
                onClick={() => void load(project.id, topic, topicSources)}>Preview topic</button>
            </div>}
          </div>
        })}
      </section>
      <section><h2>{draft ? `Review: ${draft.title}` : "Knowledge checks"}</h2>
        {draft ? <div className="knowledge-card">
          <p>Sources: {draft.sources.length ? draft.sources.map((item, index) => <span key={item.id}>
            {index ? ", " : ""}{item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">{item.title ?? item.rel}</a> : item.rel}</span>) : "None"}</p>
          {draft.warning && <p className="knowledge-warning">{draft.warning}</p>}
          {draft.changed_sources.length > 0 && <p>{draft.changed_sources.length} new or changed indexed source(s).</p>}
          {draft.missing_sources.length > 0 && <p className="knowledge-warning">{draft.missing_sources.length} previous source(s) missing.</p>}
          {!!unavailableSources.length && !!draft.sources.length && <button className="ghost" type="button"
            onClick={() => void load(draft.project_id, draft.topic, draft.sources.map((source) => source.id))}>Preview again without unavailable sources</button>}
          {draft.previous_content && <details><summary>Previous approved version (compare before replacing)</summary>
            <pre className="knowledge-previous">{draft.previous_content}</pre></details>}
          <textarea aria-label="Edit knowledge page before approval" value={content} onChange={(event) => setContent(event.target.value)} rows={18} />
          {findings && <div role="status">
            {findings.length ? <ul>{findings.map((item, index) => <li key={`${item.kind}-${index}`}>
              {item.blocking ? "Fix before approving" : "Review warning"}: {item.detail}</li>)}</ul> : <p>No issues found by the draft checks.</p>}
            <p className="quiet">These checks do not verify whether a source is true.</p>
          </div>}
          {currentReview?.diff && <details><summary>Exact text changes before approval</summary><pre className="knowledge-previous">{currentReview.diff}</pre></details>}
          {currentReview?.diff_limited && <p className="quiet">The change comparison reached its limit. Review the full draft and previous version before approving.</p>}
          <button type="button" className="ghost" onClick={async () => {
            setChecked(null); setMessage("")
            try { const result = await reviewKnowledge(draft, content); setChecked({ draft, content, ...result }) }
            catch (err) { setMessage(err instanceof Error ? err.message : "Could not check the draft") }
          }}>Check draft</button>
          <button type="button" className="primary" disabled={!findings || findings.some((item) => item.blocking)} onClick={() => void approve()}>Approve page</button>
          <button type="button" className="ghost" onClick={() => setDraft(null)}>Cancel</button>
        </div> : <div className="knowledge-card">
          <button type="button" className="ghost" onClick={() => void fetchKnowledge().then(setIndex).catch((err: Error) => setMessage(err.message))}>Run checks</button>
          {index?.findings.length ? index.findings.map((item, n) => <p key={n} className="knowledge-warning">{item.project_id}: {item.detail}</p>) : <p>No broken links or changed sources found in approved pages. This does not verify the truth of source files.</p>}
        </div>}
        <h2>Source changes</h2>
        {!brain.privacy && index && visible.map((project) => <details key={`${project.id}:${brain.scanned_at}`}>
          <summary>{project.name}: source impact plan</summary><SourceReview project={project.id} index={index} load={load} />
        </details>)}
        {index?.source_impact.map((source) => {
          const affected = source.affected.filter((item) => !focus || item.project_id === focus)
          if (!affected.length) return null
          return <div key={source.source_id} className="knowledge-card">
            <strong>{source.source_id}</strong><p className="knowledge-warning">Source {source.status}. Review what depends on it:</p>
            <ul>{affected.map((item) => {
              const page = item.kind === "page" ? index.pages.find((entry) => entry.page_id === item.id) : undefined
              return <li key={`${item.kind}:${item.project_id}:${item.id}`}>
                {page ? <button className="ghost" type="button" onClick={() => void load(page.project_id, page.topic,
                  page.topic || item.move ? page.sources.map((entry) => entry.id === source.source_id && item.move ? item.move.id : entry.id) : undefined)}>
                  {item.project_id}: {item.label}{item.move ? ` · review verified move to ${item.move.rel}` : ""}</button>
                  : <span>{item.project_id}: {item.label} (saved answer)</span>}
              </li>
            })}</ul>
          </div>
        })}
        <h2>Saved answers</h2>
        {index?.answers.filter((item) => !focus || focus === item.project_id).map((item) => <div key={`${item.project_id}-${item.name}`} className="knowledge-card">
          <strong>{item.name}</strong>{item.stale_sources.length ? <span className="knowledge-warning"> · needs recheck</span> : null}
          <p>{item.content.slice(0, 240)}</p>
        </div>)}
      </section>
    </div>
    {brain.coverage && <section className="knowledge-card">
      <h2>Scan coverage</h2>
      <p className="quiet">Last scan: {new Date(brain.scanned_at).toLocaleString()}. These are scan-wide counts; search can miss content outside the scan.</p>
      <p>{brain.coverage.counts.skipped} skipped · {brain.coverage.counts.unreadable} unreadable · {brain.coverage.counts.partial} partially read</p>
      {brain.truncated && <p className="knowledge-warning">The scan hit its file cap. Not all files or folders were checked.</p>}
      <details><summary>Show recorded reasons (up to 200 files)</summary>
        {brain.coverage.issues.filter((item) => !focus || item.project_id === focus).map((item) =>
          <p key={`${item.project_id}:${item.rel}`}><code>{item.project_id}/{item.rel}</code>: {item.reason}</p>)}
      </details>
    </section>}
    {!brain.privacy && <section className="knowledge-card"><h2>Project imports and exports</h2>
      <select aria-label="Import or export project" value={focus ?? meetingProject} disabled={!!focus}
        onChange={(event) => setMeetingProject(event.target.value)}>
        <option value="">Choose project</option>
        {visible.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
      {visible.some((project) => project.id === (focus ?? meetingProject)) && <>
        <details><summary>Capture inbox</summary><CaptureInbox key={focus ?? meetingProject} project={focus ?? meetingProject}
          notes={brain.files.filter((file) => file.project_id === (focus ?? meetingProject) && !file.env_class && file.kind === "markdown")}
          onChange={() => { setClipRevision((n) => n + 1); void fetchKnowledge().then(setIndex).catch((err: Error) => setMessage(err.message)) }} /></details>
        <details><summary>Meeting decisions and actions</summary><MeetingInbox key={focus ?? meetingProject} project={focus ?? meetingProject} /></details>
        <details><summary>Web-clip inbox</summary><WebClipInbox key={`${focus ?? meetingProject}:${clipRevision}`} project={focus ?? meetingProject}
          onChange={() => void fetchKnowledge().then(setIndex).catch((err: Error) => setMessage(err.message))} /></details>
        <details><summary>Tracked Markdown deliverables</summary>{index && <Deliverables key={focus ?? meetingProject}
          project={focus ?? meetingProject} pages={index.pages} />}</details>
        <details><summary>n8n workflow events</summary><WorkflowEvents key={focus ?? meetingProject} project={focus ?? meetingProject} /></details>
        <details><summary>Local voice-note inbox</summary><VoiceInbox key={focus ?? meetingProject} project={focus ?? meetingProject} /></details>
        <details><summary>Obsidian Markdown and Canvas export</summary><ObsidianExport key={focus ?? meetingProject} project={focus ?? meetingProject} /></details>
        <details><summary>Project memory, facts and handoffs</summary><ProjectRecords key={focus ?? meetingProject}
          project={focus ?? meetingProject} scan={brain.scanned_at} clips={index?.available_clips ?? []}
          sources={brain.files.filter((file) => file.project_id === (focus ?? meetingProject) && !file.env_class && file.kind !== "binary")
            .map((file) => ({ id: file.id, label: file.rel }))} /></details>
      </>}
    </section>}
      <section className="knowledge-card"><h2>Reusable skill draft</h2>
      <p className="quiet">Repeated prompts do not prove a workflow succeeded. Steps are suggested only from a reviewed local export that records a successful run and includes evidence. Review all steps; saving never installs or runs a skill.</p>
      {(index?.workflow_candidates ?? []).filter((item) => !focus || item.project_id === focus).map((item) =>
        <details key={`${item.project_id}-${item.name}`}>
          <summary>{item.project_id}: {item.examples[0].text} ({item.sessions} sessions; outcome {item.outcome})</summary>
          <ul>{item.examples.map((example) => <li key={example.session_id}>
            {example.when ? new Date(example.when).toLocaleString() : "Date unknown"} · session <code>{example.session_id}</code>
            <p>{example.text}</p>{!!example.files.length && <p>Referenced files: {example.files.join(", ")}</p>}
            {example.run_outcome && <p>Exported outcome: {example.run_outcome}{example.evidence ? ` — ${example.evidence}` : ""}</p>}
          </li>)}</ul>
          <button type="button" className="ghost" onClick={() => setSkill({ project_id: item.project_id, name: item.name,
            description: item.examples[0].text.slice(0, 180), steps: item.suggested_steps?.map((step, index) => `${index + 1}. ${step}`).join("\n") ?? "" })}>
            {item.suggested_steps?.length ? "Review suggested steps" : "Start a manual draft"}</button>
        </details>)}
      <select aria-label="Skill project" value={skill.project_id} onChange={(e) => setSkill({ ...skill, project_id: e.target.value })}>
        <option value="">Choose project</option>{visible.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
      <input placeholder="Skill name" aria-label="Skill name" value={skill.name} onChange={(e) => setSkill({ ...skill, name: e.target.value })} />
      <input placeholder="When should an agent use it?" aria-label="Skill description" value={skill.description} onChange={(e) => setSkill({ ...skill, description: e.target.value })} />
      <textarea rows={5} placeholder="Reviewed steps and cautions" aria-label="Skill steps" value={skill.steps} onChange={(e) => setSkill({ ...skill, steps: e.target.value })} />
      <button type="button" className="primary" disabled={!skill.project_id || !skill.steps.trim()} onClick={async () => {
        if (!window.confirm("Save this reviewed skill under .brain/skills? It will not be installed automatically.")) return
        try { const saved = await saveReviewedSkill(skill.project_id, skill.name, skill.description, skill.steps); setMessage(`Saved ${saved.path}`) }
        catch (err) { setMessage(err instanceof Error ? err.message : "Could not save skill") }
      }}>Save reviewed skill</button>
    </section>
  </div>
}
