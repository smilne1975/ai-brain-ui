import { useEffect, useState } from "react"
import { approveMeeting, fetchMeetings, previewMeeting } from "../api"
import type { MeetingItem, SavedMeetingItem } from "../types"

export function MeetingInbox({ project }: { project: string }) {
  const [notes, setNotes] = useState("")
  const [sourceName, setSourceName] = useState("Pasted meeting notes")
  const [preview, setPreview] = useState<{ notes: string; source_id: string; items: MeetingItem[] } | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [saved, setSaved] = useState<SavedMeetingItem[]>([])
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    void fetchMeetings(project).then((result) => { if (live) setSaved(result.items) })
      .catch((err: Error) => { if (live) setMessage(err.message) })
    return () => { live = false }
  }, [project])

  const current = preview?.notes === notes ? preview : null
  function edit(line: number, patch: Partial<MeetingItem>) {
    setPreview((prior) => prior && { ...prior, items: prior.items.map((item) => item.line === line ? { ...item, ...patch } : item) })
  }

  return <div>
    <p className="quiet">Paste notes or choose a local text file. Use headings like “Decisions” and “Actions”, or label a line “Action:”. Add <code>| Owner: … | Due: …</code> when recorded.</p>
    <label>Import text or Markdown <input type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" disabled={busy}
      onChange={async (event) => {
        const file = event.target.files?.[0]
        event.target.value = ""
        if (!file) return
        if (file.size > 200_000) { setMessage("Choose a smaller notes file."); return }
        try {
          const text = await file.text()
          if (text.length > 50_000 || text.includes("\0")) { setMessage("Choose a plain-text file of at most 50,000 characters."); return }
          setNotes(text); setSourceName(file.name.slice(0, 120)); setPreview(null); setSelected([]); setMessage("")
        } catch { setMessage("Could not read the file.") }
      }} /></label>
    <textarea aria-label="Meeting notes" rows={6} maxLength={50_000} value={notes} disabled={busy}
      onChange={(event) => { setNotes(event.target.value); setPreview(null); setSelected([]) }} />
    <button className="ghost" type="button" disabled={busy || !notes.trim()} onClick={async () => {
      setBusy(true); setPreview(null); setSelected([]); setMessage("")
      try { setPreview({ ...await previewMeeting(project, notes), notes }) }
      catch (err) { setMessage(err instanceof Error ? err.message : "Could not review notes.") }
      finally { setBusy(false) }
    }}>Preview decisions and actions</button>
    {current && (current.items.length === 0 ? <p>No labelled decisions or actions found.</p> : <div>
      {current.items.map((item) => <fieldset key={item.line} disabled={busy}>
        <legend>{item.kind === "action" ? "Action" : "Decision"} · line {item.line}</legend>
        <label><input type="checkbox" checked={selected.includes(item.line)} onChange={(event) =>
          setSelected(event.target.checked ? [...selected, item.line] : selected.filter((line) => line !== item.line))} /> Approve</label>
        <p className="quiet">{item.excerpt}</p>
        <label>Text <input maxLength={500} value={item.text} onChange={(event) => edit(item.line, { text: event.target.value })} /></label>
        <label>Owner <input maxLength={120} value={item.owner ?? ""} onChange={(event) => edit(item.line, { owner: event.target.value })} /></label>
        <label>Due <input maxLength={120} value={item.due ?? ""} onChange={(event) => edit(item.line, { due: event.target.value })} /></label>
      </fieldset>)}
      <button className="primary" type="button" disabled={busy || !selected.length} onClick={async () => {
        setBusy(true); setMessage("")
        try {
          const result = await approveMeeting(project, notes, sourceName, current.source_id, current.items.filter((item) => selected.includes(item.line)))
          setSelected([])
          setSaved((await fetchMeetings(project)).items)
          setMessage(`Saved ${result.added} item(s); ${result.already_saved} already in the list.`)
        } catch (err) { setMessage(err instanceof Error ? err.message : "Could not save items.") }
        finally { setBusy(false) }
      }}>Save selected items</button>
    </div>)}
    {message && <p role="status">{message}</p>}
    <h3>Approved decisions and actions</h3>
    {!saved.length && <p className="quiet">No approved meeting items yet.</p>}
    {saved.map((item) => <details key={`${item.source_id}:${item.line}`}>
      <summary>{item.kind}: {item.text}{item.owner ? ` · ${item.owner}` : ""}{item.due ? ` · due ${item.due}` : ""}</summary>
      <p>{item.source_name}, line {item.line}: {item.excerpt}</p>
    </details>)}
  </div>
}
