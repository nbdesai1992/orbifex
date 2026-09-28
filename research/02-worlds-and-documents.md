# 02 · Worlds and documents

## Synthetic companies: the closest prior art

These are what a synthetic data engine for enterprise evals will be compared against. The strongest share one move: build the world as structured data first, then render documents from it, and compute answers from the structure.

| Work | What it builds | Notable choices | Result |
|---|---|---|---|
| **EnterpriseRAG-Bench** (Onyx / UC Berkeley 2026, [2605.05253](https://arxiv.org/abs/2605.05253)) | About 500K documents for one simulated company across 9 source types (Slack, Gmail, Linear, Drive, HubSpot, Fireflies, GitHub, Jira, Confluence); 500 questions in 10 categories | A decision in a meeting shows up later in Slack and Confluence; deliberate noise (misfiled documents, near-duplicates, conflicts); correction-aware scoring; generator released | The closest open analogue; position against it |
| **CorporateBench** (Hamilton et al., Aug 2026, [2608.27391](https://arxiv.org/abs/2608.27391)) | A procedurally generated, time-evolving knowledge base of employees, teams, projects, and tasks, rendered into 230K+ documents; companies from 12 to 10,000 people | Structure sampled first, then documents, which guarantees consistency; human validation | Performance falls as the corpus nears realistic scale |
| **Era by Eon** (Gruenbaum et al., Sep 2026, [2609.09853](https://arxiv.org/abs/2609.09853)) | An entity graph seeds Salesforce, Zendesk, and Slack simulators across 23 companies | Question-conditioned generation; answer keys computed from the graph | Realism rose from 61.8 to 97.0; validators flagged 0 records as synthetic; only 3 of 36 model pairs differed significantly |
| **HERB** (Salesforce 2025, [2506.23139](https://arxiv.org/abs/2506.23139)) | Simulated software-company workflows emitting linked documents, transcripts, Slack, GitHub, and URLs (39,190 artifacts) | Answerable and unanswerable multi-hop questions with guaranteed ground truth; realistic noise | Best agentic retrieval scored 32.96; retrieval is the bottleneck |
| **CRMArena / CRMArena-Pro** (Salesforce, [2411.02305](https://arxiv.org/abs/2411.02305), [2505.18878](https://arxiv.org/abs/2505.18878)) | CRM org data from a real schema: 21 latent variables drive 25 object types (about 29K B2B, 55K B2C records) | Staged validation: dedup, schema and format, rule plus model plausibility | Agents degrade in multi-turn work; near-zero confidentiality awareness† |
| **EnterpriseBench** (Fujitsu, EMNLP 2025, [2510.27287](https://arxiv.org/abs/2510.27287)) | 500 tasks across engineering, HR, finance, admin | Access-control hierarchies; tasks generated consistently from organizational metadata | Best agent 41.8% |
| **WinSyn** (Sep 2026, [2609.12171](https://arxiv.org/abs/2609.12171)) | Multi-month projects with up to 25 role-played employees producing email | Information spread across messages; natural ambiguity | Frontier QA below 80% |
| **WorkBench** ([2405.00823](https://arxiv.org/abs/2405.00823)), **TheAgentCompany** ([2412.14161](https://arxiv.org/abs/2412.14161)) | Small databases for email, calendar, CRM, analytics, projects; a self-hosted fake software company | Graded on resulting state; checkpoint partial credit | See [03](03-environments-and-connectors.md) |

A standing critique to answer: Workspace-Bench 1.0 ([2605.03596](https://arxiv.org/abs/2605.03596)) argues synthesized files have "limited real-world dependencies". The answer is a world graph with real cross-references and measured mess ([07](07-messiness.md)).

## Question generation over documents

- **RAGAS** ([2309.15217](https://arxiv.org/abs/2309.15217)): reference-free faithfulness and relevance metrics; its library builds a knowledge graph over chunks to evolve single-hop, multi-hop, and reasoning questions (*library docs; unverified in the paper*). The baseline to beat.
- **ARES** ([2311.09476](https://arxiv.org/abs/2311.09476)): synthetic queries, light fine-tuned judges, a small human set, and prediction-powered confidence intervals. The template for "large synthetic set plus small human set plus statistics".
- **DataMorgana** (TII 2025, [2501.12789](https://arxiv.org/abs/2501.12789)): a JSON config of user types and question types with probabilities, combined into prompts; much more diverse than alternatives; the official generator for SIGIR 2025 LiveRAG. The right interface: declarative distributions.

## Structured and visual documents

- **Spreadsheets.** SheetCopilot ([2305.19308](https://arxiv.org/abs/2305.19308)) and SpreadsheetBench 2 ([2606.29955](https://arxiv.org/abs/2606.29955)) evaluate spreadsheet work; neither is a generator. For generation: render from the graph with live formulas and check they recompute.
- **PDFs and layouts.** DocSynth ([2107.02638](https://arxiv.org/abs/2107.02638)) is GAN-based and dated. No dominant 2025–26 method for synthetic business PDFs was found; render templated HTML or LaTeX to PDF or DOCX, then add scan and OCR noise as mess.

## Code repositories

Start from a working state and inject a verifiable break, so execution decides correctness.

- **SWE-smith** ([2504.21798](https://arxiv.org/abs/2504.21798)): synthesizes bugs that break existing tests in real repos (about 50K instances from 128 repos†).
- **R2E-Gym** ([2504.07164](https://arxiv.org/abs/2504.07164)): environments procedurally built by back-translating commits, with hybrid verifiers.
- **SWE-Gym** ([2412.21139](https://arxiv.org/abs/2412.21139)): executable real tasks.

## What this implies

1. A typed, time-stamped world graph is the source of truth; documents are views of it; answers are queries on it.
2. Cross-source coherence is the realism test: one decision should echo across meeting, chat, and wiki, sometimes inconsistently on purpose.
3. Question and user distributions belong in config, with target shares.
4. Answerable, unanswerable, and conflicting questions all belong in the mix.
5. Scale matters: small worlds flatter models. Plan for a size ladder.
6. With few items, model differences are rarely significant. Size evals with a power check.
