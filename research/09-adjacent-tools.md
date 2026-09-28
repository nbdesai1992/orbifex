# 09 · Adjacent tools

Open-source tools and projects close to what Orbifex does, found while researching and while checking names. Star counts are from GitHub in September 2026. Unless noted, these have not been reviewed in depth; read them before building the matching component.

| Tool | What it is | Closest Orbifex component | Note |
|---|---|---|---|
| [Kiln](https://github.com/Kiln-AI/Kiln) (Kiln-AI, about 5,100 stars) | Open-source tool to "build, evaluate, and optimize AI systems", including synthetic data generation and evals | Forge, graders, runner | The most direct open competitor for the eval workflow; not a world builder |
| [Backlot](https://github.com/brekkylab/backlot) (about 280 stars) | "A local emulator for enterprise SaaS APIs": Slack, Gmail, Google Drive | Connectors | Study before building connectors; build on it or position against it |
| [OrgSmith](https://github.com/peterzat/OrgSmith) (about 5 stars) | "Synthetic data generator for hallucinating entire" organizations | Universe builder | Same idea, tiny |
| [SceneSmith](https://github.com/nepfaff/scenesmith) (about 600 stars) | Code for "SceneSmith: agentic generation of simulation" scenes | The agent loop (other domain) | Agentic generation for physical simulation |
| EnterpriseRAG-Bench generator ([2605.05253](https://arxiv.org/abs/2605.05253)) | Released generator for a 500K-document simulated company across 9 sources | Universe, forge, continuity | Closest published pipeline; see [02](02-worlds-and-documents.md) |
| [distilabel](https://github.com/argilla-io/distilabel) | Framework for synthetic data pipelines | Forge, loop | General-purpose pipeline tooling |
| [Ragas](https://github.com/explodinggradients/ragas) | Retrieval eval metrics and test-set generation over a knowledge graph | Benchmarks (ground-truth recipe) | The baseline for question generation over documents |
| [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) (UK AISI) | Eval framework: task, solver, scorer, sandboxes | Runner | Leading candidate runtime |
| [Harbor](https://github.com/harbor-framework/harbor) | Container task format with parallel sandboxes (Terminal-Bench 2.0) | Runner, environments | Candidate task format |
| [OpenEnv](https://github.com/huggingface/OpenEnv) (Meta and Hugging Face) | Reset, step, close spec for containerized environments | Environments | Emerging environment standard |
| [Prime Intellect verifiers](https://github.com/PrimeIntellect-ai/verifiers) | Environment definitions reusable for evals, RL, and synthetic data | Environments, graders | Large community hub; quality varies |

Name note: "Artiforge" is an AI coding orchestration product (artiforge.ai), which is why that name was not used.
