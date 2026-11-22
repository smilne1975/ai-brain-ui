import { useEffect, useRef, useState } from "react"
import { approveVoiceNote, discardVoiceNote, fetchVoiceNotes, previewVoiceNote } from "../api"
import type { VoiceDraft, VoiceItem, VoiceNote } from "../types"

function timestamp(ms: number) {
  const seconds = Math.floor(ms / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
}

export function VoiceInbox({ project }: { project: string }) {
  const [available, setAvailable] = useState(false)
  const [notes, setNotes] = useState<VoiceNote[]>([])
  const [draft, setDraft] = useState<(VoiceDraft & { file: File }) | null>(null)
  const [approved, setApproved] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const player = useRef<HTMLAudioElement>(null)
  const previewFile = draft?.file
  useEffect(() => {
    let active = true
    void fetchVoiceNotes(project).then((result) => { if (active) { setNotes(result.items); setAvailable(result.available) } })
      .catch((err: Error) => { if (active) setMessage(err.message) })
    return () => { active = false }
  }, [project])
  useEffect(() => {
    if (!previewFile || !player.current) return
    const url = URL.createObjectURL(previewFile)
    player.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [previewFile])

  function edit(segment: number, patch: Partial<VoiceItem>) {
    setDraft((current) => current && { ...current, items: current.items.map((row) => row.segment === segment ? { ...row, ...patch } : row) })
  }

  return <div>
    <p className="quiet">Choose a recorded 16-bit PCM WAV file up to two minutes. Speech recognition runs locally and can mishear names or technical terms; review before saving.</p>
    {!available && <p>Local speech recognition needs a configured whisper.cpp executable and model. There is no cloud fallback.</p>}
    <label>Choose voice memo <input type="file" accept=".wav,audio/wav" disabled={!available || busy || !!draft}
      onChange={async (event) => {
        const file = event.target.files?.[0]
        event.target.value = ""
        if (!file) return
        if (file.size > 24 * 1024 * 1024) { setMessage("Choose a WAV file under 24 MiB."); return }
        setBusy(true); setMessage("Transcribing on this machine…"); setApproved([])
        try { setDraft({ ...await previewVoiceNote(project, file), file }); setMessage("") }
        catch (err) { setMessage(err instanceof Error ? err.message : "Could not transcribe voice memo.") }
        finally { setBusy(false) }
      }} /></label>
    {draft && <div>
      <p>{draft.filename}</p>
      <audio ref={player} controls preload="metadata" />
      {draft.items.map((item) => <fieldset key={item.segment} disabled={busy}>
        <legend><button type="button" className="ghost" onClick={() => {
          if (player.current) player.current.currentTime = item.start_ms / 1000
        }}>{timestamp(item.start_ms)} · jump to original</button></legend>
        <p className="quiet">{item.excerpt}</p>
        <label><input type="checkbox" checked={approved.includes(item.segment)} onChange={(event) =>
          setApproved(event.target.checked ? [...approved, item.segment] : approved.filter((segment) => segment !== item.segment))} /> Approve</label>
        <select aria-label="Voice note type" value={item.kind} onChange={(event) => edit(item.segment, { kind: event.target.value as VoiceItem["kind"] })}>
          <option value="observation">Observation</option><option value="action">Action</option>
        </select>
        <textarea aria-label="Edit voice note" rows={2} maxLength={600} value={item.text}
          onChange={(event) => edit(item.segment, { text: event.target.value })} />
      </fieldset>)}
      <button type="button" className="primary" disabled={busy || !approved.length} onClick={async () => {
        setBusy(true); setMessage("")
        try {
          const result = await approveVoiceNote(project, draft.id, draft.items.filter((item) => approved.includes(item.segment)))
          setNotes((previous) => [result, ...previous]); setDraft(null); setMessage("Saved selected notes and the original audio locally.")
        } catch (err) { setMessage(err instanceof Error ? err.message : "Could not save selected notes.") }
        finally { setBusy(false) }
      }}>Save selected notes and original audio</button>
      <button type="button" className="ghost" disabled={busy} onClick={async () => {
        try { await discardVoiceNote(project, draft.id); setDraft(null); setMessage("Draft discarded.") }
        catch (err) { setMessage(err instanceof Error ? err.message : "Could not discard the draft.") }
      }}>Discard draft</button>
    </div>}
    {message && <p role="status">{message}</p>}
    {notes.map((memo) => <details key={memo.id}>
      <summary>{memo.filename} · {memo.items.length} approved item(s)</summary>
      {memo.items.map((item) => <p key={item.segment}>
        <a href={`/api/voice-notes/${encodeURIComponent(project)}/${encodeURIComponent(memo.id)}/audio#t=${item.start_ms / 1000}`}
          target="_blank" rel="noreferrer">{timestamp(item.start_ms)} original audio</a> · {item.kind}: {item.text}
      </p>)}
    </details>)}
  </div>
}
