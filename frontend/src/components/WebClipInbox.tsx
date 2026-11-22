import { useEffect, useState } from "react"
import { approveClip, fetchClips, previewClip, setClipActive } from "../api"
import type { ClipDraft, WebClip } from "../types"

export function WebClipInbox({ project, onChange }: { project: string; onChange: () => void }) {
  const [items, setItems] = useState<WebClip[]>([])
  const [draft, setDraft] = useState<{ clip: ClipDraft; markdown: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")

  useEffect(() => {
    let active = true
    void fetchClips(project).then((result) => { if (active) setItems(result.items) })
      .catch((err: Error) => { if (active) setMessage(err.message) })
    return () => { active = false }
  }, [project])

  return <div>
    <p className="quiet">Choose an Obsidian Web Clipper Markdown file. Original websites are never fetched during import.</p>
    <label>Choose clip <input type="file" accept=".md,.markdown,text/markdown" disabled={busy}
      onChange={async (event) => {
        const file = event.target.files?.[0]
        event.target.value = ""
        if (!file) return
        setBusy(true); setMessage(""); setDraft(null)
        try {
          if (file.size > 160_000) throw new Error("Choose a smaller Markdown clip.")
          const markdown = await file.text()
          if (markdown.length > 40_000 || markdown.includes("\0")) throw new Error("Choose a Markdown clip with at most 40,000 characters.")
          setDraft({ clip: await previewClip(project, file.name, markdown), markdown })
        } catch (err) { setMessage(err instanceof Error ? err.message : "Could not preview clip.") }
        finally { setBusy(false) }
      }} /></label>
    {draft && <div className="knowledge-card">
      <strong>{draft.clip.title}</strong>
      <p>{draft.clip.filename} · {draft.clip.captured_at ?? "capture date not recorded"} · project {project}</p>
      <a href={draft.clip.url} target="_blank" rel="noreferrer">{draft.clip.url}</a>
      <pre className="knowledge-previous">{draft.clip.content}</pre>
      <button type="button" className="primary" disabled={busy} onClick={async () => {
        setBusy(true); setMessage("")
        try {
          const result = await approveClip(project, draft.clip.filename, draft.markdown, draft.clip.id)
          setItems((previous) => [result.clip, ...previous.filter((clip) => clip.id !== result.clip.id)])
          onChange()
          setDraft(null); setMessage(result.created ? "Approved clip added to local Ask." : "This clip was already imported.")
        } catch (err) { setMessage(err instanceof Error ? err.message : "Could not approve clip.") }
        finally { setBusy(false) }
      }}>Approve for local Ask</button>
      <button type="button" className="ghost" disabled={busy} onClick={() => setDraft(null)}>Cancel</button>
    </div>}
    {message && <p role="status">{message}</p>}
    {items.map((item) => <p key={item.id}>
      <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> · {item.active ? "searchable" : "not indexed"}{" "}
      <button type="button" className="ghost" disabled={busy} onClick={async () => {
        setBusy(true); setMessage("")
        try {
          const updated = await setClipActive(project, item.id, !item.active)
          setItems((previous) => previous.map((clip) => clip.id === updated.id ? updated : clip))
          onChange()
        } catch (err) { setMessage(err instanceof Error ? err.message : "Could not change clip state.") }
        finally { setBusy(false) }
      }}>{item.active ? "Remove from search" : "Restore to search"}</button>
    </p>)}
  </div>
}
