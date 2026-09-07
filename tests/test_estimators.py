import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scaler"))
from estimators import MetadataEstimator, metadata_cost


def test_heavy_job_costs_more_than_light_job():
    light = {"kind": "route", "size_kb": 10}
    heavy = {"kind": "doc", "size_kb": 500}
    assert metadata_cost(heavy) > metadata_cost(light)


def test_batch_preserves_length_and_order():
    msgs = [
        json.dumps({"kind": "route", "size_kb": 10}),
        json.dumps({"kind": "doc", "size_kb": 100}),
    ]
    values = MetadataEstimator().estimate(msgs)
    assert len(values) == 2
    assert values[1] > values[0]
