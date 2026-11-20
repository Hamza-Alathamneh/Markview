# Bundled Crossnote engine

Source: the Crossnote distribution packaged in
[Markdown Preview Enhanced 0.8.40](https://github.com/shd101wyy/vscode-markdown-preview-enhanced).
Crossnote is developed at <https://github.com/shd101wyy/crossnote>.

The engine is copied locally so Markview does not depend on a VS Code installation.
The adapter exposes four existing internal exports and removes the CLI autorun;
the rendering implementation is unchanged. The pinned source and resulting hashes
are recorded in `PROVENANCE.json`. Reproduce with `../../vendor_crossnote.py`.

The upstream NCSA license is preserved in `LICENSE.md`. Bundled dependency license
notices remain embedded in `engine.cjs` and the copied assets. Asset versions are
listed in `assets/dependencies/README.md`. Keep these notices when redistributing.

External tool integrations and optional WASM/TeX engines are not supplied by this
adapter. The supported renderer uses markdown-it, KaTeX, Mermaid, and Graphviz.
