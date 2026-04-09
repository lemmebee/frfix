run:
	.venv/bin/pip install -e . -q && .venv/bin/frfix

debug:
	.venv/bin/pip install -e . -q && .venv/bin/frfix --debug
