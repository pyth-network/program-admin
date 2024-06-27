lint:
	poetry run isort --profile=black program_admin/ tests/
	poetry run black program_admin/ tests/
	poetry run mypy program_admin/ tests/
	poetry run pylint program_admin/ tests/

install:
	poetry install

test:
	poetry run pytest
