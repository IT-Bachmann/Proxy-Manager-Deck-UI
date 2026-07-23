# Contributing to ProxyManagerDeck2

Thank you for improving ProxyManagerDeck2.

## Development workflow

1. Fork the repository and create a focused branch.
2. Keep changes small and avoid unrelated formatting rewrites.
3. Never commit credentials, databases, certificates or generated configuration.
4. Run the syntax checks and Docker builds before opening a pull request.
5. Describe the motivation, behavior change, tests and security implications.

## Local checks

```bash
python -m py_compile server.py
node --check public/app.js
node --check demo/demo.js
node --check demo/providers.js
node --check demo/notifications.js
node --check demo/theme.js
docker compose config
docker compose build
```

## Pull requests

Changes affecting authentication, secret storage, ACME execution, Nginx generation or subprocess invocation require explicit security notes and tests. New DNS providers must document required credentials without logging or returning their values.

By submitting a contribution, you agree that it is licensed under the MIT License.
