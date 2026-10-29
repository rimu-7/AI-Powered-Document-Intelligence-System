# Evaluation

| File | Purpose |
|---|---|
| `dataset/` | Labeled dataset (37 files, all supported formats + corrupted files); `labels.json` holds the expected outcome of every file |
| `build_dataset.py` | Regenerates `dataset/` deterministically (`uv run python -m evaluation.build_dataset`) |
| `synthetic.py` | Invoice/register generator with ground truth (also used by tests) |
| `evaluate.py` | End-to-end evaluation through the API of a running stack (`make evaluate`) |
| `results/` | Measured reports (`evaluation-*.json/.md`, `benchmark-*.json`) |
