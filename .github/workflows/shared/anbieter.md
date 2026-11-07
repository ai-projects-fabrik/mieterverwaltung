---
# Anbieter-Vorlage T2: Codex mit DeepSeek Flash. Laufzeit belegt im MWST-Pilot (2026-10-16).
# Einsatz: nach .github/workflows/shared/anbieter.md kopieren, dann gh aw compile.
# Secret im Projekt: DEEPSEEK_API_KEY (eigener Key mit Limit). Nur fuer oeffentlich-taugliche Daten.
# Beide Key-Namen zeigen bewusst auf dasselbe Secret (Codex liest CODEX_API_KEY zuerst).
engine:
  id: codex
  model: deepseek-flash
  env:
    OPENAI_BASE_URL: https://api.deepseek.com
    OPENAI_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    CODEX_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
  config: |
    web_search = "disabled"
    model_reasoning_summary = "none"
    model_context_window = 200000
models:
  providers:
    openai:
      models:
        deepseek-flash:
          cost:
            input: "3e-07"
            output: "1.2e-06"
            cache_read: "6e-09"
network:
  allowed:
    - api.deepseek.com
---
