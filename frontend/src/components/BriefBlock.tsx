import { useState } from "react"
import type { Brief } from "../types"

type Props = {
  brief: Brief
  compact?: boolean
  onOpenFile?: (id: string) => void
  onSave?: () => Promise<void>
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // The page may be non-secure or the permission may be denied. Try the textarea path.
  }
  try {
    const area = document.createElement("textarea")
    area.value = text
    area.setAttribute("readonly", "")
    area.style.position = "fixed"
    area.style.top = "0"
    area.style.left = "0"
    area.style.opacity = "0"
    document.body.appendChild(area)
    area.focus()
    area.select()
    const ok = document.execCommand("copy")
    area.remove()
    return ok
  } catch {
    return false
  }
}

export function briefFor(briefs: Brief[] | undefined, projectId: string): Brief | undefined {
  return (briefs ?? []).find((item) => item.project_id === projectId)
}

export function BriefBlock({ brief, compact, onOpenFile, onSave }: Props) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState("")
  const [saveError, setSaveError] = useState("")

  async function copy() {
    setCopyError("")
    const ok = await writeClipboard(brief.copy_text)
    if (!ok) {
      setCopyError("Clipboard was blocked. Select the brief and copy it manually.")
      return
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 4000)
  }

  async function save() {
    if (!onSave) return
    setSaving(true)
    setSaveError("")
    try {
      await onSave()
      setSaved("Saved BRAIN_HANDOFF.md")
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "Could not write BRAIN_HANDOFF.md.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="brief">
      <span>Pick up where I left off</span>
      <p className="brief-doing">{brief.last_doing}</p>
      {!compact && brief.decisions.length > 0 && (
        <ul className="brief-list">
          {brief.decisions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <p className="brief-next">
        <em>Next</em> {brief.next_step}
      </p>
      {!compact && brief.todos.length > 0 && (
        <ul className="brief-todos">
          {brief.todos.slice(0, 4).map((item) => (
            <li key={`${item.rel}-${item.line ?? item.text}`}>
              <i>{item.kind}</i> {item.text}
              <code>{item.rel}</code>
            </li>
          ))}
        </ul>
      )}
      {!compact && brief.key_files.length > 0 && (
        <div className="chat-files">
          {brief.key_files.map((file) =>
            file.file_id && onOpenFile ? (
              <button key={file.rel} type="button" onClick={() => onOpenFile(file.file_id as string)}>
                {file.rel}
              </button>
            ) : (
              <code key={file.rel}>{file.rel}</code>
            ),
          )}
        </div>
      )}
      <div className="brief-actions">
        <button type="button" className="primary" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy for new chat"}
        </button>
        {onSave && (
          <button type="button" onClick={() => void save()} disabled={saving}>
            {saving ? "Saving" : "Save BRAIN_HANDOFF.md"}
          </button>
        )}
      </div>
      {copyError && <p className="ask-error">{copyError}</p>}
      {saved && <p className="quiet">{saved}</p>}
      {saveError && <p className="ask-error">{saveError}</p>}
    </section>
  )
}
