# Configuration

Secrets and admin identities belong in `.env`. Business defaults remain in `src/cancheria/config/legacy_config.py` during the compatibility phase. `examples/config.example.yaml` documents the intended future data-driven shape.


## OpenAI API key in desktop installations

The public project contains an empty `OPENAI_API_KEY`. A non-technical user can open `configurador_cancheria.py`, paste their own key and press **Guardar config.py**. The configurator writes the value into the local editable configuration and CANCHERIA loads it on the next start. `OPENAI_API_KEY` from the environment remains an optional override. Do not commit the locally configured key to a public repository.
