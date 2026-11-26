# Paper

`orbifex.pdf` is built from `orbifex.tex` with the NeurIPS 2025 style file, used for layout only
(the `preprint` option). The report has not been submitted to or reviewed by NeurIPS.

    python paper/make_figures.py      # needs matplotlib; reads experiments/results/
    cd paper && tectonic orbifex.tex  # any XeTeX-based engine with fontspec works

Every number in the paper comes from `experiments/results/cpa-solo-seed7-v2/` (the eight-source version),
`experiments/results/cpa-solo-seed7/` (the earlier four-source version) or the gate reports in those folders. The two data figures are drawn by `make_figures.py`, and the two diagrams are TikZ.
