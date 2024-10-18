lint:
	poetry run isort --profile=black program_admin/ tests/
	poetry run black program_admin/ tests/
	poetry run pyright program_admin/ tests/
	poetry run pyflakes program_admin/ tests/

install:
	poetry install

test:
	poetry run pytest -rx
