import { useState } from "react"
import type { MicrostationReport } from "../types"

type Props = {
  report: MicrostationReport | null
  onOpenFile?: (id: string) => void
}

export function Keyins({ report, onOpenFile }: Props) {
  const [open, setOpen] = useState(true)
  const [copied, setCopied] = useState("")
  if (!report) return null
  const count = report.keyins.length

  async function copy(id: string, prompt: string) {
    const ok = await writeClipboard(prompt)
    setCopied(ok ? id : "")
    if (!ok) return
    window.setTimeout(() => setCopied((current) => (current === id ? "" : current)), 2500)
  }

  return (
    <section className="keyins">
      <button type="button" className="keyins-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span>Key-ins</span>
        <em>{count}</em>
        <i>{open ? "hide" : "show"}</i>
      </button>
      {open && (
        <>
          {count === 0 ? (
            <p className="quiet">No key-in table was parsed.</p>
          ) : (
            <ul className="keyin-list">
              {report.keyins.map((item) => {
                const target = item.found && item.rel ? `${item.rel}:${item.function}` : "handler not found"
                return (
                  <li key={`${item.xml}-${item.keyin}`}>
                    <code>{item.keyin}</code>
                    <span aria-hidden>→</span>
                    {item.found && item.file_id && onOpenFile ? (
                      <button type="button" onClick={() => onOpenFile(item.file_id as string)}>
                        {target}
                      </button>
                    ) : (
                      <em className={item.found ? "" : "missing"}>{target}</em>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {report.pitfalls.length > 0 && (
            <div className="pitfalls">
              {report.pitfalls.map((item) => (
                <button
                  key={`${item.id}-${item.title}`}
                  type="button"
                  className={`pitfall pitfall-${item.severity}`}
                  onClick={() => void copy(`${item.id}-${item.title}`, item.prompt)}
                >
                  <strong>{item.title}</strong>
                  <span>{item.detail}</span>
                  <em>{copied === `${item.id}-${item.title}` ? "Copied" : "Copy fix prompt"}</em>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall through when the page cannot use the async clipboard.
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
