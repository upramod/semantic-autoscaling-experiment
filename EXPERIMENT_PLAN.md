# Experimental Plan

## Primary question

Does cost-aware queue scaling improve SLO attainment when message count is a poor proxy for outstanding service work?

## Policies

- B1: native queue count, six messages/replica.
- P1: native queue count plus semantic work metric, eight estimated service-seconds/replica.

Keep the native trigger enabled in P1. This tests semantic scaling as an additive control signal, not as a replacement for a mature queue-depth safeguard.

## Primary scenarios

1. Steady workload.
2. Composition shift at constant request rate.
3. Volume spike with stable composition.
4. Mixed volume and composition spike.

## Metrics

- P95 end-to-end latency.
- P99 end-to-end latency.
- fraction of requests above a 20 s SLO.
- mean queue delay.
- replica-seconds per completed request.
- maximum desired and available replicas.
- scaling lead time after the start of the middle-third perturbation.
- oscillation count, defined as direction changes in desired replica count after suppressing one-sample noise.
- external-scaler request latency and, for an LLM run, model latency/cost.

## Minimum evidence before journal submission

- 10 or more independent seeds per policy/scenario.
- Exact Kubernetes, KEDA, node, container resource, polling, and cooldown settings recorded.
- No concurrent unrelated workload on the test cluster.
- Baseline and semantic trials interleaved or randomized to reduce time-of-day/node drift.
- A separate experiment that injects estimator underestimation to test fail-safe behavior.
- If an LLM estimator is used, report the deterministic metadata estimator separately. Otherwise the paper cannot distinguish the value of semantic features from the value of the model itself.

## Claims that should not be made from this testbed alone

- production cost savings for a real organization.
- universal latency reduction.
- Azure Functions behavior unless the same experiment is separately reproduced there.
- superiority of an LLM over lightweight statistical or rule-based estimators without a direct comparison.
