# Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -m "not live and not browser"
```

Legacy evals remain available through `python WPSetter.py --agentic-evals` after runtime dependencies are installed.
