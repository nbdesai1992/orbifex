# 03 · Environments and connectors

## Tool-use environments with simulated users and tools

| Work | State and tools | Grading | Borrow |
|---|---|---|---|
| **τ-bench** (Sierra 2024, [2406.12045](https://arxiv.org/abs/2406.12045)) | JSON databases behind Python tool functions; a model plays the user from a hidden instruction; a written policy document | Final database state against the goal; introduced **pass^k** | pass^k; policy documents as rules; state diff as the main grader |
| **τ²-bench** ([2506.07982](https://arxiv.org/abs/2506.07982)) | Dual control: the user also has tools and state | State plus communication checks | Give the user simulator its own tools when the task needs it |
| **τ³ / τ-Knowledge** (2026, [2603.04370](https://arxiv.org/abs/2603.04370)) | Adds a banking knowledge base and voice | Backend side effects; published grading fixes | Grade side effects; plan for errata |
| **ToolEmu** ([2309.15817](https://arxiv.org/abs/2309.15817)) | A model emulates tool execution, including adversarially | Model safety and helpfulness evaluators, human-checked | Adversarial emulation for safety probes, kept separate from grading |
| **StableToolBench** ([2403.07714](https://arxiv.org/abs/2403.07714)) | Cache recorded responses; simulate with a model on a miss | Solvable pass rate, pre-filtered | Cache-then-simulate; filter unsolvable tasks first |
| **BFCL v1 to v4** (Berkeley) | Deterministic in-memory Python classes | AST match for single calls; state checks for multi-turn; abstention | Stateful Python classes as cheap connectors |
| **AppWorld** ([2407.18901](https://arxiv.org/abs/2407.18901)) | 9 apps, 457 APIs, about 100 simulated people, backed by real databases | State-based unit tests, including checks that nothing else changed | The most directly relevant: a coherent seeded population across apps and collateral-damage checks |
| **ToolSandbox** (Apple, [2408.04682](https://arxiv.org/abs/2408.04682)) | Stateful tools with implicit preconditions (cellular must be on to message) | **Milestones** (required states) and **minefields** (forbidden states) | Preconditions; milestone and minefield grading |
| **ARE / Gaia2** (Meta, [2509.17158](https://arxiv.org/abs/2509.17158), [2602.11964](https://arxiv.org/abs/2602.11964)) | 12 apps, 101 tools, 10 consistent "universes" of 400–800K tokens; time passes while the model thinks; scheduled events | Verifier compares the agent's write actions to an oracle's: exact on IDs, rubric on free text, causal order, timing; 0.98 agreement with human labels | The closest blueprint: universes, write-action oracle, time and events |
| **MCP benchmarks**: MCPMark ([2509.24002](https://arxiv.org/abs/2509.24002)), MCP-Universe ([2508.14704](https://arxiv.org/abs/2508.14704)), MCP-Bench ([2508.20453](https://arxiv.org/abs/2508.20453)), LiveMCPBench ([2508.01780](https://arxiv.org/abs/2508.01780)), Toolathlon ([2510.25726](https://arxiv.org/abs/2510.25726)) | Real or self-hosted services behind MCP, reset to curated states; one container per task (Toolathlon) | Per-task verify scripts; pass@1 and pass^4 (MCPMark: 52.6% vs 33.9% for GPT-5-medium) | Serve connectors over MCP; seeded state plus a verify script per task |

## Workplace environments

- **TheAgentCompany** ([2412.14161](https://arxiv.org/abs/2412.14161)): self-hosted GitLab, Plane, RocketChat, OwnCloud; model-played colleagues; 175 tasks; checkpoint partial credit.
- **WorkArena / WorkArena++** ([2403.07718](https://arxiv.org/abs/2403.07718), [2407.05291](https://arxiv.org/abs/2407.05291)): a real ServiceNow instance; template times seed.
- **WorkBench** ([2405.00823](https://arxiv.org/abs/2405.00823)): five small databases, 26 tools, 690 tasks, graded purely on final state. The simplest template for fake mail, calendar, and CRM.
- **OSWorld** ([2404.07972](https://arxiv.org/abs/2404.07972)), **WebArena** ([2307.13854](https://arxiv.org/abs/2307.13854)) and **WebArena-Verified** (an audit that removed the model judge and substring matching).
- **GDPval** (OpenAI 2025, [2510.04374](https://arxiv.org/abs/2510.04374)): 1,320 tasks from 44 occupations producing real work product, graded blind and pairwise by experts.
- **CoreCraft** (Surge 2026, [2602.16179](https://arxiv.org/abs/2602.16179)): a simulated support org with 2,500+ entities; expert rubrics where every criterion must pass; training on it transferred to other benchmarks.
- **EnterpriseClawBench** ([2606.23654](https://arxiv.org/abs/2606.23654)): reports harness × model, cost, runtime, and artifact quality rather than one score.

## Environment synthesis at scale

AgentScaler ([2509.13311](https://arxiv.org/abs/2509.13311)) turns API clusters into read and write databases, so a tool is a database operation. EnvScaler ([2601.05808](https://arxiv.org/abs/2601.05808)) builds 191 code-backed environments with rule-based validators and avoids model simulation. SynthTools ([2511.09572](https://arxiv.org/abs/2511.09572)) filters out tools that can't be emulated reliably. EnvFactory ([2605.18703](https://arxiv.org/abs/2605.18703)): 85 verified stateful environments beat pipelines using five times more. **EnvSimBench** ([2605.07247](https://arxiv.org/abs/2605.07247)) finds the "state change cliff": models simulate unchanged state well and fail badly when several fields must change together.

## Evaluating app-building harnesses

For a harness like Consul (spec in, deployed app out), the consensus stack:

1. **Hidden end-to-end workflows against the deployed URL**, scripted (SWE-Lancer, [2502.12115](https://arxiv.org/abs/2502.12115)) or run by a browser agent (Vibe Code Bench, [2603.04601](https://arxiv.org/abs/2603.04601): 100 specs, 964 workflows).
2. **Contract tests over HTTP** (BackendForge, [2607.11042](https://arxiv.org/abs/2607.11042)).
3. **Hierarchical requirement rubrics** checked by an agent judge (Agent-as-a-Judge / DevAI, [2410.10934](https://arxiv.org/abs/2410.10934)).
4. **Visual checks** (VISTA, [2605.26144](https://arxiv.org/abs/2605.26144); ArtifactsBench, [2507.04952](https://arxiv.org/abs/2507.04952)).
5. **Human pairwise preference** for UX ("From Prompt to Product", [2512.18080](https://arxiv.org/abs/2512.18080)).

Commit0 ([2412.01769](https://arxiv.org/abs/2412.01769)) is the closest analogue for spec to whole codebase. Caution from Vibe Code Bench: step-level agreement between evaluator agents ranged from 31.8% to 93.6%, so calibrate browser-agent graders against people.

## Runtimes and task formats

- **Inspect** (UK AISI): task = dataset + solver + scorer, with sandboxes and per-sample logs. The strongest open base.
- **Harbor** (Terminal-Bench 2.0, [2601.11868](https://arxiv.org/abs/2601.11868)): a container, an instruction, and a test script per task.
- **OpenEnv** (Meta and Hugging Face, 2025): a reset/step/close spec for containerized environments, aiming to be the shared standard.
- **Prime Intellect `verifiers`** and Environments Hub; **METR task standard**.

## Environment architectures compared

| Architecture | Examples | Strength | Weakness |
|---|---|---|---|
| Real sandboxed apps | WebArena, TheAgentCompany, OSWorld, SWE-bench | Highest fidelity | Heavy, slow to reset, hard to seed |
| Real live APIs and MCP servers | ToolBench, MCP-Universe | No build cost | Unstable, unrepeatable, unsafe for writes |
| **Code-backed simulators** | τ-bench, AppWorld, WorkBench, ARE, EnvScaler | Deterministic, cheap reset, exact state diffs, seedable | Engineering cost per connector; edge cases hand-written |
| Model-emulated tools | ToolEmu, Simia, SynthTools | Unlimited breadth | State drift, no ground truth |
| Replay and cache | StableToolBench, WebArena-Verified | Reproducible | Only covers recorded paths |
| **Hybrid** | ARE, StableToolBench | Deterministic core, flexible edges | More moving parts |

## What this implies

1. Every connector sits on a typed, code-backed store. Models write content at seed time only.
2. One universe per seed, shared by every connector, so tasks require joining across apps.
3. Tools are thin, validated operations with realistic preconditions, permissions, pagination, and errors, served over MCP; graders use a separate API the agent can't reach.
4. Grade outcomes by state diff plus a collateral-damage check; add action oracles only where order and timing matter; keep model judges to free-text fields and validate them.
5. The user simulator is a component with variance: pin it, and report across two or more simulator models ("Lost in Simulation", [2601.17087](https://arxiv.org/abs/2601.17087): up to 9 points of swing).
6. One isolated container per task, deterministic reset, grader code out of the agent's reach.
7. Red-team graders before release: impossible variants must fail (ImpossibleBench, [2510.20270](https://arxiv.org/abs/2510.20270)).
