export type View = "skills" | "blueprint" | "system" | "connections"

export type BrainStatus = {
  ok: boolean
  phase: "starting" | "scanning" | "ready" | "error"
  root: string
  root_name?: string
  message: string
  files: number
  projects: number
  current: string
  generation?: number
  error?: string
  truncated?: boolean
  scanned_at?: string
}

export type ProviderInfo = {
  mode: string
  model: string | null
  label: string
}

export type Todo = { line: number; text: string }

export type FileRec = {
  id: string
  project_id: string
  project_rel: string
  rel: string
  name: string
  kind: string
  lines: number
  summary: string
  excerpt: string
  skills: string[]
  env_class: string | null
  env_keys: string[]
  entry: boolean
  todos: Todo[]
  symbols: { name: string; kind: string; decision: boolean }[]
  imports_local: string[]
  intro: string
  title: string
}

export type Project = {
  id: string
  name: string
  rel: string
  summary: string
  summary_source: string
  skills: string[]
  services: string[]
  entries: string[]
  stats: {
    files: number
    python: number
    markdown: number
    lines: number
    todos: number
    env_keys: string[]
  }
}

export type Skill = {
  id: string
  name: string
  category: string
  blurb: string
  score: number
  projects: string[]
  files: { project_id: string; file_id: string; rel: string; line: string }[]
}

export type Category = { id: string; name: string; skills: string[] }

export type Evidence = { project_id: string; file_id: string; rel: string; how: string }

export type Connection = {
  id: string
  name: string
  category: string
  description: string
  status: "connected" | "referenced" | "absent"
  projects: string[]
  live_projects: string[]
  evidence: Evidence[]
}

export type GraphNode = {
  id: string
  label: string
  sub: string
  kind: string
  project_id: string | null
  file_id: string | null
  service_id: string | null
}

export type GraphEdge = { id: string; source: string; target: string; label: string }

export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] }

export type Brain = {
  root: string
  root_name: string
  scanned_at: string
  truncated: boolean
  projects: Project[]
  files: FileRec[]
  skills: Skill[]
  categories: Category[]
  connections: Connection[]
  architecture: { corpus: Graph; projects: Record<string, Graph> }
  suggestions: string[]
  stats: {
    projects: number
    files: number
    skills: number
    lines: number
    todos: number
    connections_live: number
    connections_referenced: number
  }
  summaries: string
  provider: ProviderInfo
  signature?: string
}

export type Selection =
  | { kind: "skill"; id: string }
  | { kind: "file"; id: string }
  | { kind: "project"; id: string }
  | { kind: "connection"; id: string }

export type AskResponse = {
  answer: string
  citations: { id: string; label: string; kind: string; project_id: string }[]
  provider: string
}

export const CATEGORY_COLOR: Record<string, string> = {
  Models: "#3dff9a",
  Prompting: "#d7ffe8",
  Retrieval: "#7fd6ff",
  Agents: "#d2b4ff",
  Automation: "#f0c14a",
  Data: "#ffb086",
  Interfaces: "#9ad0ff",
  Devtools: "#ff8ad4",
  Notes: "#e7fff3",
}
