# Contributing

Thanks for helping improve LocalRedact. Because redaction failures can expose
sensitive information, behavior changes need focused tests and conservative
defaults.

## Development setup

```bash
git clone https://github.com/1aifanatic/localredact.git
cd localredact
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Please use synthetic documents and invented identifiers in tests. Never commit
real personal, customer, medical, financial, or credential data.

Pull requests should explain the user-visible behavior, add regression coverage,
and document any new false-positive or false-negative boundary. By contributing,
you agree that your contribution is licensed under AGPL-3.0-only.

Report suspected vulnerabilities through GitHub's private vulnerability-reporting
flow described in [SECURITY.md](SECURITY.md).
