import assert from "node:assert/strict"
import test from "node:test"
import { containingFolder, folderScopes, inFolder, MAP_LINK_BUDGET, MAP_NODE_BUDGET,
  searchFiles, sliceProjectGraph } from "../src/graphInventory.ts"

const file = (rel, kind = "note", title = "") => ({ id: `project:${rel}`, rel, kind, title, name: rel.split("/").at(-1) })
const node = (entry) => ({ id: `n:${entry.id}`, file_id: entry.id, kind: entry.kind })
const root = { id: "root", file_id: null, kind: "project" }
const edge = (source, target, label = "contains", id = `${source}:${target}`) => ({ id, source, target, label })

test("full inventory search can find a file beyond the visual cap and prioritizes matching paths", () => {
  const target = file("research/late/target.md", "note", "Useful reading summary")
  const sibling = file("research/early/target.md")
  const neighbor = file("inputs/reference.txt", "note")
  const files = [...Array.from({ length: 205 }, (_, i) => file(`other/file-${i}.py`, "script")), sibling, neighbor, target]
  const graph = { nodes: [root, ...files.map(node)], edges: [
    ...files.map((entry) => edge(root.id, node(entry).id)), edge(node(neighbor).id, node(target).id, "cites"),
  ] }
  const initial = sliceProjectGraph(graph, files, null, null, null)
  assert.equal(initial.nodes.length, MAP_NODE_BUDGET)
  assert.equal(initial.nodes.some((item) => item.file_id === target.id), false)
  assert.equal(searchFiles(files, "research\\late\\target.md")[0], target)
  assert.equal(searchFiles(files, "useful summary")[0], target)
  const revealed = sliceProjectGraph(graph, files, containingFolder(target.rel), new Set(["script"]), node(target).id)
  assert.equal(revealed.nodes[0].file_id, target.id)
  assert.deepEqual(revealed.nodes.filter((item) => item.file_id).map((item) => item.file_id), [target.id, neighbor.id])
  assert.equal(revealed.indexedFiles, 208)
  assert.equal(revealed.shownFiles, 2)
  assert.equal(revealed.omittedNodes, 0)
  assert.equal(revealed.omittedLinks, 0)
  assert.equal(revealed.hiddenNeighbors, 0)
})

test("excluded and stale nodes do not leak through search, folder counts or edge counts", () => {
  const visible = file("notes/a.md"), excluded = file("private/hidden.md"), another = file("notes-backup/old.md")
  const files = [file("root.md"), visible, another, file("notes/deeper/b.md")]
  const graph = { nodes: [root, ...[...files, excluded].map(node)], edges: [edge(node(visible).id, node(excluded).id)] }
  assert.deepEqual(searchFiles(files, "hidden"), [])
  assert.deepEqual(folderScopes(files), [["", 1], ["notes", 2], ["notes-backup", 1], ["notes/deeper", 1]])
  assert.equal(inFolder(another.rel, "notes"), false)
  assert.equal(inFolder(files[0].rel, ""), true)
  assert.equal(inFolder(visible.rel, ""), false)
  const graphView = sliceProjectGraph(graph, files, null, null, node(excluded).id)
  assert.equal(graphView.nodes.some((item) => item.file_id === excluded.id), false)
  assert.equal(graphView.shownFiles, 4)
  assert.equal(graphView.omittedLinks, 0)
})

test("selected nodes and their links are kept first within both render budgets", () => {
  const files = Array.from({ length: 240 }, (_, i) => file(`folder/${i}.txt`))
  const target = node(files.at(-1)), others = files.slice(0, -1).map(node)
  const graph = { nodes: [root, ...others, target], edges: [
    ...others.flatMap((item) => [edge(item.id, root.id), edge(item.id, others[0].id)]),
    ...others.map((item) => edge(target.id, item.id)),
  ] }
  const rendered = sliceProjectGraph(graph, files, null, null, target.id)
  assert.equal(rendered.nodes.length, MAP_NODE_BUDGET)
  assert.ok(rendered.edges.length <= MAP_LINK_BUDGET)
  assert.equal(rendered.nodes[0].id, target.id)
  assert.equal(rendered.edges.filter((item) => item.source === target.id).length, MAP_NODE_BUDGET - 2)
  assert.equal(rendered.hiddenNeighbors, 239 - (MAP_NODE_BUDGET - 2))
})
