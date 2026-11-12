# AI Brain feature backlog

Proposed additions, ranked by estimated value and then effort. These are ideas, not commitments or approved implementation plans. Value runs from 1 to 5; effort is small (S) or medium (M). Numbers are stable idea identifiers, not GitHub issue numbers. Ideas #1 and #2 are already built and are not included below.

## Value 5/5

- **#3 Dynamo graph reader — M:** Map `.dyn` graphs, packages, Python nodes and compatibility issues.
- **#4 pyRevit map — M:** Show extensions, ribbon buttons, scripts and Revit versions.
- **#5 MicroStation configuration map — M:** Explain WorkSpaces, WorkSets, variables and configuration problems.
- **#6 Revit add-in version map — M:** Map .NET add-ins and flag version or manifest issues.

## Value 4/5

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

## Value 3/5

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
- **#76 Project conventions drift — M:** Find inconsistent approaches such as mixed logging libraries.
- **#77 Run provenance — M:** Record a run's command, versions and inputs so results can be compared.
- **#78 Existing diagram preview — M:** View project draw.io and JSON Canvas files inside AI Brain.

## Value 2/5

- **#70 Project vocabulary — S:** Summarise the terms most associated with each project.
- **#71 Provider failover — S:** Switch AI providers when one fails, subject to privacy settings.
- **#72 Disk-space review — S:** Identify rebuildable files that could be removed after approval.
- **#73 Obsidian/OneNote ingestion — M:** Search notes alongside project files.
- **#74 Chart answers — M:** Show charts for questions about counts and timelines.
- **#75 Measure whether AI Brain helps — M:** Compare answers, time and token use with and without its context.
