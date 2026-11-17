import { useEffect, useState } from "react"
import { approveKnowledge, fetchKnowledge, previewKnowledge, saveReviewedSkill } from "../api"
import type { Brain, KnowledgeIndex, KnowledgePreview } from "../types"

export function KnowledgeView({ brain, focus }: { brain: Brain; focus: string | null }) {
  const [index, setIndex] = useState<KnowledgeIndex | null>(null)
  const [draft, setDraft] = useState<KnowledgePreview | null>(null)
  const [content, setContent] = useState("")
  const [message, setMessage] = useState("")
  const [skill, setSkill] = useState({ project_id: "", name: "", description: "", steps: "" })
  const [topicProject, setTopicProject] = useState("")
  const [topic, setTopic] = useState("")
  const [topicSources, setTopicSources] = useState<string[]>([])
  useEffect(() => { void fetchKnowledge().then(setIndex).catch((err: Error) => setMessage(err.message)) }, [brain.scanned_at])

  const visible = brain.projects.filter((project) => !focus || project.id === focus)
  async function load(id: string, pageTopic?: string, sourceIds?: string[]) {
    try { const next = await previewKnowledge(id, pageTopic, sourceIds); setDraft(next); setContent(next.content); setMessage("") }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not preview") }
  }
  async function approve() {
    if (!draft || !window.confirm(`Save reviewed knowledge for ${draft.title}? Source files will not change.`)) return
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
              <p className="quiet">Choose source files for this topic:</p>
              <div className="knowledge-source-list">{brain.files.filter((file) => file.project_id === project.id && !file.env_class).map((file) =>
                <label key={file.id}><input type="checkbox" checked={topicSources.includes(file.id)} onChange={(e) =>
                  setTopicSources((before) => e.target.checked ? [...before, file.id] : before.filter((id) => id !== file.id))} />{file.rel}</label>)}</div>
              <button type="button" className="primary" disabled={!topic.trim() || !topicSources.length}
                onClick={() => void load(project.id, topic, topicSources)}>Preview topic</button>
            </div>}
          </div>
        })}
      </section>
      <section><h2>{draft ? `Review: ${draft.title}` : "Knowledge checks"}</h2>
        {draft ? <div className="knowledge-card">
          <p>Sources: {draft.sources.map((item) => item.rel).join(", ") || "None"}</p>
          {draft.warning && <p className="knowledge-warning">{draft.warning}</p>}
          {draft.changed_sources.length > 0 && <p>{draft.changed_sources.length} new or changed indexed source(s).</p>}
          {draft.missing_sources.length > 0 && <p className="knowledge-warning">{draft.missing_sources.length} previous source(s) missing.</p>}
          {draft.previous_content && <details><summary>Previous approved version (compare before replacing)</summary>
            <pre className="knowledge-previous">{draft.previous_content}</pre></details>}
          <textarea aria-label="Edit knowledge page before approval" value={content} onChange={(event) => setContent(event.target.value)} rows={18} />
          <button type="button" className="primary" disabled={!draft.sources.length} onClick={() => void approve()}>Approve page</button>
          <button type="button" className="ghost" onClick={() => setDraft(null)}>Cancel</button>
        </div> : <div className="knowledge-card">
          <button type="button" className="ghost" onClick={() => void fetchKnowledge().then(setIndex).catch((err: Error) => setMessage(err.message))}>Run checks</button>
          {index?.findings.length ? index.findings.map((item, n) => <p key={n} className="knowledge-warning">{item.project_id}: {item.detail}</p>) : <p>No broken links or changed sources found in approved pages. This does not verify the truth of source files.</p>}
        </div>}
        <h2>Saved answers</h2>
        {index?.answers.filter((item) => !focus || focus === item.project_id).map((item) => <div key={`${item.project_id}-${item.name}`} className="knowledge-card">
          <strong>{item.name}</strong>{item.stale_sources.length ? <span className="knowledge-warning"> · needs recheck</span> : null}
          <p>{item.content.slice(0, 240)}</p>
        </div>)}
      </section>
    </div>
    <section className="knowledge-card"><h2>Reusable skill draft</h2>
      <p className="quiet">Repeated prompts are suggestions only. Write and review the steps yourself; saving never installs or runs a skill.</p>
      {(index?.workflow_candidates ?? []).filter((item) => !focus || item.project_id === focus).map((item) =>
        <button type="button" className="ghost" key={`${item.project_id}-${item.name}`}
          onClick={() => setSkill({ project_id: item.project_id, name: item.name,
            description: item.examples[0].text.slice(0, 180), steps: "" })}>
          {item.project_id}: {item.examples[0].text} ({item.count} prompts)
        </button>)}
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
