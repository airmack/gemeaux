serve:
	python3 example_app.py

cert:
	openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout key.pem -subj "/CN=localhost" -newkey rsa:4096 -addext "subjectAltName = IP:127.0.0.1, DNS:localhost"

# DEV ONLY
lint: isort black flake8

isort:
	isort --profile black .
black:
	black .
flake8:
	flake8 .
