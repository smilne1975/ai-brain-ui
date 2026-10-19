import type { Brain } from "./types"

export function projectName(brain: Brain, id: string | null | undefined): string {
  if (!id) return ""
  return brain.projects.find((project) => project.id === id)?.name ?? id
}

export function skillById(brain: Brain, id: string) {
  return brain.skills.find((skill) => skill.id === id)
}

export function fileById(brain: Brain, id: string) {
  return brain.files.find((file) => file.id === id)
}

export function connectionById(brain: Brain, id: string) {
  return brain.connections.find((item) => item.id === id)
}

export function statusLabel(status: string): string {
  if (status === "connected") return "Connected"
  if (status === "referenced") return "Referenced"
  return "Not connected"
}

export function matchesQuery(query: string, text: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return text.toLowerCase().includes(q)
}

export function formatWhen(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
