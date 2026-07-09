"""Price scanner package.

Periodically checks e-commerce sites for insumo prices, records history in
Precos_Observados, and notifies via Telegram when an offer meets one of the
severity rules (forte/boa/alvo). Config lives in Scanner_Alertas.

Entrypoints:
- `bot/scanner/runner.py` — cron entrypoint (GitHub Actions).
- `bot/scanner/heartbeat.py` — daily liveness check.
"""
