
dev:
\tuvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
\tpytest -q

fmt:
\truff check . --fix

up:
\tdocker compose up --build

down:
\tdocker compose down -v

