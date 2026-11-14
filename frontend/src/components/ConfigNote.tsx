import type { ConfigProject } from "../types"

type Props = {
  report: ConfigProject | null | undefined
  onOpen?: () => void
}

export function ConfigNote({ report, onOpen }: Props) {
  if (!report?.units?.length) return null
  const faults = report.units.reduce((count, unit) => count + unit.faults.length, 0)
  const names = report.units.map((unit) => unit.name).slice(0, 3).join(", ")
  return (
    <section className="keyins">
      <button type="button" className="keyins-toggle" onClick={onOpen}>
        <span>Config</span>
        <em>{report.units.length}</em>
        <i>{faults ? `${faults} fault${faults === 1 ? "" : "s"}` : "open"}</i>
      </button>
      <p className="quiet">{names}</p>
    </section>
  )
}
