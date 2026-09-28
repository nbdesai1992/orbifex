# 04 · Graders and humans

## Model judges

- **MT-Bench and Chatbot Arena** (Zheng et al. 2023, [2306.05685](https://arxiv.org/abs/2306.05685)): a strong model agrees with humans over 80% of the time, about as often as humans agree with each other. Names position, verbosity, and self-enhancement bias, with mitigations (swap order, reference-guided grading). Measured on general chat, not domain work.
- **G-Eval** ([2303.16634](https://arxiv.org/abs/2303.16634)): chain-of-thought steps and probability-weighted scores. Practitioners often call it unreliable.
- **Prometheus 1 and 2** ([2310.08491](https://arxiv.org/abs/2310.08491), [2405.01535](https://arxiv.org/abs/2405.01535)): open-weight judges conditioned on custom rubrics; reproducible grading.
- **Bias catalogues**: position bias ([2305.17926](https://arxiv.org/abs/2305.17926)), length control ([2404.04475](https://arxiv.org/abs/2404.04475)), twelve biases ([2410.02736](https://arxiv.org/abs/2410.02736)), JudgeBench ([2410.12784](https://arxiv.org/abs/2410.12784)), self-preference ([2404.13076](https://arxiv.org/abs/2404.13076)).
- **Juries** (PoLL, Verga et al. 2024, [2404.18796](https://arxiv.org/abs/2404.18796)): three smaller judges from different families beat one large judge, with less bias and about seven times lower cost†. Practitioner caveat: juries only help if their errors are independent.
- **Noisy judges still rank systems** (TensorZero 2026): a judge with 0.41 correlation per output reached 0.96 per agent. Fine for comparing systems in aggregate; not for per-output guardrails.

## Self-bias is the biggest threat to synthetic evals

*When LLMs Benchmark Themselves* (Google 2025, [2509.26600](https://arxiv.org/abs/2509.26600)): benchmarks a model writes favor that model, through two additive channels (author and evaluator). Combined, each model ranks itself first. Source diversity reduces it. ProfBench ([2510.18941](https://arxiv.org/abs/2510.18941)) reports self-enhancement when the same model writes the rubric and grades.

## Humans in the loop

- **Criteria drift** (Shankar et al., "Who Validates the Validators?", [2404.12272](https://arxiv.org/abs/2404.12272)): people can't define criteria until they've graded outputs, and grading changes the criteria. So humans write rubrics by grading samples, and the system proposes assertions that match their grades.
- **Selective escalation** (Trust or Escalate, [2407.18370](https://arxiv.org/abs/2407.18370)): estimate judge confidence and send only low-confidence cases up, with a guarantee of over 80% human agreement at about 80% coverage.
- **Justifying an automated annotator** (the Alternative Annotator Test, ACL 2025, [2501.10970](https://arxiv.org/abs/2501.10970)): a statistical test on a modest human subset before replacing people.
- **Prediction-powered inference** ([2301.09633](https://arxiv.org/abs/2301.09633); [2408.15204](https://arxiv.org/abs/2408.15204)): combine a small gold set with many model labels to get valid intervals.
- **Limits** (Dorner et al., [2410.13341](https://arxiv.org/abs/2410.13341)): when the judge isn't stronger than the model under test, debiasing can at best halve the human labels needed. At the frontier, people stay in the loop.
- **Agreement varies by task** (JUDGE-BENCH, [2406.18403](https://arxiv.org/abs/2406.18403)), and human raters have their own blind spots: they under-weight factuality and favor confident answers ([2309.16349](https://arxiv.org/abs/2309.16349)).
- **Model as annotator precedents**: Constitutional AI ([2212.08073](https://arxiv.org/abs/2212.08073)), RLAIF ([2309.00267](https://arxiv.org/abs/2309.00267)), Self-Taught Evaluators ([2408.02666](https://arxiv.org/abs/2408.02666)). A written quality constitution is a reasonable spec for model gates.

## Expert protocols

- **GPQA** ([2311.12022](https://arxiv.org/abs/2311.12022)): an expert writes, a second validates, the writer revises, a third validates; skilled non-experts with web access try it too. Expert agreement measures objectivity.
- **Humanity's Last Exam** ([2501.14249](https://arxiv.org/abs/2501.14249)): accepted only if frontier models fail, then two expert review rounds. An external audit questioned about 30% of chemistry and biology answers (*reported by FutureHouse*). Filtering against frontier models raises label-error risk.
- **SimpleQA** ([2411.04368](https://arxiv.org/abs/2411.04368)): two independent trainers must agree on one indisputable answer; estimated error about 3%†.
- **HealthBench** ([2505.08775](https://arxiv.org/abs/2505.08775)): 48,562 criteria from 262 physicians; the model grader is checked against physicians.
- **GDPval** ([2510.04374](https://arxiv.org/abs/2510.04374)): experts averaging 14 years of experience; about five reviews per task; automated grader agrees with experts 66% of the time against 71% between humans.
- **Rubric shapes**: PaperBench ([2504.01848](https://arxiv.org/abs/2504.01848)) hierarchical trees with weighted leaves; CoreCraft all-criteria-must-pass; HealthBench weighted with negative points.

## Where people are essential

| Essential | Replaceable |
|---|---|
| Defining quality; the first 30 or so annotations by one domain expert | Objective checks: schema, tests, regex, state |
| Calibrating every automated judge (100 to 200 labels per failure mode, true positive and true negative rates) | Bulk filtering of synthetic candidates |
| Subjective and high-stakes domains | Relative comparisons of systems over many items |
| Hard, frontier-failing items (they need more review) | Structured fake records (a faker library) |
| Reading transcripts and auditing answer keys | |

## What this implies

1. Grader order: code, then a mixed-family jury with both answer orders, then people.
2. Each judge ships with a labeled validation set and its agreement numbers.
3. Author, judges, and the model under test come from different families; report across generators.
4. People write rubrics by grading samples, review the disagreement set, and audit hard items and answer keys.
5. Use pass/fail and pairwise judgments, not 1-to-5 scales.
