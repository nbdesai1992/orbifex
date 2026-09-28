# 07 · Real-world messiness

Agents fail on the mess in real company data, not on clean documents. A synthetic world that is too tidy measures the wrong thing. This note collects what the literature says about realistic noise, proposes a taxonomy to measure, and sketches how to measure it. The taxonomy is a hypothesis until measured.

## What prior work injects

| Work | Mess it models |
|---|---|
| EnterpriseRAG-Bench ([2605.05253](https://arxiv.org/abs/2605.05253)) | Misfiled documents, near-duplicates, conflicting information across sources |
| HERB ([2506.23139](https://arxiv.org/abs/2506.23139)) | Realistic noise across linked artifacts; unanswerable questions |
| CRMArena-Pro ([2505.18878](https://arxiv.org/abs/2505.18878)) | Latent variables producing coherent but imperfect records; confidentiality constraints |
| EnterpriseBench ([2510.27287](https://arxiv.org/abs/2510.27287)) | Fragmented sources; access-control hierarchies |
| WinSyn ([2609.12171](https://arxiv.org/abs/2609.12171)) | Information distributed across emails; natural ambiguity |
| ToolSandbox ([2408.04682](https://arxiv.org/abs/2408.04682)) | Implicit preconditions between tools |
| `persona-artifact-factory` (ours, see [08](08-own-assets.md)) | Treatment classes T0–T3 and planted discrepancies with known answers |

The critique to answer (Workspace-Bench 1.0, [2605.03596](https://arxiv.org/abs/2605.03596)): synthesized files have "limited real-world dependencies". Mess must be relational (between files), not only cosmetic (within a file).

## A taxonomy to measure

| Family | Within a file | Between files |
|---|---|---|
| **Versioning** | Tracked changes left in; "v3_FINAL_real" | A superseded figure still quoted downstream |
| **Duplication** | Copy-pasted table that drifted | The same thread forwarded twice with different replies |
| **Conflict** | Summary disagrees with its own table | Chat decision contradicts the spec; two dates for one deadline |
| **Omission** | Half-filled CRM fields | "See attached" with nothing attached; a link to a deleted file |
| **Misplacement** | Decision buried in an unrelated thread | Document in the wrong project folder |
| **Format damage** | OCR errors, broken tables, merged cells, shifted CSV columns | Timezone mixups across calendar and email |
| **Human habits** | Typos, shorthand, emoji answers, replies above quotes | Nicknames for the same client across teams |
| **Access** | Redacted sections | Files only some personas can see; stale shared links |
| **Temporal** | "Next Friday" without a date | Events referenced before they happened (backdated notes) |

## How to measure it

1. **Open sources, license-checked**: the Enron email corpus, public Slack and Discord exports, GitHub issues and PRs, SEC EDGAR filings and exhibits, open government contracts and RFPs, public meeting transcripts. Record license and allowed use first.
2. **Profilers**: agents plus code that tag each mess type and estimate its rate per file type and per relationship. Output a mess profile: rates, co-occurrence, and examples.
3. **Private data, local only**: when a partner provides real data, the profiler runs on their machine and exports statistics only, never text.
4. **Validation**: a blind real-versus-synthetic judge per file type (Era by Eon reached 0 records flagged), and, more strongly, agreement between model rankings on the synthetic world and on the partner's real data.

## Mess as operators

Each mess type becomes an operator that edits a rendered file or the graph, is tagged in the graph (so graders know it is intentional), and is reversible (so a clean twin exists for minimal-pair comparisons). Rates come from the measured profile, adjustable per eval.

## Open questions

- Which mess types actually move agent scores? Measure by ablation: the same world with each operator on and off.
- How to keep planted conflicts fair: every conflict needs a rule for which source wins (latest, most authoritative, or "ask"), stated in the world's policy.
