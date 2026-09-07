import json
import logging
import os
from concurrent import futures

import grpc
import redis

import externalscaler_pb2 as pb
import externalscaler_pb2_grpc as pb_grpc
from estimators import build_estimator

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger("semantic-external-scaler")


def _meta(ref, key: str, default: str) -> str:
    return ref.scalerMetadata.get(key, default)


def _redis_client(ref):
    address = _meta(ref, "redisAddress", os.getenv("REDIS_ADDRESS", "redis:6379"))
    host, port = address.rsplit(":", 1)
    password = os.getenv("REDIS_PASSWORD") or None
    return redis.Redis(host=host, port=int(port), password=password, decode_responses=False)


class SemanticExternalScaler(pb_grpc.ExternalScalerServicer):
    def __init__(self):
        self._estimators = {}

    def _estimator(self, name: str):
        if name not in self._estimators:
            self._estimators[name] = build_estimator(name)
        return self._estimators[name]

    def IsActive(self, request, context):
        client = _redis_client(request)
        list_name = _meta(request, "listName", "work")
        length = client.llen(list_name)
        return pb.IsActiveResponse(result=length > 0)

    def StreamIsActive(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "Use the pull-based external scaler in this prototype")

    def GetMetricSpec(self, request, context):
        metric_name = _meta(request, "metricName", "semantic_work_backlog")
        target = float(_meta(request, "targetWork", "8.0"))
        return pb.GetMetricSpecResponse(
            metricSpecs=[pb.MetricSpec(metricName=metric_name, targetSizeFloat=target)]
        )

    def GetMetrics(self, request, context):
        ref = request.scaledObjectRef
        client = _redis_client(ref)
        list_name = _meta(ref, "listName", "work")
        sample_size = max(1, int(_meta(ref, "sampleSize", "64")))
        estimator_name = _meta(ref, "estimator", os.getenv("ESTIMATOR", "metadata"))
        metric_name = request.metricName or _meta(ref, "metricName", "semantic_work_backlog")

        queue_len = client.llen(list_name)
        if queue_len <= 0:
            total_work = 0.0
        else:
            n = min(sample_size, queue_len)
            raw = client.lrange(list_name, 0, n - 1)
            estimates = self._estimator(estimator_name).estimate(raw)
            mean_cost = sum(estimates) / len(estimates) if estimates else 0.0
            # Estimate total outstanding work from a bounded head sample.
            total_work = float(queue_len) * mean_cost

        LOG.info(json.dumps({
            "metric": metric_name,
            "queue_len": int(queue_len),
            "estimated_work_seconds": round(total_work, 3),
            "estimator": estimator_name,
        }))
        return pb.GetMetricsResponse(
            metricValues=[pb.MetricValue(metricName=metric_name, metricValueFloat=total_work)]
        )


def main():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pb_grpc.add_ExternalScalerServicer_to_server(SemanticExternalScaler(), server)
    port = os.getenv("PORT", "9090")
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    LOG.info("external scaler listening on %s", port)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
