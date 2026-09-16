run:
	.venv/bin/pip install -e . -q && .venv/bin/frfix

debug:
	.venv/bin/pip install -e . -q && .venv/bin/frfix --debug

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/python -m ruff check .

check: lint test
