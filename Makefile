.PHONY: test build run clean

test:
	docker-compose run --rm web pytest

build:
	docker-compose build

run:
	docker-compose up

clean:
	docker-compose down
	rm -rf data/*.db

