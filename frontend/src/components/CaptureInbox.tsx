import { useEffect, useRef, useState } from "react"
import { changeCapture, getCaptures, stageCapture, stageCaptureImage } from "../api"
import type { CaptureItem, CaptureReceipt, FileRec } from "../types"

type Receipt = { id: number; file: File; value?: CaptureReceipt; error?: string; voice?: boolean }

function errorText(err: unknown) { return err instanceof Error ? err.message : "Could not read this item." }

export function CaptureInbox({ project, notes, onChange, onVoice }: { project: string; notes: FileRec[]; onChange: () => void;
  onVoice: (file: File) => void }) {
  const [items, setItems] = useState<CaptureItem[]>([])
  const [paste, setPaste] = useState("")
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [picked, setPicked] = useState("")
  const [filter, setFilter] = useState("staged")
  const [tags, setTags] = useState("")
  const [filing, setFiling] = useState("")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const sequence = useRef(0)
  useEffect(() => {
    let active = true
    void getCaptures(project).then(({ items }) => { if (active) setItems((prior) => [...prior, ...items.filter((row) => !prior.some((item) => item.id === row.id))]) })
      .catch((err) => { if (active) setMessage(errorText(err)) })
    return () => { active = false }
  }, [project])
  const shown = items.filter((item) => filter === "all" || item.state === filter)
  const selected = shown.find((item) => item.id === picked) ?? shown[0]
  // Tie editable metadata to the selected item, not to whichever row becomes first after filing.
  const editing = selected?.id === picked
  const seed = selected?.content.toLowerCase().match(/\b[a-z][a-z0-9-]{5,}\b/g) ?? []
  const words = new Set(seed.slice(0, 100))
  const matches = notes.flatMap((note) => {
    const shared = [...new Set((`${note.title ?? ""} ${note.rel}`.toLowerCase().match(/\b[a-z][a-z0-9-]{5,}\b/g) ?? []))].filter((word) => words.has(word))
    return shared.length ? [{ note, shared }] : []
  }).sort((a, b) => b.shared.length - a.shared.length).slice(0, 3)
  function choose(item: CaptureItem) { setPicked(item.id); setTags(item.tags); setFiling(item.filing) }
  function add(row: CaptureItem) {
    setItems((prior) => prior.some((item) => item.id === row.id) ? prior.map((item) => item.id === row.id ? row : item) : [row, ...prior])
  }
  async function fileReceipt(receipt: Receipt) {
    const { file } = receipt
    try {
      if (/\.wav$/i.test(file.name)) {
        if (file.size > 24 * 1024 * 1024) throw new Error("Choose a WAV under 24 MiB.")
        const header = new TextDecoder().decode(await file.slice(0, 12).arrayBuffer())
        if (!header.startsWith("RIFF") || !header.endsWith("WAVE")) throw new Error("The file does not look like a WAV recording.")
        return { id: receipt.id, file, voice: true }
      }
      if (/\.png$/i.test(file.name) || file.type === "image/png") {
        if (file.size > 1024 * 1024) throw new Error("Choose a PNG screenshot up to 1 MiB.")
        const bytes = new Uint8Array(await file.arrayBuffer())
        if (bytes.length < 24) throw new Error("Choose a complete PNG screenshot.")
        const view = new DataView(bytes.buffer)
        if (view.getUint32(16) * view.getUint32(20) > 4_000_000) throw new Error("Choose a screenshot under four million pixels.")
        const image = await createImageBitmap(file).catch(() => { throw new Error("Could not read this PNG screenshot.") })
        image.close()
        let binary = ""
        for (let offset = 0; offset < bytes.length; offset += 16384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384))
        const value = await stageCaptureImage(project, file.name, btoa(binary))
        if (value.item) add(value.item)
        return { id: receipt.id, file, value }
      }
      if (!/\.(md|markdown|txt)$/i.test(file.name)) throw new Error("Choose text, Markdown, a PNG screenshot, or a WAV voice memo.")
      if (file.size > 160_000) throw new Error("Choose a smaller text file.")
      const text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer())
      if (text.length > 40_000 || text.includes("\0")) throw new Error("Choose a text file with at most 40,000 characters.")
      const kind = /^(?:\ufeff)?---\r?\n[\s\S]*?^(?:source|url):\s*.*$/im.test(text) ? "clip" : "note"
      const value = await stageCapture(project, file.name, text, kind)
      if (value.item) add(value.item)
      return { id: receipt.id, file, value }
    } catch (err) { return { id: receipt.id, file, error: errorText(err) } }
  }
  async function receive(files: File[]) {
    if (busy || !files.length) return
    setBusy(true); setMessage(files.length > 20 ? "Only the first 20 items were queued. Select the rest in another batch." : "")
    const queued = files.slice(0, 20).map((file) => ({ id: ++sequence.current, file }))
    setReceipts(queued)
    try {
      for (const row of queued) {
        const next = await fileReceipt(row)
        setReceipts((prior) => prior.map((item) => item.id === row.id ? next : item))
      }
    } finally { setBusy(false) }
  }
  return <section aria-label="Local capture queue">
    <p className="quiet">Capture notes, links, PNG screenshots and Web Clipper files; hand WAV recordings to the local voice review. Nothing is fetched or moved. Only approved web clips join Ask; other captures stay on the local shelf.</p>
    <textarea aria-label="Paste a note, link, or screenshot" value={paste} rows={4} maxLength={40000} onChange={(event) => setPaste(event.target.value)}
      onPaste={(event) => {
        const pngs = Array.from(event.clipboardData.files).filter((file) => file.type === "image/png")
        if (pngs.length) { event.preventDefault(); void receive(pngs) }
      }} />
    <button type="button" className="primary" disabled={busy || !paste.trim()} onClick={async () => {
      setBusy(true); setMessage("")
      try {
        const input = paste.trim()
        const result = await stageCapture(project, "Pasted capture", input, /^https?:\/\/\S+$/i.test(input) ? "link" : "note")
        if (result.item) { add(result.item); setFilter("all"); choose(result.item) }
        setMessage(result.status === "duplicate" ? "Already in the capture queue." : "Ready for review."); setPaste("")
      } catch (err) { setMessage(errorText(err)) }
      finally { setBusy(false) }
    }}>Queue pasted capture</button>
    <div className="knowledge-card" onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
      event.preventDefault(); void receive(Array.from(event.dataTransfer.files))
    }}><label>Choose or drop up to 20 files <input aria-label="Select capture files" type="file" multiple disabled={busy}
      accept=".txt,.md,.markdown,.png,.wav" onChange={(event) => {
        const files = Array.from(event.target.files ?? []); event.target.value = ""; void receive(files)
      }} /></label></div>
    {receipts.length > 0 && <ul aria-label="Batch receipts" aria-live="polite">{receipts.map((row) => <li key={row.id}>
      {row.file.name}: {row.error ? `Failed — ${row.error}` : row.voice ? "Ready for local voice review (not transcribed)" : row.value?.status ?? "Queued"}{" "}
      {row.voice && <button type="button" className="ghost" onClick={() => onVoice(row.file)}>Review voice memo</button>}
      {row.value?.existing_clip && <button type="button" className="ghost" onClick={() => {
        const target = document.getElementById(`web-clip-${row.value?.existing_clip?.id}`)
        const details = target?.closest("details")
        if (details) details.open = true
        target?.scrollIntoView({ block: "nearest" })
      }}>Existing clip: {row.value.existing_clip.title}</button>}
      {row.value?.item && <button type="button" className="ghost" onClick={() => { setFilter("all"); choose(row.value!.item!) }}>Review queued item</button>}
      {row.error && <button type="button" className="ghost" disabled={busy} onClick={async () => {
        setBusy(true)
        try { const next = await fileReceipt(row); setReceipts((prior) => prior.map((item) => item.id === row.id ? next : item)) }
        finally { setBusy(false) }
      }}>Retry {row.file.name}</button>}
    </li>)}</ul>}
    {message && <p role="status">{message}</p>}
    <label>Show captures <select value={filter} onChange={(event) => setFilter(event.target.value)}>
      <option value="staged">Needs review</option><option value="filed">Filed</option><option value="all">All states</option>
    </select></label>
    {!shown.length ? <p className="quiet">Nothing in this view yet.</p> : <div className="passage-grid">
      <div aria-label="Capture list">{shown.map((item) => <button type="button" className="brain-diagram-card" key={item.id}
        aria-pressed={selected?.id === item.id} onClick={() => choose(item)}>{item.name} · {item.kind} · {item.state}</button>)}</div>
      {selected && <article className="knowledge-card"><strong>{selected.name}</strong>
        <p className="quiet">Local copy for review · project {project}</p>
        {selected.kind === "image" ? <img className="capture-image" loading="lazy" src={`/api/captures/${encodeURIComponent(project)}/${encodeURIComponent(selected.id)}/image`}
          alt={`Captured screenshot: ${selected.name}`} /> : <pre className="knowledge-previous">{selected.content}</pre>}
        {matches.length > 0 && <ul>{matches.map(({ note, shared }) => <li key={note.id}>{note.rel} · matching filename terms: {shared.join(", ")}</li>)}</ul>}
        {selected.state === "staged" && <>
          <label>Filing label <input maxLength={150} value={editing ? filing : selected.filing} placeholder="Optional; leave uncertain captures unfiled"
            onChange={(event) => { if (!editing) choose(selected); setFiling(event.target.value) }} /></label>
          <label>Tags <input maxLength={200} value={editing ? tags : selected.tags} placeholder="Optional tags"
            onChange={(event) => { if (!editing) choose(selected); setTags(event.target.value) }} /></label>
        </>}
        {selected.state === "filed" && <p>{selected.filing || "No filing label"}{selected.tags ? ` · ${selected.tags}` : ""}</p>}
        {(selected.state === "staged" ? ["approve", "remove"] : selected.state === "filed" ? ["undo"] : ["remove"]).map((action) =>
          <button type="button" className="ghost" key={action} disabled={busy} onClick={async () => {
            setBusy(true); setMessage("")
            try {
              const next = await changeCapture(project, selected.id, action as "approve" | "undo" | "remove", editing ? tags : selected.tags, editing ? filing : selected.filing)
              if (next.removed) setItems((prior) => prior.filter((item) => item.id !== selected.id))
              if (next.item) add(next.item)
              setMessage(next.duplicate ? `Already in Web-clip inbox: ${next.duplicate.title}` : action === "approve" ? "Filed locally." : "Capture updated.")
              onChange()
            } catch (err) { setMessage(errorText(err)) }
            finally { setBusy(false) }
          }}>{action === "approve" ? selected.clip ? "Approve clip for Ask" : "File on local shelf" : action === "undo" ? "Undo filing" : "Remove from queue"}</button>)}
      </article>}
    </div>}
  </section>
}
