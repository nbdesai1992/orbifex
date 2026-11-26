# Changelog

Entries are dated by commit and listed newest first. Run counts come from the JSONL files under `experiments/results/`, and the other figures come from the commit messages and the paper.

## 2026-11-26

The repository became public, and the README was rebuilt around what the pilot found.

- The README now opens with the result and one figure, `docs/accuracy-by-size.svg`, drawn from the run records by `scripts/make_readme_figure.py`.
- The September design document moved from the README to `docs/design.md`.
- `scripts/reproduce.sh` regenerates the seed-7 dataset, compares it with the published archive and prints the results from the records. The regenerated tree is file for file identical to `cpa-solo-harbor-v2.tar.gz`, with 2,256 files and tree sha256 `25228b794204f9e84216952ec6fc75b49d4a405bce27d883177a9876fd5f946f`.
- `scripts/results_table.py` prints the README's tables and headline numbers from the JSONL files, and new tests fail if the README, the figure and the records disagree.
- The README states both sets of reading-policy rates. `ladder.json` holds them over all 47 questions of a size, and the paper quotes them over the 39 lookup questions.
- `experiments/claude_pilot.py` now defaults to the full model ID `claude-haiku-5-5`. Every earlier run passed the alias `haiku`, which resolved to that model.
- `paper/make_figures.py` also writes the paper's two data figures as SVG under `docs/`. The PDFs are unchanged.
- `CITATION.cff` and this changelog were added.
- Several claims in the README and the paper were narrowed after an independent recheck against the run records, because they said more than the records support. The numbers did not change.
  - The 8 late-payer misses are no longer said to have one cause. They gave the answer the stale invoicing export implies and deleting the export removed them, and the four-source version, which had no export, had already given the same wrong list in 2 of its 12 late-payer runs, because the invoices and most tracker rows carry the original due dates too.
  - There are two late-payer sweep questions, one for April with 5 misses and one for May with 3, and the text now says so wherever it said one question.
  - The paper no longer says the wrong answers were the cheaper ones. The pooled gap came from which sizes the runs fall in, and the paper now gives the means per size.
  - The 20 of 20 correct runs on one invoice's final due date now carry their exposure. Only 7 of those runs faced an export with a different date, and 10 had no export.
  - The Fisher test and the Wilson interval now sit beside a note that the runs are repeats of a few questions in one generated workspace and are not independent draws.
  - The paper's drawing of the build-context fault showed a timestamp of 21:37:00 that was never observed. It now shows 21:37:51, the stamp the key files of the first three sizes carry in the first archive.
- `scripts/results_table.py --facts` now prints the counts behind the first four of these. The two that depend on the generated files need `--build`, and the tests check the ones that need only the run records.

## 2026-11-25

- The README's status line and links were updated for the eight-source version, and the package version was set to 0.2.0 to match the engine.

## 2026-11-17

The workspace gained five third-party app sources, and the pilot was rerun on the new version.

- The generator now writes exports from a Slack workspace, a bank, an invoicing app, a time tracker and a retailer's order history beside the persona's own mail, calendar and drive. The invoicing app is right about totals and keeps each invoice's original due date, because an extension agreed over email never reaches it.
- Retailer orders added six questions per size, for 47 per size and 188 in all. The 164 earlier questions kept their wording and answers. The suite grew to 14 tests.
- On the eight-source version `claude-haiku-5-5` answered 242 of 252 runs correctly. The two late-payer sweep questions produced 8 of the 10 misses, and each equals the wrong answer computed from original due dates.
- An ablation deleted the invoicing export at the two largest sizes, and the same questions went from 4 of 12 runs correct to 12 of 12.
- The paper and its figures were updated for both.

## 2026-11-16

A fault in the published archive was found by running it, and the export was changed to prevent it.

- Run from an unpacked archive, the reference solver wrote the right answer and still scored zero on 31 of 105 tasks. Docker's builder had reused a same-named file from another task's build context, because the path, size and timestamp matched, so those tasks were graded with another task's answer key.
- `world.<hash>.tar.gz` and `gold.<hash>.json` now carry a hash of their content in their names, the verifier refuses a key that does not match its name, and two tests cover the rule.
- The preprint was added under `paper/`, with two data figures drawn from the pilot records and two diagrams.

## 2026-11-15

The first engine and the first pilot.

- Engine version 0.1.0 turned a persona pack into a seeded table of facts, rendered it to mail, a calendar, a drive and chat at four sizes, built questions from their answers, required a second solver to recover every answer from the files, and exported each question as a Harbor task with a separate verifier. It shipped two persona packs, eight tests and the pilot runner.
- On this four-source version `claude-haiku-5-5` answered 210 of 212 runs correctly, 140 of 140 on lookup questions and 70 of 72 on sweep questions. Both misses were on the April late-payer sweep question.

## 2026-09-27

The design.

- The README was written as the design document, with research notes and a bibliography under `research/`.
- The design added the premise that an evaluation item is easier to build backwards from its answer than to solve blind, with the limits of that premise.
- The components, the checks for each layer and three ways to start a world were set out.
- The name Orbifex was fixed, and three diagrams were added under `docs/`.

That document is now [`docs/design.md`](docs/design.md).
