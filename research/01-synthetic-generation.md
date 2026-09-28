# 01 · Generating synthetic data

## The lineage

| Work | Method | What it teaches us |
|---|---|---|
| **Self-Instruct** (Wang et al. 2022, [2212.10560](https://arxiv.org/abs/2212.10560)) | 175 seed tasks; the model writes instructions, inputs, and outputs; filter by ROUGE-L and heuristics; add survivors back to the pool | The basic loop: seed, generate, filter, add back |
| **Unnatural Instructions** (Honovich et al. 2022, [2212.09689](https://arxiv.org/abs/2212.09689)) | Few demonstrations, then paraphrase expansion | Paraphrase adds surface variety, and also contamination risk |
| **Evol-Instruct / WizardLM** (Xu et al. 2023, [2304.12244](https://arxiv.org/abs/2304.12244)) | Rewrite operators: add constraints, deepen, concretize, add reasoning, mutate topic; drop failed evolutions | Evolution operators give a controlled difficulty ladder ("add a conflicting email", "add a date constraint") |
| **Orca / Orca 2** ([2306.02707](https://arxiv.org/abs/2306.02707), [2311.11045](https://arxiv.org/abs/2311.11045)) | Explanation traces from a stronger model | Keep the rationale behind every gold answer, for review and audit |
| **Phi series** (phi-1 [2306.11644](https://arxiv.org/abs/2306.11644), phi-4 [2412.08905](https://arxiv.org/abs/2412.08905)) | Curated seeds, synthetic textbooks, multi-agent prompting, self-revision | Seed quality beats volume; phi-4's report doubles as a decontamination case study |
| **Cosmopedia** (Hugging Face 2024; folded into SmolLM2 [2502.02737](https://arxiv.org/abs/2502.02737)) | Diversity from a grid of topic, audience, and format rather than temperature | A declared grid is the cheapest diversity lever |
| **Magpie** (Xu et al. 2024, [2406.08464](https://arxiv.org/abs/2406.08464)) | Give an aligned model only the chat prefix, so it writes its own user query | Natural-sounding asks without seed prompts; useful for tickets and chat |
| **Persona Hub** (Ge et al. 2024, [2406.20094](https://arxiv.org/abs/2406.20094)) | About 1B personas mined from the web; condition every generation on one | The main diversity engine for a synthetic company: every author is a sampled persona |
| **AgentInstruct** (Mitra et al. 2024, [2407.03502](https://arxiv.org/abs/2407.03502)) | Transform raw content into a target document type, then generate and refine with suggester and editor agents | The template for "raw seed, typed document, eval item" |
| **Nemotron-4 340B** ([2406.11704](https://arxiv.org/abs/2406.11704)) | Topic-taxonomy prompts, reward-model filtering; over 98% synthetic alignment data with about 20K human examples† | A small human set can anchor a mostly synthetic pipeline |
| **Genie** (Yehudai et al. 2024, [2401.14367](https://arxiv.org/abs/2401.14367)) | Prepare grounding content, generate, filter for faithfulness | Faithfulness filters as a gate |
| **EntiGraph** (Yang et al. 2024, [2409.07431](https://arxiv.org/abs/2409.07431)) | Extract entities, then generate text about entity pairs and triples | Supports "graph first, render second" |
| **Instruction Backtranslation** ([2308.06259](https://arxiv.org/abs/2308.06259)); **Source2Synth** ([2409.08239](https://arxiv.org/abs/2409.08239)) | Write the document first, then the question it answers; ground in real tables and documents | For evals, backtranslation makes the ground truth checkable |
| **APIGen / APIGen-MT** ([2406.18518](https://arxiv.org/abs/2406.18518), [2504.03601](https://arxiv.org/abs/2504.03601)) | Staged verification: format, execution, semantics; simulated agent and human interplay | A ready-made gate template |
| **Self-Rewarding LMs** (Yuan et al. 2024, [2401.10020](https://arxiv.org/abs/2401.10020)) | The model judges its own outputs for preference data | Caution: self-judging raises scores and locks in the judge's biases |
| **2025–26:** SynthLLM ([2503.19551](https://arxiv.org/abs/2503.19551)), BeyondWeb ([2508.10975](https://arxiv.org/abs/2508.10975)), Tulu 3 ([2411.15124](https://arxiv.org/abs/2411.15124)), Self-Challenging Agents ([2506.01716](https://arxiv.org/abs/2506.01716)), Kimi K2 ([2507.20534](https://arxiv.org/abs/2507.20534)) | Concept recombination through graphs; targeted rephrasing; persona and skill targeting with explicit decontamination; model-written tasks with verifiers; synthetic tool environments at scale | Gains plateau with volume; diversity and style matter more than generator size |

## Surveys worth keeping at hand

- *Best Practices and Lessons Learned on Synthetic Data* (Liu et al., Google DeepMind 2024, [2404.07503](https://arxiv.org/abs/2404.07503)): covers training and evaluation; names factuality, fidelity, and bias as the core risks.
- *On LLMs-Driven Synthetic Data Generation, Curation, and Evaluation* (Long et al. 2024, [2406.15126](https://arxiv.org/abs/2406.15126)): a stage taxonomy of generation, curation, and evaluation.
- *Quality, Diversity, and Complexity* (Havrilla et al. 2024, [2412.02980](https://arxiv.org/abs/2412.02980)): quality drives in-distribution results, diversity drives out-of-distribution results, and pipelines tend to trade diversity away.
- *On the Diversity of Synthetic Data* (Chen et al. 2024, [2410.15226](https://arxiv.org/abs/2410.15226)): a cluster-based diversity metric that tracks downstream value.
- *LLM Data Auditor* survey (Zhang et al., TMLR 2026, [2601.17717](https://arxiv.org/abs/2601.17717)): measure the data's intrinsic quality, not only downstream scores.

## Risks

**Collapse.** Training recursively on generated data loses the tails first, then the distribution narrows ("The Curse of Recursion", [2305.17493](https://arxiv.org/abs/2305.17493); *Nature* 2024). Accumulating real and synthetic data instead of replacing it keeps error bounded ("Is Model Collapse Inevitable?", [2404.01413](https://arxiv.org/abs/2404.01413); refined by [2410.16713](https://arxiv.org/abs/2410.16713)). A verifier helps in the short run but pulls outputs toward its own bias ([2510.16657](https://arxiv.org/abs/2510.16657)). Evals are not training data, but the same mechanism means a generator-only pipeline under-samples rare cases, which are the ones enterprise evals care about most.

**Homogeneity.** Lexical, syntactic, and semantic diversity all decline through recursive generation ([2311.09807](https://arxiv.org/abs/2311.09807)). "Artificial Hivemind" (Jiang et al., NeurIPS 2025 best paper, [2510.22954](https://arxiv.org/abs/2510.22954)) finds strong repetition within one model and even stronger sameness across models. Switching vendors does not buy variety.

## What this implies

1. Seed from real structure; generate detail. Keep the rationale for every gold answer.
2. Put diversity in a declared grid (persona, role, document type, audience, noise), not in temperature.
3. Use evolution operators to build difficulty ladders on purpose.
4. Write the source first and derive the question (backtranslation), so answers are checkable.
5. Gate in stages, cheapest first, and never let one fixed judge be the only filter.
6. Keep pools append-only with human-sourced anchors; retire, don't overwrite.
