.PHONY: mock-up mock-down db-schema test gateway-up stack-up stack-down

mock-up:
	docker compose up --build -d bank ledger

mock-down:
	docker compose down

db-schema:
	psql $$DATABASE_URL -f db/schema.sql

test:
	@test -d .venv || python3 -m venv .venv
	.venv/bin/pip install -q -r gerald-gateway/requirements-test.txt
	PYTHONPATH=gerald-gateway DATABASE_URL=sqlite+pysqlite:///:memory: .venv/bin/pytest -q

gateway-up: mock-up
	docker compose up --build -d postgres gateway
	@echo "Waiting for postgres..." && sleep 4
	docker compose exec -T postgres psql -U postgres -d gerald -f - < db/schema.sql || true

stack-up:
	docker compose up --build -d
	@echo "Waiting for services..." && sleep 5
	cat db/schema.sql | docker compose exec -T postgres psql -U postgres -d gerald

stack-down:
	docker compose down

stack-rebuild:
	docker compose down
	docker compose up --build -d
	@echo "Waiting for services..." && sleep 8
	cat db/schema.sql | docker compose exec -T postgres psql -U postgres -d gerald 2>/dev/null || true

smoke:
	@echo "=== Bank stub ==="
	curl -sf http://localhost:8001/health
	@echo ""
	@echo "=== Bank user_good tx count ==="
	curl -sf "http://localhost:8001/bank/transactions?user_id=user_good" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['transactions']))"
	@echo "=== Gateway health ==="
	curl -sf http://localhost:8080/health
	@echo ""
	@echo "=== Decision user_good ==="
	curl -sf -X POST http://localhost:8080/v1/decision -H "Content-Type: application/json" -d '{"user_id":"user_good","amount_cents_requested":40000}'
	@echo ""
