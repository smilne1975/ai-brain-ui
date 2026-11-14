# AI Brain feature backlog

**This file is the master list of AI Brain feature ideas.** On 14 Nov 2026 it was merged with the separate scout list kept by Stu's Grok Bot research routine. That list now just points here, and future research scans add their ideas to this file.

Proposed additions are ranked by estimated value, then effort. They are ideas, not commitments or approved implementation plans. Value runs from 1 to 5, with AEC/BIM relevance scoring higher. Effort is small (S) or medium (M). Numbers are idea identifiers, not GitHub issue numbers. They were renumbered once in the 14 Nov 2026 merge (see *Renumbering* at the end). Ideas #1 and #2 are already built.

Each idea has a one-line summary in the ranked list and fuller notes under *Idea details*: what it would do, dated notes, sources (only pages actually opened), the date added and its status.

## Already built

- **#1 MicroStation Python awareness — S, value 5:** built 2026-10-29 ([b9c2784](https://github.com/smilne1975/ai-brain-ui/commit/b9c27841f924cfe25639a13cd30667c878c15767)).
- **#2 MCP server for Copilot agent mode — M, value 5:** built 2026-10-30 ([99f3327](https://github.com/smilne1975/ai-brain-ui/commit/99f332724fecab2896cfc813efc0add24a65328b)).

Built features to check new ideas against (from the README and commits up to `c6c96cf`, 12 Nov 2026):
- **Skills** radial graph of detected capabilities (skill catalog)
- **Blueprint / Architecture** flowchart per folder and for the whole corpus, with **Ask bar** (retrieval over the redacted index, optional LLM)
- **System** ring (circular meters, one bar per file)
- **Connections** grid (services/APIs mentioned, key *name* present or not)
- **Timeline** (Today / 7 / 30 days, file mtimes + `git log` subjects, Copilot sessions on the day)
- **Project status cards** (Active/Stale/Abandoned, Runs/Unknown, entry point + run command, half-finished signals: TODO/FIXME, stubs, empty files, unlisted imports)
- **Copilot Chat history** reader (workspaceStorage, state.vscdb, transcripts; linked to files)
- **VS Code extension** panel (webview dashboard, auto-starts server, `.vsix` in `releases/`)
- **"Pick up where I left off"** brief + *Copy for new chat* + *Save BRAIN_HANDOFF.md*
- **Daily / Weekly Digest** (+ markdown export to `.brain/digests/`, optional scheduled `BRAIN_DIGEST`)
- **MicroStation Python** awareness (MSPy badge, `*.commands.xml` key-ins → handlers, pitfall chips with copy-a-fix Copilot prompts, key-in nodes on Blueprint, `GET /api/microstation`)
- **MCP server** for Copilot agent mode (read-only tools over the index, registered by the VS Code extension; built as idea #2)
- Also in place: live file watcher refresh, SQLite scan cache, background scanning with progress, secret redaction / `.env` key-names-only, multi-provider LLM (OpenAI, Anthropic, Grok, Ollama) with heuristic no-key mode, `start.bat`/`start.cmd` launcher with port handling

## Ranked ideas

### Value 5/5

- **#3 Dynamo graph reader — M:** Map `.dyn` graphs, packages, Python nodes and compatibility issues.
- **#4 pyRevit map — M:** Show extensions, ribbon buttons, scripts and Revit versions.
- **#5 MicroStation configuration map — M:** Explain WorkSpaces, WorkSets, variables and configuration problems.
- **#6 Revit add-in version map — M:** Map .NET add-ins and flag version or manifest issues.

### Value 4/5

- **#7 Copilot instructions — S:** Draft project instructions from what the brain knows.
- **#8 Project health check — S:** Flag problems and offer Copilot fix prompts.
- **#9 More agent session history — S:** Read Copilot CLI and app sessions; potentially other agents too.
- **#10 Private folders — S:** Keep selected projects out of cloud AI, exports and shared context.
- **#11 Restart families — S:** Group repeated versions of a project and highlight unfinished work.
- **#12 AI cost ledger — S:** Show token use, estimated costs and optional spending limits.
- **#13 Correctable project facts — S:** Mark facts confirmed, inferred or unknown; let users correct them.
- **#14 Finish-it plan — S:** Turn an unfinished project into an ordered checklist.
- **#15 Copilot auto-recall — S:** Give Copilot relevant project context and record its edits.
- **#16 Model-change badge — S:** Distinguish scripts that read a model from those that change it.
- **#17 Waiting on me — S:** Find agent questions, approvals and unverified completion claims.
- **#18 Backup alerts — S:** Flag uncommitted, unpushed or otherwise unbacked-up work.
- **#19 In-use status — S:** Recognise finished tools still in use instead of calling them abandoned.
- **#20 Decision and gotcha memory — M:** Remember why choices were made and what failed before.
- **#21 PDF and standards reader — M:** Search project documents and cite relevant pages.
- **#22 Cross-project connections — M:** Find important hubs, related projects and reused helpers.
- **#23 IFC inspector — M:** Show model versions, storeys, elements and properties.
- **#24 MicroStation standards check — M:** Flag script settings that conflict with CAD standards.
- **#25 IFC requirements check — M:** Compare IFC models with an IDS requirements file.
- **#26 Data-flow map — M:** Show which scripts read and write which files.
- **#27 Revit file inspector — M:** Inspect supported model and family information without opening Revit.
- **#28 Revit journal reader — M:** Link sessions and add-in failures back to projects.
- **#29 IFC version comparison — M:** Show elements and properties changed between model versions.
- **#30 Smaller editing context — M:** Give agents the relevant function and callers instead of whole files.
- **#31 MicroStation Assistant history — M:** Link its conversations and generated scripts to projects; storage location still needs checking.
- **#32 Live MicroStation snapshot — M:** Provide an opt-in, read-only view of the active model and levels.

### Value 3/5

- **#33 Function history — S:** Show the commits behind a function or line.
- **#34 Obsidian export — S:** Export project notes and maps to an Obsidian vault.
- **#35 Task context pack — S:** Pick relevant files for a task within a token budget.
- **#36 Since last visit — S:** Highlight what changed since a project was last opened.
- **#37 Files that change together — S:** Find hidden connections in Git history.
- **#38 MCP and AI-tool inventory — S:** List configured tools and flag those that can write.
- **#39 Index freshness — S:** Warn when an answer may use stale information.
- **#40 Replaced decisions — S:** Keep old decisions while showing which one is current.
- **#41 Project board — S:** Drag projects between statuses such as active, parked and done.
- **#42 Saved answers — S:** Save useful answers and flag them when their sources change.
- **#43 Mermaid export — S:** Copy editable architecture diagrams into documentation.
- **#44 Risk hotspots — S:** Highlight large, frequently changed or unfinished files.
- **#45 Scan coverage — S:** Show which files the brain could not read and why.
- **#46 Launch chains — S:** Map launchers, scheduled tasks and scripts that start other scripts.
- **#47 Knowledge gaps — S:** Find important files that nobody has explained.
- **#48 Rebuild pack — S:** Produce recovery instructions for restoring projects on a new PC.
- **#49 Agent rules inventory — S:** List and compare agent instructions, memories and skills.
- **#50 Terminal history — S:** Link commands run by the user to projects and their timelines.
- **#51 Running-now panel — S:** Show project processes, servers and possible runaways.
- **#52 Secrets in chat logs — S:** Warn about exposed credentials without displaying their values.
- **#53 Speckle migration check — S:** Flag scripts using outdated Speckle interfaces.
- **#54 Related files — M:** Find similar scripts and notes across projects using local search.
- **#55 Explain connections — M:** Show paths between files and how certain each link is.
- **#56 Change impact — M:** Highlight what an uncommitted change may affect.
- **#57 Session size X-ray — M:** Find oversized AI sessions and suggest a fresh handoff.
- **#58 Cross-agent work log — M:** Give agents a shared project log, with lessons subject to user approval.
- **#59 Reusable agent skills — M:** Draft skills from tasks repeatedly performed.
- **#60 Brain map inside Copilot chat — M:** Let users and Copilot inspect the same project map.
- **#61 Verified runs badge — M:** Opt in to a safe check instead of assuming a detected command works.
- **#62 Shareable project page — M:** Export an offline project summary for colleagues.
- **#63 Guided walkthrough — M:** Step through a project's flow and key files.
- **#64 Documentation conflicts — M:** Find where instructions or READMEs disagree with code.
- **#65 ChatGPT and Claude imports — M:** Bring exported conversations into project history.
- **#66 Error history — M:** Link tracebacks to files and show previously successful fixes.
- **#67 Drill-down maps — M:** Zoom from an overview into project parts, files and functions.
- **#68 IFC 3D preview — M:** Inspect IFC models locally in the browser.
- **#69 DWG/DXF inspector — M:** Show drawing metadata, layers and title-block information.
- **#70 Project conventions drift — M:** Find inconsistent approaches such as mixed logging libraries.
- **#71 Run provenance — M:** Record a run's command, versions and inputs so results can be compared.
- **#72 Existing diagram preview — M:** View project draw.io and JSON Canvas files inside AI Brain.
- **#73 Follow the active window — M:** Open the matching project card and brief when you switch to a VS Code, MicroStation or Revit window.

### Value 2/5

- **#74 Project vocabulary — S:** Summarise the terms most associated with each project.
- **#75 Provider failover — S:** Switch AI providers when one fails, subject to privacy settings.
- **#76 Disk-space review — S:** Identify rebuildable files that could be removed after approval.
- **#77 Obsidian/OneNote ingestion — M:** Search notes alongside project files.
- **#78 Chart answers — M:** Show charts for questions about counts and timelines.
- **#79 Measure whether AI Brain helps — M:** Compare answers, time and token use with and without its context.

## Idea details

### #1 MicroStation Python awareness — built

- **What:** Recognise MicroStation Python projects (`MSPyBentley`, `MSPyDgnPlatform`… imports) and parse their `*.commands.xml` key-in tables. Each card and Blueprint node then lists the key-ins the project registers (e.g. `MYREPORT LEVELS`) and the functions they call. It also flags common pitfalls the Bentley guide mentions: duplicate script filenames, which break key-ins, and third-party imports that need `MS_PYTHON` pointed at a matching Python.
- **Sources:** https://developer.bentley.com/documentation/microstation-python-api/guides/developingpythonapps.md
- **Added:** 2026-10-28 · **Status:** built (2026-10-29, https://github.com/smilne1975/ai-brain-ui/commit/b9c27841f924cfe25639a13cd30667c878c15767)

### #2 AI Brain MCP server for Copilot agent mode — built

- **What:** Run the existing index as an MCP server (read-only tools such as `search_projects`, `get_brief`, `get_timeline`, `explain_file`, plus the digest as an MCP resource). Copilot in VS Code could then query Stu's whole project corpus instead of grepping. The existing VS Code extension can register it through `mcpServerDefinitionProviders`, so no manual `mcp.json` is needed. Tools marked `readOnlyHint` skip confirmation.
- **Note (2026-10-30):** Add a local usage tally (which tool Copilot called, answer size, time) and a *doctor* check, so Stu can see whether agent mode actually calls AI Brain. Vesalius found agents often skip such tools until set up right, and keeps exactly this tally. Source: https://github.com/haplollc/Vesalius
- **Sources:** https://code.visualstudio.com/api/extension-guides/ai/mcp · https://github.com/basicmachines-co/basic-memory · https://github.com/Graphify-Labs/graphify · https://github.com/yamadashy/repomix
- **Added:** 2026-10-28 · **Status:** built (2026-10-30, https://github.com/smilne1975/ai-brain-ui/commit/99f332724fecab2896cfc813efc0add24a65328b)

### #3 Dynamo graph reader — value 5, effort M

- **Summary:** Map `.dyn` graphs, packages, Python nodes and compatibility issues.
- **What:** Parse Dynamo JSON (Nodes, Connectors, Inputs/Outputs, `NodeLibraryDependencies`) into a mini-Blueprint per graph. The view shows packages used, embedded Python/DesignScript nodes (text added to the index and Ask bar), Revit API calls, Dynamo Player inputs, and Dynamo version. Cards can then flag a graph that depends on a missing package or an old Dynamo version. Autodesk published an official `.dyn` JSON Schema in Feb 2026, which makes parsing reliable.
- **Note (2026-10-30):** Dynamo 4.2 (Aug 2026, shipped in Revit 2027.3 as 4.2.1) catches pyRevit-style code in Dynamo Python nodes, which the Dynamo runtime can't run, and exposes typed *Define Data* inputs that tools can read without opening the graph. Worth copying both: a "pyRevit code in a Dynamo Python node" pitfall chip, and listing Define Data inputs as the graph's Player inputs. Source: https://dynamobim.org/dynamo-core-4-2-release/
- **Note (2026-10-31):** Dynamo 4.3 (16 Oct 2026) lets Autodesk Assistant edit Python Script and Code Block nodes and stamps each edit with an authorship comment and date, and DynamoMCP can now read the current graph as JSON. The reader can pick up those comments to badge AI-edited nodes (with date) on the graph view, so Stu sees which node code he wrote and which the assistant changed. Source: https://github.com/DynamoDS/Dynamo/wiki/Release-Notes (4.3.0) · https://github.com/DynamoDS/Dynamo/releases/tag/v4.3.0
- **Note (2026-11-02):** Flag Python nodes still set to the IronPython 2.7 or CPython3 engine, which the Dynamo team marks obsolete now that PythonNet3 is the default (Dynamo 4.0 in Revit 2027 migrates CPython nodes automatically and keeps a backup of the original file), and group that backup with its migrated graph instead of counting it as a separate graph. Also flag packages a graph uses that don't yet target .NET 10, which Dynamo 4.x requires. Source: https://archicoder.com/posts/dynamo-vs-pyrevit-2026/ (12 Oct 2026: PythonNet3 default, automatic CPython migration with backup, IronPython 2.7 and CPython3 obsolete, package authors must target .NET 10)
- **Sources:** https://github.com/DynamoDS/Dynamo/pull/16919 · https://docs.pyrevitlabs.io/extensions/
- **Added:** 2026-10-28 · **Status:** idea

### #4 pyRevit map — value 5, effort M

- **Summary:** Show extensions, ribbon buttons, scripts and Revit versions.
- **What:** Detect pyRevit `*.extension` folders and turn the `.tab/.panel/.pushbutton` hierarchy into a "ribbon map" view. It shows each button's `bundle.yaml` title, tooltip, `min/max_revit_version` and engine, the script type (py/cs/dyn), shared `lib/` modules, and event `hooks/`. Add Revit, pyRevit and Dynamo entries to the skill catalog, which has no AEC skills today.
- **Note (2026-10-30):** pyRevit 7.0 (6 Oct 2026) no longer supports Revit versions below 2021 and removed its pre-2021 fallbacks, so the map should flag bundles whose `min_revit_version` or version checks still target pre-2021 Revit. It should also show which engine each script needs (IronPython 2.7, IronPython 3.4 or CPython), since 7.0 reports these per Revit year. Source: https://github.com/pyrevitlabs/pyRevit/releases/tag/v7.0.0.26278%2B2233
- **Sources:** https://docs.pyrevitlabs.io/extensions/
- **Added:** 2026-10-28 · **Status:** idea

### #5 MicroStation configuration map — value 5, effort M

- **Summary:** Explain WorkSpaces, WorkSets, variables and configuration problems.
- **What:** Parse MicroStation configuration files (`*.cfg`, `*.ucf`, legacy `*.pcf`) found in project folders. Follow `%include` / `%if` / `%level` directives and show a per-WorkSet card listing the key variables (`MS_DEF`, `MS_RFDIR`, `MS_ADDINPATH`, `_USTN_WORKSETROOT`…), which level set each one (System → User), and which scripts or add-ins rely on them. Flag common faults: missing trailing `/` on folder values, hard-coded `C:/Users/...` paths, `%lock`ed variables a script tries to override, and `.pcf` projects that still need upgrading to WorkSets.
- **Sources:** https://docs.bentley.com/LiveContent/web/MicroStation-v2026/Help/en/topics/123015/GUID-4B1D4DEF-A362-9896-05C3-D487EF7346C7.html · https://docs.bentley.com/LiveContent/web/MicroStation-v2026/Help/en/topics/123015/GUID-9B0F78CB-DEFE-41E7-BC3A-4E7B47D3F381.html
- **Added:** 2026-10-29 · **Status:** idea

### #6 Revit add-in version map — value 5, effort M

- **Summary:** Map .NET add-ins and flag version or manifest issues.
- **What:** Detect compiled Revit add-ins in project folders: parse `.addin` manifests (AddIn Type, Name/Text, Assembly path, FullClassName, AddInId, VendorId) and the matching `.csproj` (TargetFramework, RevitAPI/RevitAPIUI references or NuGet packages). Each card shows which Revit years the add-in targets, with flags for `net48` projects that must be rebuilt as `net8.0-windows` for Revit 2025+, duplicate `AddInId` GUIDs (Revit refuses to load them), hard-coded `bin\Debug` assembly paths, and `FullClassName` values that match no class in the scanned C#. Complements idea #4, which only covers pyRevit scripts.
- **Note (2026-11-01):** Revit 2027 moved to .NET 10, so the year map needs a third band: `net48` up to 2024, `net8.0-windows` for 2025–2026, `net10.0-windows` (SDK 10.0.100, `global.json`) for 2027. Also flag `.addin` manifests installed for all users under `C:\ProgramData\Autodesk\Revit\Addins\<year>`, which Revit 2027 no longer reads (all-user add-ins now live under `C:\Program Files\Autodesk\Revit\Addins\<year>`), and show the new 2027 `ManifestSettings` (`ContextName`, `PublicAssemblies`, `Dependencies`) when present. Source: https://blog.autodesk.io/revit-2027-sdk-net-10-api-changes-and-additions/
- **Note (2026-11-07):** When parsing Revit/C# add-in code for the year map, blank `#if` / `#elif` / `#endif` preprocessor branches (byte-length preserving) before tree-sitter runs, so a `#if REVIT2025` block no longer closes a class early and drops later members or API calls the card needs. Source: https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.103 (0.9.103, 6 Nov 2026 03:35 AEDT: C# preprocessor directives blanked before parse)
- **Sources:** https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API/files/Revit_API_Developers_Guide/Introduction/Getting_Started/Using_the_Autodesk_Revit_API/Revit_API_Revit_API_Developers_Guide_Introduction_Getting_Started_Using_the_Autodesk_Revit_API_NET8_Update_html.html · https://help.autodesk.com/cloudhelp/2025/ITA/Revit-API/files/Revit_API_Developers_Guide/Introduction/Add_In_Integration/Revit_API_Revit_API_Developers_Guide_Introduction_Add_In_Integration_Add_in_Registration_html.html
- **Added:** 2026-10-30 · **Status:** idea

### #7 Copilot instructions — value 4, effort S

- **Summary:** Draft project instructions from what the brain knows.
- **What:** Opt-in button on each card, alongside *Save BRAIN_HANDOFF.md*: generate `.github/copilot-instructions.md` (or `AGENTS.md`) from what the scan already knows: stack, entry point, run command, conventions, known gotchas, and "query AI Brain first". Every new Copilot chat in that folder then starts with that context, so Stu doesn't have to paste the handoff.
- **Note (2026-10-30):** Include a short "scope map" (area → folder globs, e.g. `keyins: commands/**`, `reports: src/reports/**`) so Copilot searches the right folder first instead of grepping the whole tree; prefixer reports 53–92% less search output across 18 repos with such a map. Source: https://github.com/Albisourous/prefixer
- **Note (2026-10-31):** Keep the generated file short (about 60–80 lines) and put detail in linked notes that each start with a one-line `description:`, so Copilot reads the summary first and opens only the notes the task needs. Mark replaced notes *superseded* so they drop out of what is read by default. Source: https://github.com/shoitzsx/obsidian-second-brain
- **Note (2026-11-02):** When regenerating a file that already exists (instructions, `AGENTS.md`, handoff), check the new text before writing it: refuse and show a diff if it shrank sharply, turned into a placeholder, or dropped most of the hard facts (paths, commands, version numbers) the old version had, so a bad LLM run can't quietly wipe out good instructions. Source: https://github.com/yaguete/second-brain (new 2 Nov 2026 07:23 AEDT: write guards check each page's title, that it didn't collapse into a placeholder or shrink drastically, and that it kept at least 90% of the old version's hard facts)
- **Sources:** https://code.visualstudio.com/docs/copilot/customization/custom-instructions · https://github.com/Graphify-Labs/graphify
- **Added:** 2026-10-28 · **Status:** idea

### #8 Project health check — value 4, effort S

- **Summary:** Flag problems and offer Copilot fix prompts.
- **What:** A per-project "health" tab that lists concrete problems: secrets or passwords written into code, hard-coded local paths (e.g. `C:\Users\...` or a fixed MicroStation workspace), oversized files that are risky to edit, unused files and unreferenced scripts. Each finding comes with a ready-to-paste Copilot prompt to fix it. It builds on the existing redaction and half-finished signals, which flag issues but don't turn them into fixes.
- **Note (2026-10-31):** Give each finding a severity badge (P0 critical, e.g. a committed password; P1 high, e.g. a hard-coded workspace path; P2 medium, e.g. an oversized file) so Stu fixes the worst first, plus a *Fix all* button that copies one Copilot prompt covering every finding with its file and line. Source: https://www.greptile.com/docs/changelog (severity badges, 28 Mar 2026; *Fix All* sends every issue to the coding agent at once, 6 Mar 2026)
- **Sources:** https://github.com/haydenschmitty/floorplan
- **Added:** 2026-10-29 · **Status:** idea

### #9 More agent session history — value 4, effort S

- **Summary:** Read Copilot CLI and app sessions; potentially other agents too.
- **What:** Extend the Copilot history reader beyond VS Code `workspaceStorage` to Copilot CLI and GitHub Copilot app sessions, which are stored as `~/.copilot/session-state/<session-id>/events.jsonl` (plus plans and checkpoints). They are matched to project folders and shown on the Timeline and in briefs next to VS Code chats. Also check the current reader still catches new VS Code chats, since the Copilot harness (the default since VS Code 1.142) runs sessions through the separate Agent Host.
- **Note (2026-11-01):** If Stu also tries Claude Code, Codex or Gemini CLI, read their local transcripts the same way (`~/.claude/projects/<slug>/<id>.jsonl`, `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, `~/.gemini/tmp/<alias>/chats/session-*.jsonl`), so one Ask-bar search like "the chat where I fixed the level export" covers every agent and returns the matching lines word for word, saying plainly when nothing matches. Source: https://github.com/arm-pz/session-retrace (31 Oct 2026: searches the transcripts Qoder, Claude Code, Codex and Gemini CLI keep on disk, ranks matches with verbatim evidence, never invents a session)
- **Sources:** https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference · https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/chronicle · https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/session-data · https://code.visualstudio.com/updates/v1_144
- **Added:** 2026-10-29 · **Status:** idea

### #10 Private folders — value 4, effort S

- **Summary:** Keep selected projects out of cloud AI, exports and shared context.
- **What:** Let Stu mark folders (e.g. a client project under NDA) as *private* in `.brain/`. Their contents never go to a cloud LLM provider (Ask bar and briefs fall back to Ollama or heuristic mode), never appear in exports or handoffs, and stay hidden from the planned MCP server. The rule is checked at every point that reads files, and a broken rule blocks sending until fixed. Redaction today hides secrets inside files; this hides whole folders.
- **Note (2026-11-01):** Enforce the rule for Copilot agent mode too: ship (with idea #15) a `preToolUse` hook that returns `permissionDecision: "deny"` with a reason when the agent tries to read a file in a private folder or a credential path (`.env` but not `.env.example`, `~/.ssh/`, `*.pem`, `*.pfx`, `credentials.*`), so the agent picks another route instead of pulling the file into its transcript. Keep the check fast: per the VS Code docs a command error denies the call, but a timeout falls through to normal permissions. Sources: https://github.com/thiensubs/kimi-plugin-codebase-memory (new 1 Nov 2026 18:13 AEDT: C `PreToolUse` secret guard that blocks credential-path reads and secret-shaped values and writes the reason back to the model) · https://code.visualstudio.com/docs/copilot/customization/hooks (Copilot `preToolUse` deny decision; errors deny, timeouts fall through)
- **Note (2026-11-07):** Extend the private/redaction gate to *content* as well as folders: when indexing or sending text to a cloud LLM, refuse by default anything that looks like a raw database connection string or an unsafe server/file path over HTTP, with a clear reason, and require an explicit opt-in to allow those shapes (same idea as refusing credential paths). Source: https://github.com/topoteretes/cognee/releases/tag/v1.6.7 (1.6.7, 7 Nov 2026 04:15 AEDT: raw DB connection strings and unsafe server/file paths refused by default)
- **Sources:** https://sourcegraph.com/changelog (19 Oct 2026: context filters keep excluded repos and files invisible to agents at every point; invalid rule blocks everything)
- **Added:** 2026-10-30 · **Status:** idea

### #11 Restart families — value 4, effort S

- **Summary:** Group repeated versions of a project and highlight unfinished work.
- **What:** Group folders that are restarts of the same tool (`levels_report`, `levels_report_v2`, `levels_report - Copy`, `new_levels_final`) by name similarity and shared files, mark which one is current, and show the family as one card with its history. The Digest gains an "open loops" list: tools restarted two or more times, or edited for weeks with no commit, run command or finished signal, so Stu can pick one to finish or archive. Idea #22 finds copied helpers; this finds whole-project restarts.
- **Sources:** https://github.com/Yutiao-xX/silent-reflect (rule-based screening for stalled notes, repeated restarts and churn without closure before any model runs; weekly "open loops")
- **Added:** 2026-10-30 · **Status:** idea

### #12 AI cost ledger — value 4, effort S

- **Summary:** Show token use, estimated costs and optional spending limits.
- **What:** Log every LLM call AI Brain makes (Ask bar, briefs, digests, Blueprint summaries, MCP replies): provider, model, tokens in/out, estimated cost and which feature triggered it. Show a small spend meter in the header and a weekly line in the Digest, with an optional monthly cap that switches to Ollama or heuristic mode when hit. Stu paused the auto-builder over token use, so this shows exactly what AI Brain itself is spending.
- **Note (2026-11-01):** Log cached input tokens separately, and when the provider is Anthropic, mark AI Brain's long, fixed system prompts (brief, digest, Blueprint summary) for prompt caching so repeat calls cost less; add a setting to turn it off for gateways that reject it. Source: https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.100 (0.9.100, 1 Nov 2026 11:53 AEDT: Claude backend caches its stable system prompt with `cache_control`, counts cached tokens back into `input_tokens`, `GRAPHIFY_CLAUDE_PROMPT_CACHE=0` turns it off)
- **Sources:** https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.96 (0.9.96, 25 Oct 2026: every `extract` run writes token usage to a `cost.json` ledger kept as cost history)
- **Added:** 2026-10-30 · **Status:** idea

### #13 Correctable project facts — value 4, effort S

- **Summary:** Mark facts confirmed, inferred or unknown; let users correct them.
- **What:** Tag each fact on a project card (purpose, entry point, run command, Python or host-app version, status) as *confirmed*, *inferred* or *unknown*, with the files it came from. A *Questions* list asks Stu about the unknowns, and a *Correct this* button lets him fix a wrong fact. Answers and corrections are saved in `.brain/` and kept across rescans, so he only fixes a guess once. Idea #41 overrides status only and idea #64 settles docs-vs-code clashes; this covers every card fact.
- **Note (2026-10-31, From Second Brain):** Show the date each fact was last confirmed next to its source, and drop a confirmed fact back to *unconfirmed* when no fresh evidence (rescan match, commit or Stu's OK) has backed it for 30 days. When a new scan contradicts a confirmed fact, ask Stu instead of quietly overwriting it. Source: https://x.com/Argona0x/status/2111837226006921640 (Argona: every page shows claim, source and last-confirmed date; 30 days without a fresh source → unconfirmed; the checker tags you instead of overwriting)
- **Note (2026-11-01):** When the LLM (not a plain rule) supplies a fact or theme, require a short verbatim quote from the file it came from and check that the quote really appears in that file before accepting it; a fact whose quote can't be found is kept as *unknown*. Hovering a fact shows the quote. Source: https://github.com/ShayanHemm/second-brain (1 Nov 2026 AEDT: every theme and estimate must be backed by a quote from the entry, and the page checks the quotes against the text before accepting them)
- **Sources:** https://github.com/1npo/codebase-dossier (every claim marked confirmed, inferred or unknown with cited files; `/dossier confirm` and `/dossier correct`, which survive rebuilds)
- **Added:** 2026-10-30 · **Status:** idea

### #14 Finish-it plan — value 4, effort S

- **Summary:** Turn an unfinished project into an ordered checklist.
- **What:** A *Finish this* button on a Stale or Abandoned card that turns the existing half-finished signals (stub functions, empty files, unlisted imports, missing entry point or run command, unanswered unknowns) into an ordered checklist of what must exist first before the tool can run, e.g. "1. add `requirements.txt` → 2. fill `export_levels()` stub → 3. wire key-in to handler". It asks Stu one question at a time about the gaps it can't infer, and each step carries a copy-ready Copilot prompt; Stu ticks steps off and the plan is saved in `.brain/`. Idea #11 picks which loop to close; this says how to close it.
- **Sources:** https://github.com/KingofNothing07/Project_Mentor-Brainstorm_to_Build_Anything (work-in-progress intake for half-finished projects, reverse flowchart = "what must exist first, the build order", one question at a time, approved changes only)
- **Added:** 2026-10-31 · **Status:** idea

### #15 Copilot auto-recall — value 4, effort S

- **Summary:** Give Copilot relevant project context and record its edits.
- **What:** Offer a one-click install of a personal Copilot hook (`~/.copilot/hooks/ai-brain.json`, so it applies in every repo) that VS Code agent mode, Copilot CLI and the Copilot app all run. At session start it adds a short AI Brain brief for the open folder, and on each prompt it adds up to 3–5 matching projects, files or gotchas from the index, only when at least two independent terms match. A post-tool hook sends each file Copilot edits to AI Brain, so Copilot's work shows on the Timeline and in briefs even when no chat log is found. This puts AI Brain into the session without Copilot having to decide to call the MCP tools (agents often skip them). The hook runs a Python or `node` command, not a PowerShell script, because the work PC blocks unsigned scripts.
- **Note (2026-11-01):** Let Stu pin a few rules as *always inject* (e.g. "never save over the live DGN", "Revit 2025+ add-ins need .NET 8") so the hook adds them on every prompt in that project regardless of the two-match gate and token budget, while ordinary memories still go through relevance. Show a small density score per injected memory (repeated, vague or not actionable) so low-value text is trimmed before it costs tokens. Source: https://github.com/EaveBounty/agent-memo-harness (1 Nov 2026 AEDT, v0.1.1: force rules never dropped by the budget, auto rules only above a relevance threshold, redundancy/specificity/actionability density score)
- **Sources:** https://code.visualstudio.com/docs/copilot/customization/hooks (Preview: hooks "add context… without relying on the model to request the action"; VS Code, Copilot app and Copilot CLI share one hook format; personal hooks in `~/.copilot/hooks/`) · https://github.com/dizeldz20-ux/claude-second-brain (session-start "recall before you read" rule, per-prompt injection of up to 5 nodes behind a two-match noise gate, post-tool edit stream buffered when the server is down) · https://github.com/katolikov/kanerva (per-prompt memory injection under a token budget, Copilot CLI plugin)
- **Added:** 2026-10-31 · **Status:** idea

### #16 Model-change badge — value 4, effort S

- **Summary:** Distinguish scripts that read a model from those that change it.
- **What:** Mark each Revit, Dynamo and MicroStation script or add-in as *Read-only* (reports, CSV/Excel export) or *Changes the model*, using plain code patterns and no LLM: a Revit `Transaction` that is started and committed (or Dynamo's `TransactionManager` transaction in a Python node), element create, delete or set-parameter calls, and MicroStation element add, replace, delete or save calls. The badge shows on cards, the pyRevit ribbon map (#4) and the Dynamo graph view (#3), with the `file:line` that set it, so Stu knows which tools to run only on a saved or detached copy. Idea #38 flags write-capable MCP servers and #26 tracks data files; this covers his own scripts.
- **Note (2026-11-02):** Read pyRevit's own markers too: functions decorated with `@automation.operation(..., effects=("model.read",), inputs=(...))` declare their effect and typed inputs, so the badge can use the declared effect as evidence and flag a marker that says `model.read` while the code still opens a `Transaction`. Source: https://github.com/pyrevitlabs/pyRevit/pull/3884 (merged 2 Nov 2026 09:01 AEDT: marked operations declare `effects` and typed `inputs`; only query/pure functions that open no transaction can be run by the agent)
- **Sources:** https://github.com/arenchichmanian/revit-sleeves-qc (31 Oct 2026: Dynamo CPython3 scripts for Revit listed with a "Changes the model?" column; the check script only writes a CSV, the fix script writes to the model, "save the file first") · https://www.revitapidocs.com/2025/308ebf8d-d96d-4643-cd1d-34fffcea53fd.htm (any change to a Revit document needs an open `Transaction`; changes become part of the document only on `Commit`)
- **Added:** 2026-11-01 · **Status:** idea

### #17 Waiting on me — value 4, effort S

- **Summary:** Find agent questions, approvals and unverified completion claims.
- **What:** From the Copilot chats AI Brain already reads (and later CLI sessions, #9), list the sessions where the ball is with Stu: the agent's last turn asked him a question or for approval and he never replied, or the agent said "done"/"fixed" but nothing in the session ran, built or tested the change (no terminal run, test or later commit). Each entry shows the project, the one-line ask or claim, its age and a *Reopen chat* / *Copy follow-up prompt* button, and the list sits in the "pick up where I left off" brief and the Digest. Idea #11 finds stalled projects and #58 counts session size; this finds the specific conversations waiting on him.
- **Note (2026-11-05):** Also list the TODOs said in those chats ("we still need to backfill…", "remember to document it in the deploy guide") as open items linked to the exact message, and tick each one off when a later message or commit closes it, so promises made mid-session don't get lost when the chat scrolls away. Source: https://github.com/deanyool/lorevault (new 3 Nov 2026 12:13 AEDT: reads Claude Code, Codex and Cursor history offline, extracts decisions, rules, gotchas and open TODOs, each with a backlink to its source message, closes TODOs, `lore todos`)
- **Sources:** https://github.com/PudinKiller/brain-network (31 Oct 2026 AEDT: Obsidian map of project "brains" showing who holds the ball on each item, you or an agent, which decisions wait on you with one clear question, "done means checked") · https://github.com/HeshamSayed/hmind (Claude Code plugin, v0.7.2: "Honest status", a "done" with nothing tested, built or run is flagged)
- **Added:** 2026-11-01 · **Status:** idea

### #18 Backup alerts — value 4, effort S

- **Summary:** Flag uncommitted, unpushed or otherwise unbacked-up work.
- **What:** A *Needs backup* list and card badge for work that exists only on this PC: git projects with uncommitted changes or commits not pushed, local branches never pushed, repos with no remote at all, and project folders that aren't git repos yet hold recent edits, each with its age and size (e.g. "levels_report: 14 files changed over 9 days, never pushed"). A fast-forward-only *Fetch* can refresh ahead/behind counts, and AI Brain never pushes or commits for Stu. The Digest lists the oldest unbacked work first, so a lost or reimaged work PC doesn't take months of scripts with it. Idea #36 lights up changes since his last visit and #49 (rebuild pack) describes the setup; this shows what isn't saved anywhere else.
- **Sources:** https://github.com/suhailaleryani/DevFileExplorer (new 2 Nov 2026 09:24 AEDT: Windows project dashboard with a *Needs attention* view listing uncommitted changes, unpushed commits, branches never pushed and commits behind the remote; repos with no remote never flagged as unpushed; fetch-all and fast-forward-only pull, push deliberately left out)
- **Added:** 2026-11-02 · **Status:** idea

### #19 In-use status — value 4, effort S

- **Summary:** Recognise finished tools still in use instead of calling them abandoned.
- **What:** Stop marking a finished tool as Stale or Abandoned just because its code hasn't changed. A project gets an *In use* status, with the evidence shown, when something on the PC still points at it: a pyRevit extension path (#4), a MicroStation `MS_ADDINPATH` / `MS_MACRO` or WorkSet variable (#5), a Revit `.addin` assembly path (#6), a Task Scheduler job, VS Code task or shortcut (#46), an MCP config (#38), or when its output files keep changing while its code doesn't. Cryptic folders (`test`, `New folder (3)`, `0614`) also get a readable name from their README title or the document they produced, with the real folder name kept underneath. Idea #41 lets Stu override status by hand; this gets the common case right without him.
- **Sources:** https://github.com/epoko77-ai/vibestrata (new 3 Nov 2026 15:44 AEDT: local dashboard of AI-made projects; *In use* state when a skill, launch agent, MCP server or shell alias points at a finished tool, or its outputs keep changing while its code doesn't; readable names from the README title or the document a folder produced)
- **Added:** 2026-11-05 · **Status:** idea

### #20 Decision and gotcha memory — value 4, effort M

- **Summary:** Remember why choices were made and what failed before.
- **What:** Pull typed memories (decision / gotcha / constraint / preference) from `decisions.md` files, commit subjects and Copilot chats, store them as plain markdown under `.brain/memory/`, and link each one to the files it concerns. Briefs, cards and the Ask bar can then answer "why did I switch away from X?" and show the reason next to the code.
- **Note (2026-10-30):** Mine the Copilot chats for Stu's corrections ("no, don't…", rejected edits) as gotcha drafts that he OKs in one click, then count per week whether the same mistake comes back, so each lesson shows if it helped. Source: https://github.com/ursalfas11/self-improving-brain
- **Note (2026-10-30):** Record which chat, commit or file each memory came from, so that when Stu deletes a chat, marks a folder private (idea #10) or rejects a source as wrong, a *Forget source* action removes every memory drawn from it, keeping any that another source still backs. Source: https://github.com/govinargo-labs/cheesedb
- **Note (2026-11-01):** Anchor each memory to the exact lines it is about and store a SHA-256 of those lines. On rescan, mark it *shifted* when the same text has moved (update the line numbers quietly) and *stale* when the text itself changed, so a gotcha about code that has since been rewritten is flagged instead of shown as current. Source: https://github.com/ArthurC02/Domain-Memory-PlugIn (new 1 Nov 2026 18:40 AEDT: every rule cites the source lines that enforce it with a SHA-256; changed code reports the citation as `shifted` or `stale`; agents only propose candidates, nothing counts until reviewed)
- **Note (2026-11-05):** Keep *dead ends* as a memory type too: a fix Copilot tried that didn't work (error, attempted fix, why it failed, files) and designs Stu rejected on purpose, so briefs, the hooks (#15) and the MCP server can say "already tried, failed because…" before the same fix is suggested again. A dead end can be reopened with a reason when a dependency or requirement changes. Source: https://github.com/msking18/agent-memory-mcp (new 3 Nov 2026 23:03 AEDT: `record_dead_end` / `check_dead_ends` with `error_loop` and `architectural` kinds, `reopen_dead_end`, notes anchored to files with a staleness warning)
- **Note (2026-11-07):** Keep an *incident ledger* beside decisions and gotchas: short "happened once, never again" records (symptom, root cause, fix, files) filled from chats and commits, so a new Copilot session is warned before it reintroduces a regression the team already paid for. Source: https://github.com/egecagintepe/agent-project-onboarding (new 5 Nov 2026 19:18 AEDT: 8-dossier AGENTS.md onboarder with an incident ledger methodology, "Happened Once, Never Again")
- **Note (2026-11-13):** Before saving a new memory, check for similar ones already stored and show "similar to …" next to the draft. Ask Stu whether to merge them, keep both until he decides, and never merge or delete on its own, so a retried save can't quietly duplicate or overwrite a lesson. Source: https://github.com/basicmachines-co/basic-memory/commit/a2e7f7d55dcfa7b3dd67f575c0639b3dbd787b8f (11 Nov 2026 13:39 AEDT: memory-ingest asks the user before merging a similar note and keeps both notes until they decide) · https://github.com/basicmachines-co/basic-memory/commit/3dda18fbfaae4dc871918a94d8c019722dcef52a (similar-notes advice made informational, no automatic edit or delete)
- **Sources:** https://github.com/insomnolence/thalamus · https://github.com/tigerless-labs/agent-memory · https://github.com/lopax76/second-brain
- **Added:** 2026-10-28 · **Status:** idea
- **Note (2026-11-13, From Second Brain):** Add an optional 'dreaming' pass that reads past run and agent logs and suggests new memories, which Stu approves before they're saved. Source: https://x.com/Aura_lixx/status/2117406964636647858 (promo for an Anthropic engineer's harness workshop; original source not linked)

### #21 PDF and standards reader — value 4, effort M

- **Summary:** Search project documents and cite relevant pages.
- **What:** The scanner skips `.pdf` today. Extract text locally (pypdf) from PDFs inside project folders, such as BIM execution plans, client CAD/BIM standards and API docs, so they show up in the Ask bar, Skills and Blueprint. They would link to the scripts that implement them. The existing redaction and per-project file caps apply.
- **Note (2026-11-02):** Many client standards and old BIM plans are scanned image-only PDFs with no text layer. Run offline OCR (RapidOCR) on the first ~15 pages of those, and record a plain reason for each file that still yields no text ("no text layer", "encrypted", "damaged") so it shows in the coverage view (#45) instead of silently missing. Source: https://github.com/bslnssb/second-brain (new 1 Nov 2026 AEDT: local SQLite FTS5 document search, offline OCR of image-only PDFs, PDF/DOCX/PPTX/XLSX, per-file failure reasons, Windows exe)
- **Sources:** https://github.com/Graphify-Labs/graphify · https://github.com/crow-hq/crow-desktop (also reads `.docx`, `.pptx`, `.xlsx`/CSV with one note per sheet: worth covering Word/Excel standards and schedules too, not just PDF)
- **Added:** 2026-10-28 · **Status:** idea

### #22 Cross-project connections — value 4, effort M

- **Summary:** Find important hubs, related projects and reused helpers.
- **What:** Rank the most-connected files and concepts (PageRank) and cluster the corpus into communities (Louvain/Leiden). Show "surprising connections" between projects, such as the same helper copied into three folders or two projects sharing one prompt. This gives a new lens on the whole corpus that Blueprint's per-folder flowcharts don't provide, and it can be exported as a one-page `GRAPH_REPORT.md`.
- **Sources:** https://github.com/Graphify-Labs/graphify · https://github.com/lopax76/second-brain
- **Added:** 2026-10-28 · **Status:** idea

### #23 IFC inspector — value 4, effort M

- **Summary:** Show model versions, storeys, elements and properties.
- **What:** When a project folder contains `.ifc` files, use IfcOpenShell to add a card section with schema version, storeys, entity counts by class and property sets. It would also link the scripts that open those files. Optionally expose a few ifcMCP-style tools (entities in a space, properties of an element) through the Ask bar or idea #2.
- **Sources:** https://github.com/smartaec/ifcMCP
- **Added:** 2026-10-28 · **Status:** idea

### #24 MicroStation standards check — value 4, effort M

- **Summary:** Flag script settings that conflict with CAD standards.
- **What:** Let Stu keep one standards file (level names, colours, line styles and weights, text and dimension styles) in `.brain/` or a project, then list every level, style and colour name that his MicroStation scripts and configs hard-code. Names that aren't in the standard are flagged on the card, so a script that would create an off-standard level is caught before it runs on a real drawing.
- **Sources:** https://github.com/Slayer-F1/microstation-agent-skills
- **Added:** 2026-10-29 · **Status:** idea

### #25 IFC requirements check — value 4, effort M

- **Summary:** Compare IFC models with an IDS requirements file.
- **What:** When a project folder holds both an `.ids` (buildingSMART Information Delivery Specification) and `.ifc` files, run IfcTester locally and show pass/fail per specification on the card, e.g. "Walls: Pset_WallCommon.IsExternal missing on 112 of 340". The full HTML/BCF report can be saved under `.brain/`. It builds on idea #23 (IFC inspector) and turns "what is in the model" into "does the model meet the client's requirements".
- **Note (2026-11-07):** When a project folder holds an IDS (or other acceptance profile) together with IFC *and* drawings/schedules, also flag *cross-file seams* (e.g. fire wall REI60 in the requirement vs REI30 on the element GUID in the model, or a cover thickness that differs between model and sheet), keep each finding with clause/storey/GUID, and optionally write a BCF under `.brain/` for Stu to open in his checker. Source: https://github.com/KonkovDV/AeroBIM (updated 7 Nov 2026 AEDT: pack-gateway cross-check of IFC, IDS, drawings and schedules; fail-closed pack flag; HTML/JSON/PDF/BCF out)
- **Sources:** https://docs.ifcopenshell.org/ifctester.html · https://github.com/LTplus-AG/ifc-lite
- **Added:** 2026-10-30 · **Status:** idea

### #26 Data-flow map — value 4, effort M

- **Summary:** Show which scripts read and write which files.
- **What:** Find the file paths and patterns Stu's scripts read and write (`open()`, `pandas.read_csv`/`to_excel`, `openpyxl`, `csv`, `sqlite3`, `json.dump`, MicroStation/Revit open-and-save calls, plus `.dgn`/`.rvt`/`.ifc`/`.xlsx` paths written as strings) and draw them as "reads"/"writes" edges to data-file nodes on the Blueprint, with the file and line each came from. Stu can then see chains across projects, such as one tool writing `levels.csv` that another tool reads, and which outputs nothing uses any more. Idea #46 covers what starts what; this covers what data moves between tools.
- **Sources:** https://github.com/RepoLadder/repoladder (every arrow traced to code with file:line evidence, including database reads and writes and calls by URL) · https://github.com/fatjon-kalemaj/accretion (lifts the Graphify code graph to services, HTTP calls, events and data stores, each fact keeping its file and line)
- **Added:** 2026-10-31 · **Status:** idea

### #27 Revit file inspector — value 4, effort M

- **Summary:** Inspect supported model and family information without opening Revit.
- **What:** When a project folder holds `.rvt` projects or `.rfa` families, read them from disk with the open-source RvtIO CLI (no Revit or Revit API needed) and add a card section with the Revit version each file was saved in, project information, and element counts by category. Cards can then flag models or families saved in a newer Revit than the scripts and add-ins next to them target (ties to ideas #4 and #6), and an optional *Export IFC* hands the model to the IFC inspector (#23). Today `.rvt`/`.rfa` are opaque binaries to the scanner.
- **Note (2026-11-01):** A second open-source reader, **rvt-open** (Apache-2.0, Rust CLI plus Python bindings), opens `.rvt`/`.rfa`/`.rte`/`.rft` from Revit 2008 to 2027 and decodes typed elements, storeys, rooms and saved parameters from 2015 on. It covers Revit 2027 files, which RvtIO was only tested up to 2026, and its `rvt-schedule` (CSV schedules) and `rvt-sheet` (plan SVG) give the card a schedule and plan preview; `rvt-ifc` and `rvt-gltf` can feed the IFC inspector (#23) and the 3D preview (#68). Use whichever reader opens the file, and show the export's own diagnostics (what was approximated or left out) on the card. Source: https://github.com/helenkwok/rvt-open (new 1 Nov 2026 16:55 AEDT)
- **Note (2026-11-07):** A third reader option, **revit-free** / `rvttool` (pure Python, OLE + shared-window deflate, no Revit), extracts element trees with names (levels, views, families, sheets), wall location lines, a 2D plan SVG, and a FreeCAD macro / DXF-per-level export — useful when RvtIO or rvt-open isn't available, and for a lightweight plan preview on the card. Still early (Revit 2017 samples validated; solid tessellation incomplete). Source: https://github.com/carlosdanielmirandadelima-blip/revit-free (new 7 Nov 2026 06:59 AEDT)
- **Sources:** https://github.com/mahach666/RvtIO (31 Oct 2026, v0.1.0 preview: reads `.rvt`/`.rfa` metadata, project info, elements and parameters without Revit; exports compact JSON or IFC2X3; tested on Revit 2020–2026 files, read-only)
- **Added:** 2026-10-31 · **Status:** idea

### #28 Revit journal reader — value 4, effort M

- **Summary:** Link sessions and add-in failures back to projects.
- **What:** Read Revit's own session journals (`%LOCALAPPDATA%\Autodesk\Revit\Autodesk Revit <year>\Journals`, one text file per session, highest number = newest) for each installed Revit year, using plain pattern rules and no LLM. Each session becomes a Timeline entry (Revit year, start/end, models opened), and lines naming Stu's own add-ins are linked to their project cards: loaded, *Failed to initialize the add-in* (assembly missing), or Revit closed after the add-in with `ExceptionCode=0xe0434352`. The card then shows "last seen in Revit 2026 on 30 Oct: failed to load, DLL missing", so Stu learns his add-in broke without opening Revit. Idea #6 checks the `.addin` manifests and code; idea #66 reads logs inside project folders; this reads what Revit itself recorded when it ran them.
- **Sources:** https://help.autodesk.com/cloudhelp/2024/ENU/Revit-GetStarted/files/GUID-477C6854-2724-4B5D-8B95-9657B636C48D.htm (a new journal per session, start to stop) · https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-read-the-journal-file-Revit.html (journal folder per Revit year) · https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Failed-to-initialize-the-add-in-because-the-assembly-does-not-exist.html (updated 7 Oct 2026: add-in assembly-not-found message and the `ExceptionCode=0xe0434352` journal line when Revit then closes) · https://github.com/aaronrumple/Revit-Matrix (new 31 Oct 2026, C#: streams Revit journal files live while you work; README is one line, so used only as the prompt)
- **Added:** 2026-11-01 · **Status:** idea

### #29 IFC version comparison — value 4, effort M

- **Summary:** Show elements and properties changed between model versions.
- **What:** When a project folder holds two or more versions of the same IFC model (e.g. `model_rev02.ifc` and `model_rev03.ifc`, or an `.ifc` that changed between git commits or scans), run IfcDiff locally and show what changed on the card and Timeline: elements added, deleted and changed by IFC class, plus the old and new value of each changed property, type, container or classification, e.g. "rev03: 14 walls changed (Pset_WallCommon.FireRating), 6 doors added on Level 2". The changed-property table can be saved as CSV under `.brain/`, and a script that wrote the newer file (#26) is linked to it, so Stu sees what his own export or fix script actually did to the model. Builds on the IFC inspector (#23); IDS (#25) checks one model against rules, this compares two models.
- **Sources:** https://docs.ifcopenshell.org/ifcdiff.html (IfcDiff CLI and Python library: Added / Deleted / Changed GlobalIds, optional type, property, container, aggregate and classification checks, JSON output) · https://github.com/BIMvoice/ifcdelta (new 1 Nov 2026 AEDT: old vs new IFC, one row per changed property with old and new values, CSV export, re-exported elements whose GlobalId changed paired by content instead of a false delete and add, changes under 1 mm ignored as export noise)
- **Added:** 2026-11-01 · **Status:** idea

### #30 Smaller editing context — value 4, effort M

- **Summary:** Give agents the relevant function and callers instead of whole files.
- **What:** Add a `get_edit_context(symbol)` tool to the AI Brain MCP server that returns, within a fixed budget of about 4,000 tokens, the function's body, a skeleton of its file (imports, classes, constants and signatures without the other bodies) and each caller's call site with a few lines either side; files under about 300 lines come back whole. A companion *safe to rename or delete?* tool also counts string references such as `getattr` names and MicroStation key-in tables, so a handler only called from `*.commands.xml` never shows "0 callers". An optional Copilot `preToolUse` hook (with #15) stops agent mode reading a whole Python or C# file over about 300 lines and hands back that file's function list with line ranges instead, and each reply logs tokens returned against the size of the files touched, so the ledger (#12) shows what was saved. Idea #35 builds a pack for Stu to paste; this keeps Copilot's own reads small while it edits his large MicroStation and Revit scripts.
- **Sources:** https://github.com/erayerturk/surgical-context-mcp (new 1 Nov 2026 21:44 AEDT: Tree-sitter + SQLite code graph MCP server, `get_edit_context` returns body, file skeleton and ±5-line caller windows under a 4,000-token budget, `check_rename_or_delete` also checks `getattr` and other string references, `PreToolUse` hook blocks unbounded reads of files over 300 lines and returns the symbol table, `get_token_savings` measures returned vs raw tokens)
- **Added:** 2026-11-02 · **Status:** idea

### #31 MicroStation Assistant history — value 4, effort M

- **Summary:** Link its conversations and generated scripts to projects; storage location still needs checking.
- **What:** MicroStation 2026.2's Python Assistant (Technology Preview) keeps Conversations, History and Memories, has Ask and Agent modes, and saves resumable workflows with plans and generated code across sessions. Read these like the Copilot chats: link each conversation and generated script to the project folder it was saved into, show them on the Timeline and in briefs, and list the Assistant's Memories in the agent rules inventory (#49), so automation Stu builds inside MicroStation doesn't stay invisible to AI Brain. Bentley doesn't document where these are stored, so step one is locating them on Stu's PC (read-only).
- **Sources:** https://docs.bentley.com/LiveContent/web/MicroStation-v2026.0.2/Help/en/topics/Concept/new_and_changed_in_microstation_2026.html (2026.2: Conversations, History and Memories navigation, Ask and Agent modes, resumable workflows that preserve progress across MicroStation sessions; Custom Instructions renamed Memories)
- **Added:** 2026-11-05 · **Status:** idea

### #32 Live MicroStation snapshot — value 4, effort M

- **Summary:** Provide an opt-in, read-only view of the active model and levels.
- **Sources:** none recorded (from the repo backlog).
- **Added:** 2026-11-12 (repo backlog, `c6c96cf`) · **Status:** idea

### #33 Function history — value 3, effort S

- **Summary:** Show the commits behind a function or line.
- **What:** For any function or line range in a scanned project, run local `git log -L` (and PR titles when the remote is GitHub) and show every commit that touched those lines: date, author, message, the relevant diff hunk, and who last wrote the current lines. Cards, the Ask bar and the MCP server can then answer *"why does this look like this?"* with cited history, not just *"what does it do?"*. The Timeline already lists commit subjects; this is per-symbol line history. Complements idea #56 (what breaks if you change it) and #64 (whether the docs still match).
- **Sources:** https://github.com/Nomannazir/codebase-brain-mcp (new 6 Nov 2026 05:23 AEDT: `explain_history` / `search_history` via `git log -L`, current authorship, linked PR titles and descriptions)
- **Added:** 2026-11-07 · **Status:** idea

### #34 Obsidian export — value 3, effort S

- **Summary:** Export project notes and maps to an Obsidian vault.
- **What:** Export the scan as an Obsidian-ready folder: one markdown note per project/file with `[[wikilinks]]` for imports and connections, plus a `.canvas` (JSON Canvas) of the Blueprint/Skills map. Stu can then browse and annotate it in Obsidian alongside his notes.
- **Sources:** https://jsoncanvas.org/ · https://github.com/Graphify-Labs/graphify
- **Added:** 2026-10-28 · **Status:** idea
- **Note (2026-11-13, From Second Brain):** Also keep the Obsidian export in a private git repo so other agents (Copilot, Claude Code, Grok Bot) can read it as shared memory instead of rebuilding context. Source: https://x.com/0xCodila/status/2118763717370274251 (setup prompt is in the video only)

### #35 Task context pack — value 3, effort S

- **Summary:** Pick relevant files for a task within a token budget.
- **What:** Type a task ("add a level report to my MicroStation tool"), set a token budget, and AI Brain picks the smallest high-value set of files (personalised PageRank seeded on matching files). It compresses them to signatures with tree-sitter, shows a token-count tree, and copies one pack. The existing *Copy for new chat* is fixed to brief + key files; this pack is chosen for the task.
- **Sources:** https://github.com/yamadashy/repomix · https://github.com/lopax76/second-brain
- **Added:** 2026-10-28 · **Status:** idea

### #36 Since last visit — value 3, effort S

- **Summary:** Highlight what changed since a project was last opened.
- **What:** AI Brain records when Stu last opened each project and lights up on the Blueprint and cards only what changed since then: new files, edited files, uncommitted work, and what the last `git pull` brought in (from the reflog, not commit dates). The Timeline shows fixed windows today; this shows the gap since he last looked.
- **Note (2026-10-30):** Lay the Blueprint out by containment (folder ⊃ file ⊃ function) rather than a force layout, so unchanged nodes stay on the same spot between scans and only changes stand out. Keep a small graph snapshot per scan so Stu can also compare any two (e.g. last Friday vs now) side by side, with a file moved to another folder shown as a *move*, not a delete plus an add. Source: https://github.com/voidixyn/glassbrain
- **Note (2026-11-02):** Roll the change counts up the folder tree so a collapsed parent folder still shows how many changed files sit below it, let Stu snooze a project's or file's change mark for 1, 3 or 7 days, and add a *Next changed file* step-through ("3 of 12"). Files that scripts or agents created while AI Brain was closed are picked up on the next start, with a short grace period so files Stu is still editing aren't flagged. Source: https://github.com/kashicards/unread-plus (Obsidian plugin added to the community directory 1 Nov 2026 23:23 AEDT: per-status folder badges at every depth, snooze, offline detection with a grace period, open next/previous unread)
- **Note (2026-11-13):** For git projects, add a *history scrubber*: each Blueprint link records the commit that added it and the one that removed it, so Stu can step through a project commit by commit, with new links flashing and removed ones ghosted, and see when a script started depending on a config or helper. Source: https://github.com/ax3cubed/cartograph (new 10 Nov 2026 23:18 AEDT: typed links store the commits that added and removed them; time scrubber steps through history commit by commit, added links flash and removed links ghost)
- **Sources:** https://github.com/icydotdev/codecity · https://github.com/haydenschmitty/floorplan
- **Added:** 2026-10-29 · **Status:** idea

### #37 Files that change together — value 3, effort S

- **Summary:** Find hidden connections in Git history.
- **What:** Mine `git log` for files that are usually committed together and draw them as a dashed "changes with" edge in Blueprint and the file detail panel. It costs no LLM tokens and reveals hidden coupling (a script and the config or template it secretly depends on) that import parsing misses.
- **Sources:** https://github.com/YURIBEDRAN/rubi
- **Added:** 2026-10-29 · **Status:** idea

### #38 MCP and AI-tool inventory — value 3, effort S

- **Summary:** List configured tools and flag those that can write.
- **What:** Add a Connections panel that lists every MCP server configured for VS Code (`.vscode/mcp.json` per project plus user settings) and other AI tool configs. It shows each server's tools and whether they only read or can write. AEC servers such as Revit-model MCPs, which can change a live model, get flagged, and the panel notes which projects use which servers.
- **Note (2026-10-30):** Two AEC servers to recognise and flag as write-capable: Bentley's **MicroStation MCP Server** (early access; full read/write via the Python API, and key-ins such as *File Fence* can still write files outside the sandbox) and **DynamoMCP**, built into Dynamo 4.2, which can add nodes, run and save graphs. Sources: https://www.bentley.com/en/infrastructure-ai/mcp-servers/ · https://dynamobim.org/dynamo-core-4-2-release/
- **Note (2026-10-30):** Also recognise the **pyRevit 7 agent runtime** (opt-in MCP server over stdio, Oct 2026). Its `run_modify` tool changes the live Revit model, with each change approved inside Revit by default, so it should be listed as write-capable; `run_query` and the other tools only read. Sources: https://github.com/pyrevitlabs/pyRevit/releases/tag/v7.0.0.26278%2B2233 · https://github.com/fulviofb/revit-claude-mcp
- **Note (2026-11-01):** Also recognise **tbc-revit-mcp** (fork of bimwright `rvt-mcp`, Revit 2022–2027, 252 tools) and **tbc-acad-mcp** (AutoCAD / Civil 3D `dwg_*` tools). Both are write-capable: `send_code` runs C# inside the live Revit session (the fork adds a `dry_run` mode, worth showing as a safer option) and `revit_create_family` builds families. Their Windows installer adds entries to every AI client's config it finds, so the inventory should show which clients got them. Sources: https://github.com/desarrolloteambimcivil/tbc_mcp_setup (1 Nov 2026 AEDT) · https://github.com/desarrolloteambimcivil/tbc_mcp_revit
- **Note (2026-11-02):** Also recognise Autodesk's own **Revit Public MCP Server** (Tech Preview, Revit 2027): since the 29 Sep 2026 update for Revit 2027.2+ it ships as three installers, *Read*, *Write* (includes Read; swaps family types, duplicates views, overrides graphics) and *Experimental*, so the inventory should say which one is installed and list Write and Experimental as write-capable. Source: https://archicoder.com/posts/dynamo-vs-pyrevit-2026/ ("Where MCP and Autodesk Assistant sit")
- **Note (2026-11-07):** Also recognise **Autodesk MCP Bridge** (`s81/Autodesk--mcp`): live Revit *and* AutoCAD/Civil 3D sessions on the same PC (2022–2027, including Revit/`net10` and AutoCAD 2027), with read tools plus write-capable ones (`revit_set_parameters`, `revit_create_walls`, `revit_execute_csharp`, `autocad_modify_entities`, `autocad_execute_csharp`…). List Write tools as write-capable and show which host instances are running. Source: https://github.com/s81/Autodesk--mcp (updated 7 Nov 2026 AEDT)
- **Note (2026-11-10):** When listing a Repomix MCP entry, flag whether it runs with `--sandbox`. Repomix 1.19.0 (8 Nov 2026) documents that without `--sandbox` the `pack_codebase` tool trusts the `repomix.config.*` in whatever folder it packs (a config file is code), so pointing it at an untrusted cloned repo is a risk; it also now always runs its secret scan for MCP packs. Source: https://github.com/yamadashy/repomix/releases/tag/v1.19.0
- **Sources:** https://github.com/HorizunGroup/horizun-revit-mcp · https://github.com/DeusData/codebase-memory-mcp
- **Added:** 2026-10-29 · **Status:** idea

### #39 Index freshness — value 3, effort S

- **Summary:** Warn when an answer may use stale information.
- **What:** Before each Ask-bar answer, brief or (later) MCP reply, re-scan only the files changed since the last index pass and stamp the answer with an "index age" badge. If a file couldn't be re-read, the answer says "may be stale" so Stu doesn't trust an outdated picture. The file watcher already exists; this ties it to each answer.
- **Note (2026-11-05):** Judge freshness by file content, not just mtime: a file re-saved, synced or checked out with identical content shouldn't mark an answer "may be stale" or trigger a re-scan. When ranking evidence for an answer, put source files ahead of tests and docs (a soft weight, not an exclusion). Source: https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.102 (0.9.102, 4 Nov 2026 09:46 AEDT: a file unchanged in content is not re-flagged stale by mtime; source nodes rank above tests and docs; `update` re-extracts only files whose content changed)
- **Sources:** https://github.com/Graphify-Labs/graphify (hook-guard fresh/stale policy) · https://github.com/Graphicle-AI/graphicle ("files that change are synced before each answer")
- **Added:** 2026-10-29 · **Status:** idea

### #40 Replaced decisions — value 3, effort S

- **Summary:** Keep old decisions while showing which one is current.
- **What:** Extends idea #20. Each decision can carry an effective date (`@effective:2026-06-10`), so when a later decision replaces it ("switched from Revit 2024 to 2025 API"), the Ask bar and briefs show the current one and keep the old one as history. Queries can also ask "what was true on <date>?".
- **Sources:** https://github.com/basicmachines-co/basic-memory/pull/1426 (v0.24, temporal qualifiers / time-aware search)
- **Added:** 2026-10-29 · **Status:** idea

### #41 Project board — value 3, effort S

- **Summary:** Drag projects between statuses such as active, parked and done.
- **What:** A board view of the project cards in columns (Active / Parked / Stale / Abandoned / Done). Stu can drag a card to override the automatic status and add a one-line reason, which is saved in `.brain/`, so a project he paused on purpose stops showing up as "stale".
- **Sources:** https://obsidian.md/changelog/2026-10-05-desktop-v1.14.4/ (Bases kanban view and group options)
- **Added:** 2026-10-29 · **Status:** idea

### #42 Saved answers — value 3, effort S

- **Summary:** Save useful answers and flag them when their sources change.
- **What:** A *Save answer* button on Ask-bar replies stores the answer as a markdown page under `.brain/answers/`, linked to the files it was built from. When any of those files later changes, the saved answer is flagged "needs re-check" in the Digest, so useful explanations are kept but not trusted blindly. Idea #39 covers live answers; this covers saved ones.
- **Note (2026-10-31, From Second Brain):** Offer to file good Ask-bar answers back automatically (Stu approves the list), so the brain grows from use, and keep the raw scan separate from the saved pages so answers never edit source data. Source: https://x.com/Argona0x/status/2111837226006921640 (reader never edits sources; answers filed back as wiki pages)
- **Sources:** https://github.com/siris9476/mnemoloci
- **Added:** 2026-10-29 · **Status:** idea

### #43 Mermaid export — value 3, effort S

- **Summary:** Copy editable architecture diagrams into documentation.
- **What:** A *Copy as Mermaid* button on the Blueprint (folder or corpus) and on MicroStation key-in maps that emits a `flowchart` block Stu can paste into a README, Teams/Confluence page or Copilot chat. It renders on GitHub and in VS Code, unlike a screenshot, and stays editable. Idea #34 targets Obsidian; this targets plain docs.
- **Note (2026-10-31):** Obsidian 1.15 (22 Oct 2026) now draws Mermaid 12.1 diagrams in a note's theme colours, zoomable, with no prompt, so the same block also renders cleanly if Stu pastes it into Obsidian or uses idea #34. Source: https://obsidian.md/changelog/
- **Sources:** https://github.com/Graphify-Labs/graphify (`graphify export callflow-html`, Mermaid architecture/call-flow export)
- **Added:** 2026-10-30 · **Status:** idea

### #44 Risk hotspots — value 3, effort S

- **Summary:** Highlight large, frequently changed or unfinished files.
- **What:** Rank files that are large, edited often (from mtimes and `git log`) and full of TODO/FIXME markers, and show them as a treemap or highlight on the System ring. These are the scripts most likely to break when Copilot touches them next. Idea #22 ranks by connectivity and #38 shows coupling; this ranks by risk.
- **Note (2026-11-01):** Sort files into four plain groups instead of one ranking: *Refactor first* (edited often, big, no tests), *Landmines* (big but untouched for months, so nobody dares edit them), *Workhorses* (edited often but small) and *Backwaters*. Give each a 0–100 risk score with the evidence shown (commits, share of `fix` commit subjects, size, how many files import it, tests present), and list circular import chains separately. Source: https://github.com/D0NO1/repo-archaeologist (new 1 Nov 2026 16:48 AEDT: Feathers-style risk quadrant from git history, bugfix ratio, circular dependency chains, one offline HTML report)
- **Sources:** https://github.com/MaibornWolff/codecharta (metric view: area/height/colour by size, commits, complexity; hotspots)
- **Added:** 2026-10-30 · **Status:** idea

### #45 Scan coverage — value 3, effort S

- **Summary:** Show which files the brain could not read and why.
- **What:** A per-project list of files that were indexed, partly parsed, skipped (binary `.dgn`, `.rvt`, `.dwg`, `.pdf`, over the size cap) or excluded, with the reason. The Ask bar then says "12 files in this folder aren't indexed" instead of a flat "nothing found", so Stu knows when an empty answer is a blind spot rather than a real no. Idea #39 covers stale files; this covers unseen ones.
- **Sources:** https://github.com/DeusData/codebase-memory-mcp (CBM Lens *Coverage* workspace: indexed / partially parsed / skipped / excluded paths; `check_index_coverage` before negative claims)
- **Added:** 2026-10-30 · **Status:** idea

### #46 Launch chains — value 3, effort S

- **Summary:** Map launchers, scheduled tasks and scripts that start other scripts.
- **What:** Draw dashed "launches" edges on the Blueprint from `.bat`/`.cmd` launchers, `subprocess`/`os.system`/`Popen` calls, `.vscode/tasks.json` and `launch.json`, and exported Task Scheduler jobs to the scripts they start. Stu can then follow `start.bat` → `main.py` → the worker it spawns, which import parsing misses because those links are strings, not imports.
- **Sources:** https://github.com/DeusData/codebase-memory-mcp/releases/tag/v0.12.0 (v0.12, 15 Oct 2026: process launches become `SPAWNS` edges; scripts, Makefiles and CI jobs link to the programs they run)
- **Added:** 2026-10-30 · **Status:** idea

### #47 Knowledge gaps — value 3, effort S

- **Summary:** Find important files that nobody has explained.
- **What:** List the files and functions many others depend on (helpers, shared configs, key-in handlers) that have no README section, docstring, decision note, handoff mention or Copilot chat explaining them, ranked by how many things rely on them. Each entry has a *Copy prompt* that asks Copilot to write a short "how this is meant to be used" note, so the scripts Stu would be most lost in get explained first. Idea #22 ranks hubs and #46 shows unseen files; this shows hubs nobody has explained.
- **Sources:** https://github.com/jha0313/second-brain-eval-kit (codebase-brain: `why` returns cited docs and commits for a file; a heavily used header with only one doc is reported as a knowledge gap)
- **Added:** 2026-10-31 · **Status:** idea

### #48 Rebuild pack — value 3, effort S

- **Summary:** Produce recovery instructions for restoring projects on a new PC.
- **What:** A *Save rebuild pack* button that writes one readable markdown file (saved only where Stu picks, e.g. a OneDrive folder) describing how to get every project running again on a new PC: per project the entry point, run command, Python / MicroStation / Revit version, required packages, `.env` key *names* only (never values), MCP servers and VS Code extensions used, and the order to restore them in. Places that need a fresh sign-in or licence are flagged, and the pack is never sent to a cloud AI. Unlike the per-project handoff, it covers the whole setup.
- **Sources:** https://x.com/Michael_Fenech_/status/2112204877971821055 (backup and recovery SOP: map the setup, readable recovery pack stored outside the account, connections table excluding passwords and keys, ordered rebuild steps, test one recovery) · **Tag:** From Second Brain
- **Added:** 2026-10-31 · **Status:** idea

### #49 Agent rules inventory — value 3, effort S

- **Summary:** List and compare agent instructions, memories and skills.
- **What:** Find the instruction and memory files AI tools already keep, both in project folders (`.github/copilot-instructions.md`, `*.instructions.md`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*.mdc`, `*.agent.md`, prompt files) and in the user folder (`~/.copilot/`, `~/.claude/`, `~/.cursor/rules/`), without changing them. Show them per project and as one list, where the same rule kept by several tools or projects appears once with every source shown, and flag rules that contradict each other or name files and commands that no longer exist. Idea #7 writes new instructions and idea #64 checks docs against code; this shows what every tool has already been told.
- **Note (2026-11-01):** Keep a change feed of those files: on each scan, record what changed in any instruction, rule, memory or skill file, with a diff and whether Stu or an agent made the change (from the Copilot edit stream, idea #15, or git), shown on the Timeline. Stu can then spot an agent quietly rewriting its own rules or filling memory with one-off details. Source: https://github.com/hakastein/skillwatch (31 Oct 2026: local FastAPI + React window with a live feed of every skill and memory edit an agent makes, with a diff, where and who changed it; read-only towards the agent)
- **Note (2026-11-01):** Give each always-loaded file (`copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`) a "resident tax": its token size times how many Copilot sessions per week started in that folder (from the chat history), projected over 30 days, so Stu sees which bloated file costs the most. Also run plain trust checks on every rule and memory file: text phrased as an instruction aimed at the agent that Stu didn't write (possible prompt injection), `curl … | sh` style commands, secrets and email addresses, entries with no source, and near-duplicates. Sources: https://github.com/Eileenes/RecallROI (new 1 Nov 2026 20:55 AEDT: per-memory token P&L, "resident tax" of files injected every session projected to 30/90 days, zombie memories, near-duplicate clusters, secret scan) · https://github.com/gravion-ux/memorytrust (new 1 Nov 2026 20:42 AEDT: 0–100 trust score with rules for missing source, stale or expired facts, conflicts, secrets, personal data and instruction-shaped or pipe-to-shell text)
- **Note (2026-11-02):** Besides the list, draw the setup as a small graph: instruction files, prompt files, skills, agents, hooks and MCP servers as nodes, with *uses* edges (a hook runs a script, a project uses an MCP server), *mentions* edges (a file names a skill or server) and dashed *unwritten link* nodes for references to files that don't exist. Read only each MCP server's name, transport and host, never `env` values or arguments. Source: https://github.com/EyeDipInBytes/claude-constellation (new 2 Nov 2026 08:23 AEDT: star map of `~/.claude` memory, skills, agents, commands, hooks, MCP servers and projects; links from wikilinks, mentions, uses and structure; secret filter, `--redact`)
- **Note (2026-11-02):** Include agent skills (`SKILL.md` in project and `~/.copilot/skills/` folders): each skill's name and description sit in context at the start of every session, used or not, so show the listing's token cost per skill, pairs of skills whose descriptions overlap, and skills that never ran in any Copilot session in the chat history, with a reversible *Park* (move aside, restore later) rather than delete. Source: https://github.com/codegobrrrr9/skilldiet (new 2 Nov 2026 11:42 AEDT: per-skill listing tokens, overlap pairs, never-fired skills from session logs, reversible prune with a manifest, no model calls)
- **Sources:** https://github.com/Ewen2015/dachshund (30 Oct 2026: read-only import of the memory and rule files that Claude Code, Codex, Cursor, Copilot and others keep, one Markdown library, identical memories merged as "echoes" with every source shown) · https://github.com/Ewen2015/dachshund/blob/main/docs/AGENTS.md (exact paths per agent, e.g. Copilot memory and instruction Markdown under `~/.copilot`, Cursor rules under `~/.cursor/rules/`)
- **Added:** 2026-10-31 · **Status:** idea

### #50 Terminal history — value 3, effort S

- **Summary:** Link commands run by the user to projects and their timelines.
- **What:** Read the PowerShell history files (`%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\*_history.txt`, including the VS Code host's own file) and match each command to the project folder it ran in or names (`python levels_report.py`, `pip install ifcopenshell`, `git commit`). The commands show on the Timeline and in briefs, and a run command Stu has actually typed counts as evidence for the card's run command and the *Runs* badge (#61). History is passed through the existing secret redaction first, since it can hold passwords. Idea #9 covers Copilot CLI sessions and #67 error logs; this covers what Stu ran himself.
- **Sources:** https://github.com/nitishagar/agent-memory (31 Oct 2026 AEDT: local-first recorder of shell commands, git context and agent transcripts, redacted at capture, queryable over MCP as "what did I do and why") · https://learn.microsoft.com/en-us/powershell/module/psreadline/about/about_psreadline (history file per host, e.g. `Visual Studio Code Host_history.txt`, stored in `$Env:APPDATA\Microsoft\Windows\PowerShell\PSReadLine`; can contain sensitive data)
- **Added:** 2026-10-31 · **Status:** idea

### #51 Running-now panel — value 3, effort S

- **Summary:** Show project processes, servers and possible runaways.
- **What:** List the processes whose command line or working folder sits inside a scanned project (e.g. `python.exe levels_report.py`, a uvicorn or `node` dev server, a job Copilot started in a terminal) with project, uptime, CPU, RAM and listening port, read locally with `psutil`. Flag runaways: a process that has kept a core busy for over an hour, or a server still holding a port long after its project was last touched, with *Copy PID* and *Stop* buttons (Stop asks first). Cards get a "running now" dot and the Digest lists forgotten servers. Idea #61 runs a check on demand and #47 draws what starts what; this shows what is actually running right now.
- **Sources:** https://github.com/evoleinik/agent-exporter (new 1 Nov 2026 15:37 AEDT: sorts agent sessions into working / needs you / your turn / stale, counts processes an agent started that kept a core busy past 1 h and the memory stale sessions still hold; Python standard library only)
- **Added:** 2026-11-01 · **Status:** idea

### #52 Secrets in chat logs — value 3, effort S

- **Summary:** Warn about exposed credentials without displaying their values.
- **What:** Scan the AI chat history AI Brain already reads (Copilot `workspaceStorage` chats and transcripts, later Copilot CLI sessions from #9) for keys, tokens, passwords and credentialed URLs that ended up in a chat, e.g. after the agent ran `type .env` or printed environment variables. Show only the type, a short fingerprint, how many sessions hold it and what put it there (file read, terminal output, pasted by Stu), never the value, plus a reminder that the key was already sent to the model provider and must be rotated. Suggest the deny rule from #10 to stop it happening again. Idea #8 finds secrets in project code; this finds the copies sitting in chat logs.
- **Sources:** https://github.com/codegobrrrr9/agent-residue (new 2 Nov 2026 11:23 AEDT: finds secrets in Claude Code and Codex session logs and memory, reports type, keyed fingerprint, counts and which tool call put each there, never prints a value, suggests deny rules, "scrubbing is not rotation")
- **Added:** 2026-11-02 · **Status:** idea

### #53 Speckle migration check — value 3, effort S

- **Summary:** Flag scripts using outdated Speckle interfaces.
- **What:** When a project's scripts use Speckle (`specklepy` imports, `Speckle.Sdk`/`Speckle.Objects` NuGet references), flag the calls that stop working on models in Speckle's 2026.9 data format, which every ACC sync and file upload has produced since compatibility mode ended on 1 Nov 2026: `operations.receive` / `Receive2`, walks of the object graph or root object, `object.children` queries, `displayValue` geometry and `referencePointTransform`. Each finding shows `file:line`, the replacement (`operations.receive3` with `specklepy[bundle]`, `Receive3`, the EAV query endpoint, `modelPlacement`) and a copy-ready Copilot fix prompt.
- **Sources:** https://docs.speckle.systems/whats-new/developers (2026.9: parquet bundles with no root object, `Receive2` obsolete, objects endpoints return 404, `object.children` replaced by the EAV query endpoint, `modelPlacement`, older SDKs get a 404; compatibility mode ends 1 Nov 2026)
- **Added:** 2026-11-02 · **Status:** idea

### #54 Related files — value 3, effort M

- **Summary:** Find similar scripts and notes across projects using local search.
- **What:** Select any file, Copilot chat or digest item to see a live list of semantically similar files across all projects. It would use a small local embedding model or Ollama, cached in `.brain/cache.sqlite`, and nothing is uploaded. This finds near-duplicate scripts and earlier attempts that keyword retrieval misses.
- **Note (2026-10-30):** Run the embedding search alongside the Ask bar's existing keyword search and a fuzzy match on function and file names, then merge the three lists by reciprocal rank. Exact names such as `get_levels` and loose questions such as "where do I export sheets" then both find the right file. Source: https://github.com/mikekonan/cograph
- **Sources:** https://github.com/brianpetro/obsidian-smart-connections (v4.7 release notes) · https://github.com/reorproject/reor
- **Added:** 2026-10-28 · **Status:** idea

### #55 Explain connections — value 3, effort M

- **Summary:** Show paths between files and how certain each link is.
- **What:** In the Blueprint Ask bar, "path A → B" highlights the shortest chain of imports/calls between two files or concepts, and "explain X" summarises one node and its neighbours. Each edge is tagged EXTRACTED (read from source) or INFERRED (guessed), so Stu can see what is certain.
- **Note (2026-10-31):** Give each path one overall confidence equal to its weakest hop, name that hop in a summary line, and show each inferred edge's score (e.g. `INFERRED 0.75`). When several equally short routes exist, show the least certain one and say it was chosen from N, so a path never looks surer than its weakest link. Source: https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.99 (0.9.98–0.9.99, 31 Oct 2026 AEDT)
- **Sources:** https://github.com/Graphify-Labs/graphify
- **Added:** 2026-10-28 · **Status:** idea

### #56 Change impact — value 3, effort M

- **Summary:** Highlight what an uncommitted change may affect.
- **What:** For a folder that is a git repo, take the uncommitted changes and highlight on the Blueprint every file or function they touch or depend on, with a plain-English "this change affects…" line before Stu commits or asks Copilot to continue.
- **Sources:** https://github.com/Egonex-AI/Understand-Anything
- **Added:** 2026-10-28 · **Status:** idea

### #57 Session size X-ray — value 3, effort M

- **Summary:** Find oversized AI sessions and suggest a fresh handoff.
- **What:** Using the Copilot chat history AI Brain already reads, chart how large each session's context grew, flag sessions that ran very long or re-read the same files repeatedly, and suggest saving a handoff and starting fresh at that point. It helps Stu keep Copilot sessions short and focused.
- **Note (2026-11-02):** Flag the costly case directly: returning to a large session after a break long enough for the prompt cache to expire. Show the estimated cost of resuming as is versus starting fresh with a handoff note (*Save BRAIN_HANDOFF.md*), since a handoff written before the break was cheaper in every one of 414 measured returns (about 69% saved on Claude Code, 55% on Codex), while compacting first only paid off after several requests. Source: https://github.com/ignatov/tokprof (new 2 Nov 2026 11:02 AEDT: token, cost and prompt-cache profiler for agent session logs, with the resume vs compact vs handoff benchmark)
- **Sources:** https://github.com/YURIBEDRAN/rubi
- **Added:** 2026-10-29 · **Status:** idea

### #58 Cross-agent work log — value 3, effort M

- **Summary:** Give agents a shared project log, with lessons subject to user approval.
- **What:** A shared plain-text logbook (`.brain/log/`) that Copilot, Claude Code, Cursor or Grok Bot sessions can append one-line entries to ("18:40 | copilot | levels-report | added CSV export"). The entries appear on the Timeline and in briefs. Agents can propose "lessons", which become instructions only after Stu clicks *Keep*.
- **Sources:** https://github.com/eugeniughelbur/obsidian-second-brain (Crew)
- **Added:** 2026-10-29 · **Status:** idea

### #59 Reusable agent skills — value 3, effort M

- **Summary:** Draft skills from tasks repeatedly performed.
- **What:** Spot work Stu repeats across projects and Copilot chats (e.g. "add a key-in to a MicroStation Python tool", "export Revit schedules to Excel") and draft a reusable `SKILL.md` from the steps, scripts and gotchas already in the index. After Stu reviews it, the skill can be saved to the project's skills folder or `~/.copilot/skills/`, so Copilot can reuse it in any project. Idea #7 writes per-project instructions; this captures cross-project how-tos.
- **Sources:** https://screenpipe.com/blog/screenpipe-v2-32-workflows · https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference
- **Added:** 2026-10-29 · **Status:** idea

### #60 Brain map inside Copilot chat — value 3, effort M

- **Summary:** Let users and Copilot inspect the same project map.
- **What:** Package the Blueprint or a project card as a VS Code canvas extension (Preview, Copilot harness sessions). Stu and the agent then look at the same live project map beside the chat: the agent can highlight the files it plans to touch and Stu can click nodes to add them as context. It builds on the existing VS Code extension and pairs with idea #2.
- **Sources:** https://code.visualstudio.com/updates/v1_144
- **Added:** 2026-10-29 · **Status:** idea

### #61 Verified runs badge — value 3, effort M

- **Summary:** Opt in to a safe check instead of assuming a detected command works.
- **What:** An opt-in *Check it runs* button on a card that tries the detected run command in a throwaway venv or subprocess with a timeout (or only `py_compile` / import checks for MicroStation and Revit scripts that need a host app). The card then says *Runs (verified 2026-10-30)* or shows the first error and a fix prompt. Today the **Runs** badge only means a start command was found.
- **Sources:** https://www.greptile.com/docs/changelog (TREX, GA 16 Oct 2026: starts the app in a sandbox and tests the affected flows)
- **Added:** 2026-10-30 · **Status:** idea

### #62 Shareable project page — value 3, effort M

- **Summary:** Export an offline project summary for colleagues.
- **What:** An *Export page* button on a project card that writes one self-contained offline HTML file (no server, no network loads): the card summary, Blueprint, MicroStation key-in map, run steps and a list of open questions/unknowns, each linked to file and line. Stu can attach it to an email or Teams post, or hand a tool to a colleague who doesn't run AI Brain. *Save BRAIN_HANDOFF.md* targets an AI chat; this targets people.
- **Sources:** https://github.com/sardi-dev/wirehouse (single offline HTML map with file:line evidence, `--against` change view) · https://github.com/thusinh1969/vibe_rescue (team `handoff.html` with functional blocks, function leads and unknowns)
- **Added:** 2026-10-30 · **Status:** idea

### #63 Guided walkthrough — value 3, effort M

- **Summary:** Step through a project's flow and key files.
- **What:** A *Walk me through it* mode that steps through one flow at a time, e.g. MicroStation key-in → handler → helper → output file, or `main.py` → the functions it calls. Each step gets a short explanation and the `file:line` it rests on, with a *Continue* button and a "where would I change X?" check at the end. It helps Stu re-learn a forgotten script before editing it. Idea #55 answers one path query; this is an ordered tour.
- **Sources:** https://github.com/Cyvid7-Darus10/repo-explainer (sequence-diagram tour with Continue button, file:line per hop, quiz)
- **Added:** 2026-10-30 · **Status:** idea

### #64 Documentation conflicts — value 3, effort M

- **Summary:** Find where instructions or READMEs disagree with code.
- **What:** Compare what a project's README, `BRAIN_HANDOFF.md`, Copilot instructions and notes claim (run command, entry point, Python/MicroStation/Revit version, file and function names) with what the scan finds, and list each disagreement as a conflict card, e.g. "README says `python run.py`; no `run.py` exists". Stu picks the true side once; the choice is saved in `.brain/`, the stale doc stays flagged until fixed, and the choice is dropped if either side changes. A doc mention links to code only when it names exactly one file or function, so nothing is guessed.
- **Note (2026-10-31, From Second Brain):** Run the review as an optional nightly (weekday evening) pass over the day's changes that only *suggests* edits to README, handoff and Copilot instruction files as a diff; nothing is written until Stu approves. Source: https://x.com/maestrooth/status/2114052058454131049 (nightly second-brain audit: suggests edits, nothing changes without approval) · https://x.com/Argona0x/status/2111837226006921640 (nightly checker for contradictions, stale claims and orphan pages)
- **Note (2026-11-07):** Besides missing names, also catch docs that pass parameters a function no longer takes, imports that would fail, and sections last edited long before the code they describe changed; each finding cites the doc section and, for renames, suggests the likely new name. Source: https://github.com/Nomannazir/codebase-brain-mcp (new 6 Nov 2026 05:23 AEDT: `find_doc_drift` for Markdown/reST — missing symbols, bad example params, failing imports, staleness by history)
- **Sources:** https://github.com/topoteretes/cognee/releases/tag/v1.6.6 (29 Oct 2026: conflict review on by default, durable resolutions, choices retired when the data changes) · https://github.com/DeusData/codebase-memory-mcp/releases/tag/v0.12.0 (docs, ADRs and PDFs linked to code only when a reference names exactly one definition)
- **Added:** 2026-10-30 · **Status:** idea

### #65 ChatGPT and Claude imports — value 3, effort M

- **Summary:** Bring exported conversations into project history.
- **What:** Import the `conversations.json` export zips from ChatGPT or Claude (other chat apps later if their exports are similar), so AI chats held outside VS Code join the Copilot history: linked to the project folders and files they mention, shown on the Timeline and searchable from the Ask bar and briefs. Each import writes an index note listing the conversations it added, so Stu can check or undo it. Idea #9 covers Copilot CLI; this covers web chat apps.
- **Sources:** https://github.com/basicmachines-co/basic-memory/releases/tag/v1.0.0 (1.0, 30 Oct 2026 AEDT) · https://github.com/basicmachines-co/basic-memory/pull/1878 (ChatGPT and Claude importers return the paths of each conversation note written, for an import index note)
- **Added:** 2026-10-30 · **Status:** idea

### #66 Error history — value 3, effort M

- **Summary:** Link tracebacks to files and show previously successful fixes.
- **What:** Find `*.log` files and Python tracebacks in project folders (and in the Copilot chats AI Brain already reads), match each error to the scanned `file:line` and function with plain pattern rules before any LLM is called, and show a "last failure" line on the card and Timeline, e.g. "`KeyError: 'Level'` in `report.py:88`, 3 times this week". Repeated errors are grouped into one entry and a fix prompt can be copied. Idea #61 runs a script to see if it works; this reads the failures Stu has already hit.
- **Note (2026-10-31):** When an error stops appearing (the script later runs cleanly, or a commit touches the failing file), store the error together with what changed in between (the commit, or the diff of the file). The next time the same error shows up in any project, the card shows that earlier fix next to it instead of only a fresh fix prompt. Source: https://github.com/sagarkonkanagaon-netizenk/deja (records an error and exactly what changed between the failing and the passing run, then shows that fix when the error appears again in any repo)
- **Note (2026-11-02):** When a fix prompt or MCP reply carries a long log, squeeze it without losing lines: runs of lines that differ only by numbers become one template plus a table of the values, identical lines become a count, and errors, warnings and odd values stay as plain lines. Decode the result and compare it with the original before using it, and pass the log through unchanged if that check fails or saves little. Source: https://github.com/T-Celor/the-dam (new 2 Nov 2026 06:50 AEDT: lossless `dam-squeeze` for 6,000–29,000-character outputs, every result decoded and checked against the source, about 24% tokens saved with 100% of lines recoverable)
- **Sources:** https://github.com/fatterdev/threski-studio (log analysis: deterministic matching first, AI only on a miss, report with file, code location and likely cause; repeats promoted to rules)
- **Added:** 2026-10-30 · **Status:** idea

### #67 Drill-down maps — value 3, effort M

- **Summary:** Zoom from an overview into project parts, files and functions.
- **What:** Add zoom levels above the file graph: a plain-English overview of the whole corpus, then each project split into a few named parts (e.g. "key-in commands", "report export", "config"), then the files and functions. Open a box to go one level down. The LLM (or folder names in no-key mode) only names and groups files, while every arrow still comes from the scan. A grouping that leaves a file out or puts it in two parts is rejected, and the grouping is saved in `.brain/` so the boxes stay the same between scans. Idea #22 clusters by links and #64 tours one flow; this gives a stable map to zoom through.
- **Sources:** https://github.com/RepoLadder/repoladder (clickable rungs from plain language down to files; Claude only names and groups, the build rejects groupings that skip or double-assign a file; `grouping.json` kept so boxes stay stable; no-AI mode groups by folder) · https://github.com/fatjon-kalemaj/accretion (executive, domain, scenario and code levels with drill-down; the narrative may rename and group but cannot add facts)
- **Added:** 2026-10-31 · **Status:** idea

### #68 IFC 3D preview — value 3, effort M

- **Summary:** Inspect IFC models locally in the browser.
- **What:** An *Open in 3D* button on IFC files found by the scan that shows the model in a panel of the React UI using web-ifc and three.js, so the file never leaves the PC. Stu can switch to plan or section views, browse the storey and IFC-class tree and click an element to see its property sets. Elements that fail an IDS check (#25) or changed between versions (#29) can be coloured in the same view. Idea #23 lists what is in the model as text; this shows it.
- **Sources:** https://github.com/malvarez2890-lang/visor-ifc (1 Nov 2026 AEDT: in-browser IFC viewer on three.js and web-ifc, file processed on the device and never uploaded; plan with 1 m cut, X/Y/Z sections, explode by level, IFC-class and spatial tree, property panel, measurements)
- **Added:** 2026-11-01 · **Status:** idea

### #69 DWG/DXF inspector — value 3, effort M

- **Summary:** Show drawing metadata, layers and title-block information.
- **What:** When project folders hold `.dwg` or `.dxf` files (exports from Stu's MicroStation scripts, or consultant drawings), read them locally with a dependency-free reader and add a card section with DWG version, units, layers with item counts, the text found and detected title blocks. The text joins the Ask bar, layer names can be checked against the standards file (#24), and a script that writes the drawing (#26) is linked to it. The reader doesn't open `.dgn`, so DGN files stay listed in the coverage view (#45).
- **Sources:** https://github.com/ezpzfile/ezpzfile-cad (new 5 Nov 2026 14:54 AEDT, MIT: clean-room JavaScript reader for DWG R13–2018+, DXF, IFC and more with no dependencies; returns layers with item counts, text items, version/units metadata and warnings for what was skipped; `findFrames` finds title blocks)
- **Added:** 2026-11-05 · **Status:** idea

### #70 Project conventions drift — value 3, effort M

- **Summary:** Find inconsistent approaches such as mixed logging libraries.
- **Sources:** none recorded (from the repo backlog).
- **Added:** 2026-11-12 (repo backlog, `c6c96cf`) · **Status:** idea

### #71 Run provenance — value 3, effort M

- **Summary:** Record a run's command, versions and inputs so results can be compared.
- **Sources:** none recorded (from the repo backlog).
- **Added:** 2026-11-12 (repo backlog, `c6c96cf`) · **Status:** idea

### #72 Existing diagram preview — value 3, effort M

- **Summary:** View project draw.io and JSON Canvas files inside AI Brain.
- **Sources:** none recorded (from the repo backlog).
- **Added:** 2026-11-12 (repo backlog, `c6c96cf`) · **Status:** idea

### #73 Follow the active window — value 3, effort M

- **Summary:** Open the matching project card and brief when you switch to a VS Code, MicroStation or Revit window.
- **What:** An opt-in *Follow* mode: a small local watcher reads only the title or path of the window in front (VS Code workspace, a MicroStation `.dgn`, a Revit `.rvt`, a script open in Notepad++) and AI Brain, or its VS Code panel, jumps to the matching project card and brief, with the key-ins, WorkSet or scripts tied to that file. Stu can pause it at any time, titles never leave the PC, and folders marked private (#10) are ignored, so switching from MicroStation back to his scripts brings up the right context without searching.
- **Sources:** https://github.com/fieldr-studio/clingnote-obsidian (new 10 Nov 2026 10:15 AEDT: Obsidian plugin plus Windows companion that attaches notes to the files, folders, apps and web pages you work in and opens the right note when you switch back, recognising contexts by window title or path, kept local, with pause/resume)
- **Added:** 2026-11-13 · **Status:** idea

### #74 Project vocabulary — value 2, effort S

- **Summary:** Summarise the terms most associated with each project.
- **What:** Score the words in identifiers, comments and notes by TF-IDF and show a small word cloud per project ("levels", "sheet index", "IFC export"), plus "where does this word live?" across the corpus. Stu gets a quick sense of what a forgotten folder is about without reading it.
- **Sources:** https://github.com/MaibornWolff/codecharta (domain view: TF-IDF vocabulary per folder)
- **Added:** 2026-10-30 · **Status:** idea

### #75 Provider failover — value 2, effort S

- **Summary:** Switch AI providers when one fails, subject to privacy settings.
- **What:** Let Stu order his configured providers (e.g. Anthropic → OpenAI → Grok → Ollama → heuristic). When a call to one fails, times out or hits a rate limit, AI Brain retries the same request on the next one instead of showing an error, pauses the failing provider for a few minutes (circuit breaker) and tests it again before using it again. Each Ask-bar answer, brief or digest shows which provider actually answered. Private folders (idea #10) and the spend cap (idea #12) still decide which providers are allowed.
- **Sources:** https://sourcegraph.com/changelog/automatic-provider-failover (19 Oct 2026: model requests routed around a failing provider to another serving the same model, restored after test requests succeed)
- **Added:** 2026-10-31 · **Status:** idea

### #76 Disk-space review — value 2, effort S

- **Summary:** Identify rebuildable files that could be removed after approval.
- **What:** Total the size of folders in each project that can be rebuilt from scratch (`.venv`/`venv`, `node_modules`, `__pycache__`, `dist`/`build`, C# `bin`/`obj`, `.vs`, `.pytest_cache`) and show it on Stale and Abandoned cards and in one corpus-wide "reclaimable space" table. A dry run lists what would go and how much it frees. Deleting needs an explicit confirm and keeps a receipt in `.brain/`. It never touches source files or git history, and it skips projects with uncommitted changes or recent edits. The card keeps the run command and requirements, so a deleted venv can be rebuilt later (see #60). Pairs with #11 (archive a restart family) and #52 (stop forgotten servers).
- **Note (2026-11-05):** Offer a separate, opt-in list of what Revit and AutoCAD leave on the work PC (journals, worker logs, crash dumps, web and graphics caches, temp and autosave leftovers) with sizes and a risk tier per category, never touching model and drawing files (`*.rvt`, `*.rfa`, `*.dwg`, `*.dxf`, `*.ifc`, `*.pdf`…) or OneDrive / ACC / Desktop Connector folders, and keep Revit journals as records (idea #28 reads them) rather than deleting them. Source: https://github.com/DailenG/DeadLoad (new 5 Nov 2026 02:56 AEDT, pre-release: review-before-delete cleanup of Autodesk leftovers on engineering workstations, Routine / Review / Restricted tiers, protected file types and folders, journals compressed and kept)
- **Sources:** https://github.com/n8watkins/devguard (new 2 Nov 2026 05:34 AEDT: `devguard sweep` dry run lists build output in finished worktrees with sizes, `--apply` deletes it and writes a JSON receipt, worktrees with unmerged branches or uncommitted changes are kept, source and history are never touched)
- **Added:** 2026-11-02 · **Status:** idea

### #77 Obsidian/OneNote ingestion — value 2, effort M

- **Summary:** Search notes alongside project files.
- **What:** Optionally point AI Brain at an Obsidian vault or OneNote export so personal notes about projects join the index, Ask bar and Timeline, linked to the project folders they mention. Ask-bar answers would show which source a hit came from.
- **Sources:** https://github.com/topoteretes/cognee/releases/tag/v1.6.6rc1
- **Added:** 2026-10-29 · **Status:** idea

### #78 Chart answers — value 2, effort M

- **Summary:** Show charts for questions about counts and timelines.
- **What:** Let the Ask bar return a small chart or timeline instead of text when the question is about counts or time, such as "commits per project last month", "which projects did I touch in October" or "Copilot sessions per week". It reuses data AI Brain already has (git log, mtimes, Copilot history) and renders it in the dark/green UI style.
- **Sources:** https://ampcode.com/news/visualize-this (Amp, 29 Oct 2026: charts, timelines and diagrams rendered in the thread)
- **Added:** 2026-10-30 · **Status:** idea

### #79 Measure whether AI Brain helps — value 2, effort M

- **Summary:** Compare answers, time and token use with and without its context.
- **What:** Stu writes 10–20 real questions about his projects with the expected answer (file, function or run command). AI Brain asks each one of Copilot CLI twice, with and without AI Brain context (MCP or hooks), and reports the pass rate, tokens used and time for each, saying plainly when the difference is too small to trust. It shows whether AI Brain is saving Copilot tokens and time or just adding context. Idea #2's usage tally counts calls; this measures the result.
- **Note (2026-11-02):** Test two reply modes as well as with/without: AI Brain returning only *where to look* (files, line ranges, signatures) versus returning the code itself, and keep negative results. zt-memory found its code-context MCP raised the right-file rate for a local 14B model from about 25% to 93–100%, but for a strong cloud agent (Claude Code, 45 real bugs) quality was unchanged, the locations-only mode cut cost about 3%, and returning 4,000 tokens of code raised cost 16–24%. So the check should show whether AI Brain helps Copilot's own model or mainly helps Ollama. Source: https://github.com/Giotor84/zt-memory (new 2 Nov 2026 04:48 AEDT: README benchmark table, negative results kept on purpose)
- **Sources:** https://github.com/jha0313/second-brain-eval-kit (skill-eval: isolated headless runs with and without the skill, hard checks plus judge votes, cost cap, "difference not detected" reported instead of overclaiming)
- **Added:** 2026-10-31 · **Status:** idea

## Renumbering (14 Nov 2026 merge)

- **Repo numbers that changed:** #70→#74, #71→#75, #72→#76, #73→#77, #74→#78, #75→#79, #76→#70, #77→#71, #78→#72. All other repo numbers are unchanged.
- **New in the merge:** #73 Follow the active window (from the scout list).
- **Old scout-list numbers:** #1–#31 unchanged; #32–#68 became #33–#69; #69 became #73; #70–#75 became #74–#79.

## Scout log

The last few research scans. Idea numbers inside these entries are the old scout-list numbers from the time of each scan.

- 2026-11-07 09:00 AEDT (Australia/Sydney): lean pass since 2026-11-05 15:11 (repo commits: none new, last push still 2026-10-30 09:41 AEDT, newest commit `99f3327`; releases: Graphify 0.9.103 read, Cognee 1.6.7 read, screenpipe app 2.7.143 (enterprise/search/auth fixes only), IfcOpenShell Bonsai alphas; Basic Memory, Mem0, Letta, Khoj, Logseq, Reor, Smart Connections, Repomix, GraphRAG, LightRAG, codebase-memory-mcp, Dynamo 4.2.3 (already noted last scout), pyRevit (env --redact quote fixes only): nothing feature-new; Obsidian changelog: nothing new for AI Brain since 1.15.1; Sourcegraph 2 Nov (already noted last scout) and Greptile changelogs: nothing relevant; GitHub search for repos created since 5 Nov incl. AEC terms, e.g. Nomannazir/codebase-brain-mcp, egecagintepe/agent-project-onboarding, carlosdanielmirandadelima-blip/revit-free, s81/Autodesk--mcp, KonkovDV/AeroBIM, iv3rins/dsh-memory, anidealab/brain-kit: the rest covered by existing ideas #7, #15, #20, #53, #55, #63 or README-less; skipped pirate/setup-guide MicroStation/Visio/Revit installer repos). 1 idea added: *Function line history ("why is it built this way")* (new #32). Notes added to #6 (C# `#if` blanking before parse), #10 (refuse DB connection strings on ingest), #20 (incident ledger), #25 (cross-file IDS/model/sheet seams), #27 (revit-free pure-Python reader), #37 (Autodesk MCP Bridge Revit+AutoCAD; was #36), #63 (doc-drift: bad params, failing imports, rename suggestions; was #62). Old #32–73 renumbered to #33–74; cross-references updated.
- 2026-11-10 09:00 AEDT (Australia/Sydney): lean pass since 2026-11-07 09:00 (repo commits: none new, newest commit `99f3327`; releases: Graphify 0.9.104 and 0.9.105 read (extractor, watch and cache fixes only; nothing new for AI Brain), Repomix 1.19.0 read (MCP sandbox/config trust note added to #37), pyRevit 7.0.1.26312 read (installer crash fix only), IfcOpenShell Bonsai alphas; Basic Memory (1.0.0 already seen), Obsidian, Logseq, Khoj, Smart Connections, GraphRAG, LightRAG, Cognee, Mem0, Letta, screenpipe, Dynamo: none new; GitHub search for repos created since 7 Nov for second brain / knowledge graph / agent memory / codebase map: only tiny repos, covered by existing ideas). No new ideas.
- 2026-11-13 09:00 AEDT (Australia/Sydney): lean pass since 2026-11-10 09:00 (repo commits: 1 new, `c6c96cf` *Add ranked feature backlog* (12 Nov 2026 23:10 AEDT), docs only, no new built features; noted in the built list with the four repo-only ideas; releases: Graphify 0.9.106–0.9.108 read (extractor, query and MCP reload fixes; nothing new for AI Brain), Obsidian 1.15.1 public (already seen), IfcOpenShell Bonsai alphas; commits since 10 Nov of Basic Memory (similar-note merge advice, note added to #20), Dynamo (AI-touched node badge, already noted in #3), pyRevit (agent and CLI fixes), codebase-memory-mcp (test-impact CI, SVN watcher core), Logseq, LightRAG, Cognee, screenpipe: nothing else new for AI Brain; Khoj, Reor, Smart Connections, Repomix, GraphRAG, Mem0, Letta: none new; Sourcegraph 9 Nov and Greptile changelogs: nothing new; Obsidian community plugins added since 10 Nov (e.g. ClingNote, Agent Change Review, Copy as Context, Uncommitted, Vault Disk Usage: the rest covered by #15, #18, #34, #72); GitHub search for repos created since 10 Nov for second brain / knowledge graph / codebase map / agent memory and Revit / MicroStation / IFC / Dynamo / pyRevit / BIM MCP, e.g. ax3cubed/cartograph, OYGUS/Helios, victusfate/mindmeld, aphesist/anamnesis, nikolaikrasilnikov/Revit-Bridge, BIM-MODE connectors: covered by existing ideas). 1 idea added: *Follow the active window (context brief)* (new #69). Notes added to #20 (ask before merging similar memories) and #35 (git history scrubber). Old #69–74 renumbered to #70–75.
- 2026-11-14 (Australia/Sydney): merged the scout list into this file, which is now the master. 72 duplicate ideas merged, 4 repo-only ideas kept, 1 scout-only idea added (#73).
