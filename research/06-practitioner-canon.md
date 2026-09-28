# 06 · The practitioner canon

What people building evals actually cite and argue about, from roughly 40 sources across Reddit (via an archive, since reddit.com blocks fetches), Hacker News, and lab and practitioner writing. "Most cited" is a count across this sample, not a census.

## Most cited

1. **MT-Bench / LLM-as-a-judge** (Zheng et al. 2023). The founding judge paper; criticized for measuring agreement on general chat.
2. **SWE-bench / Verified.** The reference agent environment; retired by OpenAI in Feb 2026 for flawed tests and contamination, in favor of SWE-bench Pro.
3. **Hamel Husain and Shreya Shankar's Evals FAQ** ([hamel.dev](https://hamel.dev/blog/posts/evals-faq/)) and course. The working manual; criticized as labor-heavy and light on statistics.
4. **Who Validates the Validators?** (criteria drift).
5. **Chatbot Arena and "The Leaderboard Illusion"** ([2504.20879](https://arxiv.org/abs/2504.20879)).
6. **Model collapse** (Nature 2024) with the "accumulate, don't replace" correction. Most practitioners treat collapse fears as overstated; the live worry is style sameness ("slop").
7. **τ-bench / τ²-bench** and pass^k.
8. **Codex / HumanEval** for pass@k vocabulary.
9. **Humanity's Last Exam**, and its answer-key problems.
10. **Self-Instruct, Alpaca, Evol-Instruct, Orca**: mostly historical now.
11. **Phi, Cosmopedia, Hugging Face's Synthetic Data Playbook (FinePhrase).**
12. **Persona Hub and Magpie**: the two standard diversity methods.
13. **Tulu 3, OLMo 2, Nathan Lambert's RLHF Book** ([rlhfbook.com](https://rlhfbook.com/c/15-synthetic)).
14. **DeepSeek R1 and V3**: distillation and verifiable rewards; why RL environments took off.
15. **Eugene Yan's "Evaluating LLM-Evaluators"** ([eugeneyan.com](https://eugeneyan.com/writing/llm-evaluators/)).
16. **Lilian Weng, "Reward Hacking in RL"** ([lilianweng.github.io](https://lilianweng.github.io/posts/2024-11-28-reward-hacking/)).
17. **Agentic Benchmark Checklist.**
18. **WebArena, OSWorld, Terminal-Bench, BrowseComp.**
19. **GDPval, Mercor APEX, Surge AdvancedIF**: the 2025–26 turn to expert-built evals.
20. **Prime Intellect `verifiers` and Environments Hub; distilabel.**

Also central: Anthropic's "Demystifying evals for AI agents" (Jan 2026), Jason Wei's "Successful language model evals", Chip Huyen on evaluation-driven development, and Epoch AI's FAQ on RL environments.

## Consensus

1. Look at data before choosing metrics: read about 100 traces, name failure modes, count them.
2. Cheapest grader first. "Never use a model where regex or an AST parse works" is close to universal.
3. Pass/fail or pairwise, not 1-to-5 scales.
4. A judge is a model with its own test set: 100 to 200 human labels per failure mode, split, with true positive and true negative rates.
5. Build evals from your own traffic and past failures; start with 20 to 50 tasks.
6. Keep capability evals (low pass rate) apart from regression evals (near 100%); saturated capability evals move to regression.
7. Agent evals grade outcomes and environment state, and report pass^k.
8. Public benchmarks saturate and leak; private, fresh, or rolling sets are the answer.
9. Audit the answer key; label errors can dominate "failures".
10. For RL environments, reward-hacking resistance is the minimum bar, and sandbox security is part of it.
11. Synthetic data needs structured diversity: condition on dimensions or personas, one item per call, dedupe, verify, anchor on real seeds.
12. Synthetic training data works where outputs are verifiable; indiscriminate recursive training is what collapses.
13. Noisy judges are fine for comparing systems in aggregate, not as per-output guardrails.
14. Don't outsource the core loop: in-house experts own quality; outside annotators scale it.

## Disagreements

- **Error analysis first, or metrics first.** Product teams (Husain and Shankar) say look first. Benchmark builders (Jason Wei) want a single number and 1,000+ items up front.
- **How far to trust judges.** Optimists cite correlation with humans and aggregate ranking; skeptics cite correlated errors between agent and judge.
- **Synthetic data for evals.** Husain treats synthetic test inputs from structured dimensions as acceptable but a last resort for sensitive data. Surge and Mercor argue prompts and rubrics must be human-written. Nobody disputes synthetic training data where outputs are verifiable.
- **Are benchmarks dead?** Surge treats them as marketing; SWE-bench's co-creator says saturation is normal and the answer is the next benchmark; Epoch says prefer slow-saturating, expert-curated ones.
- **RL environments as a business.** Epoch documents a large market (six to seven figure quarterly contracts; about $20K for a website replica, up to $300K for a complex product simulation; $200–2,000 per task). Critics call environment building a temporary rung; Nathan Lambert expects hard environments to get "exponentially harder" to build.

## Enterprise practice

Start with notebook review and one expert. Build a versioned golden set from four sources: a production sample, adversarial cases, edge cases, and replays of shipped failures. Run it as a release gate against the last shipped baseline. Redo error analysis every two to four weeks, and spot-check 10 to 20 outlier traces weekly. Expect to build in-house on an observability tool rather than buy an eval product.

## What this implies

Our design has to satisfy both camps: an error-analysis-first workflow for designing an eval, and metrics-grade rigor (size, intervals, audits) before releasing one. Synthetic data must answer the "human-written only" critique with measured realism and human-owned rubrics.
