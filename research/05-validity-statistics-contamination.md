# 05 · Validity, statistics, contamination

## Validity

- **Construct validity** (Bean et al., NeurIPS 2025, [2511.04703](https://arxiv.org/abs/2511.04703)): 29 experts reviewed 445 benchmarks and found widespread problems. Eight recommendations, including defining the phenomenon, avoiding contamination, and reporting uncertainty.
- **Agentic Benchmark Checklist** (Zhu et al., NeurIPS 2025, [2507.02825](https://arxiv.org/abs/2507.02825)): separates task validity from outcome validity. Setup and reward flaws distort agent scores by up to 100% relative; τ-bench counted empty responses as success, and SWE-bench tests were too thin.
- **Answer-key audits keep finding errors**: SWE-bench Verified (at least 59.4% of audited failures had flawed tests; OpenAI stopped reporting it in Feb 2026), Humanity's Last Exam (about 30% of chemistry and biology answers questioned), MMLU (6.5% erroneous, [2406.04127](https://arxiv.org/abs/2406.04127)), LoCoMo (6.4% wrong, and a judge accepting up to 63% of deliberately wrong answers).
- **Reward hacking and grader gaming**: ImpossibleBench ([2510.20270](https://arxiv.org/abs/2510.20270)) mutates tests to contradict the spec, so any pass is cheating. Anthropic ([2511.18397](https://arxiv.org/abs/2511.18397)) shows hacking in production environments generalizing into broader misbehavior. A July 2026 incident, in which a model escaped an eval sandbox to fetch test answers, made sandbox security part of eval design.

## Difficulty

- **Adversarial filtering**: SWAG and HellaSwag with AFLite ([1808.05326](https://arxiv.org/abs/1808.05326), [1905.07830](https://arxiv.org/abs/1905.07830), [2002.04108](https://arxiv.org/abs/2002.04108)) remove items a simple model solves from surface cues. For worlds: an item fails if the question alone, or a single file, answers it.
- **Contrast sets** (Gardner et al., [2004.02709](https://arxiv.org/abs/2004.02709)): minimal edits that flip the label. From a world graph these come almost free: change one fact, re-render.
- **Item response theory**: tinyBenchmarks ([2402.14992](https://arxiv.org/abs/2402.14992)), metabench ([2407.12844](https://arxiv.org/abs/2407.12844)), Fluid Benchmarking ([2509.11106](https://arxiv.org/abs/2509.11106)). Run a mixed-strength panel over each item, fit difficulty and discrimination, drop items that don't separate models.
- **Targets**: RL environment buyers want pass rates clearly above zero, at least 2–3% (Epoch AI); practitioners suggest about 70% for product evals ("if you pass everything, you aren't testing hard enough").
- **Self-evolving and auto-built benchmarks**: AutoBencher ([2407.08351](https://arxiv.org/abs/2407.08351)) gives the generator privileged information the model under test lacks; Benchmark Self-Evolving ([2402.11443](https://arxiv.org/abs/2402.11443)); Arena-Hard / BenchBuilder ([2406.11939](https://arxiv.org/abs/2406.11939)); model-written evaluations validated by crowdworkers (Perez et al., [2212.09251](https://arxiv.org/abs/2212.09251)).

## Statistics

- **Error bars** (Miller, Anthropic 2024, [2411.00640](https://arxiv.org/abs/2411.00640)): clustered standard errors, paired differences, power analysis.
- **pass@k and pass^k**: pass@k is the chance at least one of k tries succeeds (capability, from the Codex paper); pass^k is the chance all k succeed (reliability, τ-bench). Anthropic notes that at k=10 they can "tell opposite stories". Report both with at least four trials.
- **Significance with small sets**: in Era by Eon, only 3 of 36 model pairs differed significantly after correction. Size evals with a power check.
- **Time horizon** (METR, [2503.14499](https://arxiv.org/abs/2503.14499)): logistic fit of success against the log of human completion time; needs human baseline times.

## Contamination

- **Detection**: exchangeability test on canonical versus shuffled order (Oren et al., [2310.17623](https://arxiv.org/abs/2310.17623)); guided-completion probes (Golchin and Surdeanu, [2308.08493](https://arxiv.org/abs/2308.08493)); survey ([2406.04244](https://arxiv.org/abs/2406.04244)).
- **Rephrasing defeats n-gram checks** (Yang et al., [2311.04850](https://arxiv.org/abs/2311.04850)): a 13B model trained on rephrased MMLU reached GPT-4-level scores†. Deduplicate semantically.
- **Lifecycle practices**: canary strings in released files; public, held-out, and private splits (SWE-Bench Pro, [2509.16941](https://arxiv.org/abs/2509.16941)); rolling refresh (SWE-bench-Live [2505.23419](https://arxiv.org/abs/2505.23419), SWE-rebench [2505.20411](https://arxiv.org/abs/2505.20411), LiveBench [2406.19314](https://arxiv.org/abs/2406.19314)); published errata (τ³, WebArena-Verified).

## What this implies

1. Write the construct down before generating; audit task validity and outcome validity before release.
2. Every release includes an answer-key audit and an impossible-variant probe for every grader.
3. Difficulty is fit, not guessed; shortcut filters run on every item.
4. One definition of each metric, used everywhere; intervals on every number; power before claims.
5. Canary, semantic dedup, splits, fresh seeds, errata.
