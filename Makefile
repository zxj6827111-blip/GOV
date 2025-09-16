.PHONY: dev backend frontend lint typecheck unit e2e test install

backend:
	uvicorn api.main:app --reload

frontend:
	npm --prefix app run dev

dev:
	bash -c 'trap "kill 0" EXIT; npm --prefix app run dev & uvicorn api.main:app --reload'

lint:
	ruff check .

typecheck:
	mypy api engine tests

unit:
	pytest

e2e:
	@if [ -x app/node_modules/.bin/playwright ]; then \
		npm --prefix app run test:e2e; \
	else \
		echo "Playwright not installed; skipping e2e tests."; \
	fi

install:
	pip install -r api/requirements.txt
	npm --prefix app install
	npx --yes playwright install --with-deps chromium

test: lint typecheck unit e2e
