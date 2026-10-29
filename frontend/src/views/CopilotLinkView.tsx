import { useEffect, useState } from "react"
import { fetchMcpDoctor, fetchMcpUsage } from "../api"
import type { McpDoctor, McpUsage } from "../types"
import { formatWhen } from "../format"

export function CopilotLinkView() {
  const [usage, setUsage] = useState<McpUsage | null>(null)
  const [doctor, setDoctor] = useState<McpDoctor | null>(null)
  const [error, setError] = useState("")
  const [checking, setChecking] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancel = false
    fetchMcpUsage()
      .then((data) => {
        if (!cancel) setUsage(data)
      })
      .catch((reason: unknown) => {
        if (!cancel) setError(reason instanceof Error ? reason.message : "MCP usage is not ready.")
      })
    return () => {
      cancel = true
    }
  }, [])

  async function runDoctor() {
    setChecking(true)
    setError("")
    try {
      setDoctor(await fetchMcpDoctor())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The doctor could not run.")
    } finally {
      setChecking(false)
    }
  }

  async function copySnippet() {
    const text = usage?.snippet || doctor?.snippet || ""
    if (!text) return
    const ok = await writeClipboard(text)
    setCopied(ok)
    if (ok) window.setTimeout(() => setCopied(false), 2500)
  }

  const maxCount = Math.max(1, ...(usage?.counts ?? []).map((item) => item.count))
  const descriptions = new Map((usage?.tools ?? []).map((tool) => [tool.name, tool.description]))

  return (
    <div className="conn-page">
      <header className="conn-head">
        <div>
          <p className="eyebrow">Agent mode</p>
          <h1>copilot link</h1>
        </div>
        <p className="conn-count">{usage?.link.label ?? "Checking"}</p>
      </header>
      <div className="mcp-status">
        <i className={`mcp-light mcp-light-${usage?.link.state ?? "idle"}`} />
        <div>
          <strong>{usage?.link.label ?? "Waiting"}</strong>
          <p>
            {usage?.link.last_call ? `Last call ${formatWhen(usage.link.last_call)}` : "No calls yet"}
            {usage?.scanning ? " · a scan is in progress, tools use the last index" : ""}
            {usage?.demo ? " · demo sample calls" : ""}
          </p>
          <p className="quiet">{usage?.link.detail}</p>
        </div>
      </div>
      <div className="chips">
        <button type="button" className="primary" onClick={() => void copySnippet()} disabled={!usage && !doctor}>
          {copied ? "Copied" : "Copy mcp.json snippet"}
        </button>
        <button type="button" onClick={() => void runDoctor()} disabled={checking}>
          {checking ? "Checking" : "Run doctor"}
        </button>
      </div>
      <p className="quiet tl-note">
        Copilot agent mode can call these read-only tools instead of grepping the tree. Nothing is uploaded. .env values are never returned.
        Resource <code>brain://digest/latest</code>.
      </p>
      {error && <p className="ask-error">{error}</p>}
      <section className="digest-block">
        <h2>Tools</h2>
        <ul className="mcp-tools">
          {(usage?.counts ?? []).filter((item) => item.tool !== "digest").map((item) => (
            <li key={item.tool}>
              <div>
                <strong>{item.tool}</strong>
                <span>{descriptions.get(item.tool)}</span>
              </div>
              <em>{item.count}</em>
              <div className="mcp-bar" aria-hidden>
                <i style={{ width: `${Math.round((item.count / maxCount) * 100)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="digest-block">
        <h2>Recent calls</h2>
        {usage && usage.recent.length === 0 ? <p className="quiet">No calls logged.</p> : null}
        <table className="mcp-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Tool</th>
              <th>Args</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            {(usage?.recent ?? []).map((call) => (
              <tr key={`${call.ts}-${call.tool}-${call.args}`}>
                <td>{formatWhen(call.ts)}</td>
                <td>
                  {call.tool}
                  {call.source === "demo" ? <em> sample</em> : null}
                </td>
                <td>{call.args}</td>
                <td>
                  {call.bytes} B{call.truncated ? " · truncated" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {doctor && (
        <section className="digest-block">
          <h2>Doctor</h2>
          <ul className="mcp-checks">
            {doctor.checks.map((check) => (
              <li key={check.id} className={`mcp-check mcp-check-${check.status}`}>
                <strong>
                  {check.status} · {check.title}
                </strong>
                <span>{check.detail}</span>
                {check.fix ? <em>{check.fix}</em> : null}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall through when the clipboard API is blocked.
  }
  try {
    const area = document.createElement("textarea")
    area.value = text
    area.setAttribute("readonly", "")
    area.style.position = "fixed"
    area.style.left = "0"
    area.style.top = "0"
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
