# Contributing

```bash
git clone <repo>
cd cancheria
python -m venv .venv
pip install -e ".[dev]"
pytest
```

Keep one logical change per PR, include tests, and never commit real customer data, WhatsApp profiles, cookies or secrets. New domain code must not import Playwright/OpenAI directly.
