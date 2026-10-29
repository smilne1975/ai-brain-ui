export type View = "skills" | "blueprint" | "system" | "connections" | "copilot" | "timeline" | "cards" | "digest"

export type BriefTodo = { text: string; rel: string; kind: string; line?: number }
export type BriefFile = { rel: string; file_id: string | null; why: string }

export type Brief = {
  project_id: string
  name: string
  generated_at: string
  source: string
  last_doing: string
  decisions: string[]
  todos: BriefTodo[]
  todo_count: number
  fixme_count: number
  next_step: string
  key_files: BriefFile[]
  run_command: string
  copy_text: string
}

export type BriefBoard = { generated_at: string; source: string; briefs: Brief[] }

export type DigestProject = { project_id: string; name: string; detail?: string; files?: number }
export type DigestTodo = { project_id: string; project: string; rel: string; text: string; kind: string }
export type DigestChat = { id?: string; project_id: string | null; project: string; when: string | null; prompt: string; summary: string }
export type DigestFocus = { project_id: string; name: string; why: string }

export type Digest = {
  period: "day" | "week"
  label: string
  generated_at: string
  source: string
  window_start: string
  window_end: string
  summary?: string
  touched: DigestProject[]
  newly_stale: DigestProject[]
  newly_abandoned: DigestProject[]
  todos: { open: number; fixmes: number; top: DigestTodo[] }
  chats: DigestChat[]
  focus: DigestFocus[]
  markdown: string
  saved_path?: string
}

export type TimelineFile = {
  rel: string
  name: string
  when: string
  via: "mtime" | "git" | "both" | string
  change: string
  commit: string | null
  note: string
}

export type TimelineCommit = { hash: string; subject: string; when: string }

export type ChatFileRef = { rel: string; name: string; file_id: string | null }

export type ChatPrompt = { text: string; when: string | null; files: ChatFileRef[] }

export type ChatSession = {
  id: string
  project_id: string | null
  project_name: string | null
  workspace_path: string
  title: string
  when: string | null
  source: string
  prompt: string
  summary: string
  summary_source: string
  prompts: ChatPrompt[]
  files: ChatFileRef[]
}

export type ChatIndex = {
  enabled: boolean
  source: string
  roots: string[]
  sessions: ChatSession[]
  by_project: Record<string, string[]>
  truncated: boolean
  llm: boolean
}

export type TimelineChat = {
  id: string
  title: string
  when: string | null
  prompt: string
  summary: string
  files: ChatFileRef[]
}

export type TimelineProject = {
  project_id: string
  name: string
  summary: string
  summary_source: string
  files: TimelineFile[]
  commits: TimelineCommit[]
  chats?: TimelineChat[]
  more?: number
}

export type TimelineDay = { date: string; label: string; projects: TimelineProject[] }

export type TimelineWeek = {
  id: string
  label: string
  start: string
  end: string
  file_count: number
  project_count: number
  days: TimelineDay[]
}

export type Timeline = {
  window_days: 1 | 7 | 30
  label: string
  generated_at: string
  source: string
  project_count: number
  file_count: number
  weeks: TimelineWeek[]
}

export type CardEntry = { path: string; how: string; kind: string }

export type MicrostationKeyin = {
  keyin: string
  handler: string
  module: string
  function: string
  xml: string
  xml_id: string | null
  found: boolean
  rel: string
  file_id: string | null
  source: string
}

export type MicrostationPitfall = {
  id: string
  severity: "red" | "amber"
  title: string
  detail: string
  prompt: string
}

export type MicrostationReport = {
  project_id: string
  name: string
  keyins: MicrostationKeyin[]
  commands: string[]
  scripts: string[]
  third_party: string[]
  pitfalls: MicrostationPitfall[]
}

export type ProjectCard = {
  project_id: string
  name: string
  blurb: string
  blurb_source: string
  activity: "active" | "stale" | "abandoned"
  run: "runs" | "unknown"
  entry: CardEntry | null
  last_touched: string | null
  files: number
  languages: { name: string; count: number }[]
  unfinished: {
    todos: number
    fixmes: number
    stubs: string[]
    empty: string[]
    missing_requirements: string[]
  }
  microstation: MicrostationReport | null
}

export type CardBoard = {
  generated_at: string
  source: string
  cards: ProjectCard[]
}

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
  microstation: MicrostationReport | null
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
  CAD: "#c6f54e",
  Notes: "#e7fff3",
}

export type McpToolCount = { tool: string; count: number }
export type McpToolInfo = { name: string; description: string }
export type McpCall = {
  ts: string
  tool: string
  args: string
  bytes: number
  ms: number
  truncated: boolean
  source: string
}
export type McpUsage = {
  counts: McpToolCount[]
  last_call: string | null
  recent: McpCall[]
  tools: McpToolInfo[]
  resource: string
  snippet: string
  link: { state: "registered" | "sample" | "idle"; label: string; last_call: string | null; detail: string }
  scanning: boolean
  demo: boolean
  index_source: string
}
export type McpCheck = {
  id: string
  status: "pass" | "warn" | "fail"
  title: string
  detail: string
  fix: string
}
export type McpDoctor = { generated_at: string; checks: McpCheck[]; snippet: string }
