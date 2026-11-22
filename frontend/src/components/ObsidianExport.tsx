import { useState } from "react"
import { downloadObsidian, previewObsidian } from "../api"
import type { ObsidianPreview } from "../types"

export function ObsidianExport({ project }: { project: string }) {
  const [preview, setPreview] = useState<ObsidianPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  async function act(work: () => Promise<void>) {
    setBusy(true); setMessage("")
    try { await work() }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not export the Obsidian package.") }
    finally { setBusy(false) }
  }
  return <div>
    <p className="quiet">Download approved project notes and a JSON Canvas map. AI Brain does not write into your vault or copy project files.</p>
    <button type="button" className="ghost" disabled={busy}
      onClick={() => void act(async () => { setPreview(null); setPreview(await previewObsidian(project)) })}>Preview files</button>
    {preview && <div>
      <p>{preview.node_count} map nodes · {preview.edge_count} links</p>
      {!!preview.omitted_pages && <p className="knowledge-warning">{preview.omitted_pages} stale, unreadable, or excess page(s) omitted.</p>}
      {!!preview.unresolved_count && <p className="knowledge-warning">{preview.unresolved_count} unresolved or ambiguous note link(s) listed in the index.</p>}
      <ul>{preview.paths.map((path) => <li key={path}><code>{path}</code></li>)}</ul>
      <button type="button" className="primary" disabled={busy} onClick={() => void act(async () => {
        const url = URL.createObjectURL(await downloadObsidian(project, preview))
        const link = document.createElement("a")
        link.href = url; link.download = `${preview.folder}.zip`; link.click()
        window.setTimeout(() => URL.revokeObjectURL(url), 15_000)
        setMessage("Download handed to the browser. Unzip it at the vault root, keeping the package folder name.")
      })}>Download the previewed package</button>
    </div>}
    {message && <p role="status">{message}</p>}
  </div>
}
