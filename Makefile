.PHONY: test build serve clean help superserve

superserve:
	@./superserve.sh

help:
	@echo "Available targets:"
	@echo "  make serve      - Build and run the application"
	@echo "  make superserve - Run server with auto-update from main branch"
	@echo "  make test       - Run all tests"
	@echo "  make build      - Build Docker images"
	@echo "  make clean      - Stop containers and remove database files"
	@echo "  make help       - Show this help message"

serve:
	docker-compose up --build

test: build
	docker-compose run --rm -e TESTING=1 web pytest

build:
	docker-compose build

clean:
	docker-compose down
	rm -rf data/*.db

