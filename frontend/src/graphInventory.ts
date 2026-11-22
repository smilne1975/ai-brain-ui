import type { FileRec, Graph } from "./types"

export const MAP_NODE_BUDGET = 180
export const MAP_LINK_BUDGET = 400

type IndexedFile = Pick<FileRec, "id" | "rel" | "name" | "title" | "kind">

export function containingFolder(rel: string) {
  return rel.slice(0, Math.max(0, rel.lastIndexOf("/")))
}

export function inFolder(rel: string, folder: string | null) {
  return folder === null || (folder === "" ? !rel.includes("/") : rel.startsWith(`${folder}/`))
}

export function folderScopes(files: IndexedFile[]) {
  const counts = new Map<string, number>()
  for (const file of files) {
    let folder = containingFolder(file.rel)
    if (!folder) counts.set("", (counts.get("") ?? 0) + 1)
    while (folder) {
      counts.set(folder, (counts.get(folder) ?? 0) + 1)
      folder = containingFolder(folder)
    }
  }
  return [...counts].sort(([first], [second]) => first.localeCompare(second))
}

export function searchFiles<T extends IndexedFile>(files: T[], query: string): T[] {
  const text = query.trim().replaceAll("\\", "/").toLowerCase()
  const words = text.split(/\s+/).filter(Boolean)
  return files.map((file) => {
    const path = file.rel.toLowerCase(), name = file.name.toLowerCase()
    const match = `${path} ${(file.title ?? "").toLowerCase()} ${file.kind}`
    const score = !words.every((word) => match.includes(word)) ? -1 : !text ? 0 :
      path === text ? 4 : name === text ? 3 : name.startsWith(text) ? 2 : path.includes(text) ? 1 : 0
    return { file, score }
  }).filter((row) => row.score >= 0)
    .sort((a, b) => b.score - a.score || a.file.rel.localeCompare(b.file.rel)).map((row) => row.file)
}

export function sliceProjectGraph(graph: Graph, files: IndexedFile[], folder: string | null,
  kinds: Set<string> | null, selectedId: string | null) {
  const pathById = new Map(files.map((file) => [file.id, file.rel]))
  const indexedNodes = graph.nodes.filter((node) => !node.file_id || pathById.has(node.file_id))
  const allowed = indexedNodes.filter((node) => {
    if (node.kind === "project") return true
    const path = node.file_id ? pathById.get(node.file_id) : undefined
    return (!kinds || kinds.has(node.kind)) && (folder === null || (path !== undefined && inFolder(path, folder)))
  })
  const nodesById = new Map(indexedNodes.map((node) => [node.id, node]))
  // Only restore a selection that still exists in the visible index.
  const selectedNode = selectedId ? nodesById.get(selectedId) : undefined
  const neighbors = new Set<string>()
  const incident = []
  const remainder = []
  for (const edge of graph.edges) {
    if (!nodesById.has(edge.source) || !nodesById.has(edge.target)) continue
    if (selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id)) {
      neighbors.add(edge.source === selectedNode.id ? edge.target : edge.source)
      incident.push(edge)
    } else remainder.push(edge)
  }
  const roots = indexedNodes.filter((node) => node.kind === "project")
  const pinned = [...(selectedNode ? [selectedNode] : []), ...roots,
    ...[...neighbors].flatMap((id) => nodesById.has(id) ? [nodesById.get(id)!] : [])]
  const unique = new Map([...pinned, ...allowed].map((node) => [node.id, node]))
  const nodes = [...unique.values()].slice(0, MAP_NODE_BUDGET)
  const ids = new Set(nodes.map((node) => node.id))
  const eligibleEdges = [...incident, ...remainder].filter((edge) => unique.has(edge.source) && unique.has(edge.target))
  const edges = eligibleEdges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).slice(0, MAP_LINK_BUDGET)
  const shownNeighbors = new Set(edges.flatMap((edge) => edge.source === selectedNode?.id ? [edge.target] :
    edge.target === selectedNode?.id ? [edge.source] : []))
  const fileCount = (rows: Graph["nodes"]) => new Set(rows.flatMap((node) => node.file_id && pathById.has(node.file_id) ? [node.file_id] : [])).size
  return { nodes, edges, indexedFiles: files.length, shownFiles: fileCount(nodes),
    omittedNodes: unique.size - nodes.length, omittedLinks: eligibleEdges.length - edges.length,
    hiddenNeighbors: neighbors.size - shownNeighbors.size }
}
