.PHONY: build kind load keda deploy test zip
build:
	./scripts/build_images.sh
kind:
	./scripts/kind_create.sh
load:
	./scripts/kind_load_images.sh
keda:
	./scripts/install_keda.sh
deploy:
	./scripts/deploy.sh
test:
	python -m pytest -q tests
zip:
	cd .. && zip -r Semantic_Cost_Autoscaling_Prototype.zip Semantic_Cost_Autoscaling_Prototype -x '*/results/*' '*/__pycache__/*'
