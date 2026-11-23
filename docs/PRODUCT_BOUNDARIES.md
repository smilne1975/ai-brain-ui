# Product ownership and adoption

AI Brain, MicroStationBot and the Orchestrator can ship independently. The upstream references below are review inputs, not dependencies. All three keep their own user data and settings.

| Work | Owner |
|---|---|
| Capture, search, citations, research workspaces, maps, decisions and memory useful without writing code | AI Brain UI |
| CAD/BIM/AEC interpretation or UI: key-ins, WorkSets, DGN models/references, CAD standards and live model access | MicroStationBot; defer other vendor adapters until the owner and demand are agreed |
| General agent/model routing, approval, handoffs, and orchestration controls | Orchestration agent and its standalone product; each host owns its own adapters |

Split mixed work. For example, AI Brain owns an evidence map that can show any source-backed relationship; MicroStationBot owns finding and explaining DGN references. The Orchestrator owns a general approval pattern; MicroStationBot owns how approval interacts with a live model. Keep GitHub history where it is; link any scoped successor before retiring an old ticket. Do not copy private notes or private issue contents into the public repository.

For the existing AI Brain backlog: saved workspaces (#99), decision triage (#19), capture (#96), evidence maps (#53), and source review (#80) remain general. The MicroStation configuration, live model, and standards tickets (#1, #35, #27) are migration or routing references, not new standalone AI Brain builds. Tool-specific Revit and Dynamo proposals (#3, #9, #20, #29, #40) should not be built here; choose a specialist owner before filing or building replacements. Generic version comparison, dependencies, and citation navigation can still be developed in AI Brain using neutral examples.

## Handoff after a change ships

1. The source owner verifies the change merged and shares the public link (or the approved internal reference), what changed, and an acceptance test with the relevant receiving owner only. Share no user data, secrets, or private paths.
2. The receiver records `review`, `adopt`, `adapt`, `defer`, or `skip` in its own issue or adoption ledger. Note the reason, downstream owner, local issue/PR and standalone test. Check for an existing handoff before creating another.
3. Adoption is a separate, reviewed change. Do not mirror repos, sync user data, install dependencies, schedule a build, start Cursor, or merge automatically. A shared package is worth considering only if maintaining the same mature logic twice becomes a demonstrated cost.

For OpenBot, start **Route product work and adoption** manually to get a routing proposal from the Orchestration agent. It does not notify owners or build anything by itself. Use sample data or links safe to share with that agent.

## Legacy CAD cutover checklist

- [ ] Confirm MicroStationBot's own brain runs without installing or starting AI Brain.
- [ ] Confirm MicroStationBot can replace the existing WorkSet/configuration and key-in journeys with representative tests. Record which legacy clients, if any, still use AI Brain's `BRAIN_LEGACY_CAD=1` lane.
- [ ] Publish a migration note and agree the cutover with Stu before removing compatibility code or closing migrated work.

### Handoff record (template)

```text
Upstream issue / merged PR:
Receiving product and owner:
Choice (review / adopt / adapt / defer / skip) and reason:
What transfers; what stays local:
Downstream issue / PR:
Acceptance test and result (not run / passed / failed):
```
