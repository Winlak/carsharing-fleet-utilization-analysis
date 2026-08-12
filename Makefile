.PHONY: install lint test reproduce reproduce-check

install:
	python3 -m pip install --upgrade pip
	python3 -m pip install -r requirements.txt

lint:
	python3 -m ruff check .

test:
	python3 -m pytest -q

reproduce:
	python3 -m src.run_pipeline

reproduce-check: reproduce
	git diff --exit-code
	test -z "$$(git status --porcelain --untracked-files=all)"
