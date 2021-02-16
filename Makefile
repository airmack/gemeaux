serve:
	python3 example_app.py

cert:
	./cert.sh

# DEV ONLY
lint: isort black flake8

isort:
	isort --profile black .
black:
	black .
flake8:
	flake8 .
