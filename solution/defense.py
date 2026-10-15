"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    batch_id = payload.get("batch_id")
    prof = ctx.tools.batch_profile(batch_id)
    if "error" in prof:
        return Verdict(alert=False, pillar="checks")

    # Volume checks
    row_count = prof.get("row_count", 0)
    if row_count < ctx.baseline["row_count_min"] or row_count > ctx.baseline["row_count_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"row_count {row_count} out of bounds")

    # Null rate checks
    null_rate_customer = prof.get("null_rate", {}).get("customer_id", 0.0)
    if null_rate_customer > ctx.baseline["null_rate_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"null_rate_customer_id {null_rate_customer} > max")

    # Distribution checks (amount mean)
    mean_amount = prof.get("mean_amount", 0.0)
    if mean_amount < ctx.baseline["mean_amount_min"] or mean_amount > ctx.baseline["mean_amount_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"mean_amount {mean_amount} out of bounds")

    # Freshness / staleness checks
    staleness_min = prof.get("staleness_min", 0.0)
    if staleness_min > ctx.baseline["staleness_min_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"staleness_min {staleness_min} > max")

    return Verdict(alert=False, pillar="checks")


def check_contract_checkpoint(payload, ctx):
    contract_id = payload.get("contract_id")
    checkpoint_batch_id = payload.get("checkpoint_batch_id")
    diff = ctx.tools.contract_diff(contract_id, checkpoint_batch_id)
    if "error" in diff:
        return Verdict(alert=False, pillar="contracts")

    violations = diff.get("violations", [])
    if violations:
        return Verdict(alert=True, pillar="contracts", reason=f"violations: {violations}")

    freshness_delay = diff.get("freshness_delay_min", 0.0)
    if freshness_delay > ctx.baseline["freshness_delay_max_min"]:
        return Verdict(alert=True, pillar="contracts", reason=f"freshness_delay {freshness_delay} > max")

    return Verdict(alert=False, pillar="contracts")


def check_lineage_run(payload, ctx):
    run_id = payload.get("run_id")
    slice_data = ctx.tools.lineage_graph_slice(run_id)
    if "error" in slice_data:
        return Verdict(alert=False, pillar="lineage")

    duration_ms = slice_data.get("duration_ms", 0.0)
    if duration_ms > ctx.baseline["lineage_duration_ms_max"]:
        return Verdict(alert=True, pillar="lineage", reason=f"duration_ms {duration_ms} > max")

    actual_downstream_count = slice_data.get("actual_downstream_count", 1)
    if actual_downstream_count <= 0:
        return Verdict(alert=True, pillar="lineage", reason="orphan output: actual_downstream_count <= 0")

    actual_upstream = slice_data.get("actual_upstream", [])
    if len(actual_upstream) < 2 or "raw.orders" not in actual_upstream or "raw.customers" not in actual_upstream:
        return Verdict(alert=True, pillar="lineage", reason=f"missing upstream: {actual_upstream}")

    return Verdict(alert=False, pillar="lineage")


def check_feature_materialization(payload, ctx):
    ref = payload.get("batch_id")
    drift = ctx.tools.feature_drift(payload.get("feature_view"), ref)
    if "error" in drift:
        return Verdict(alert=False, pillar="ai_infra")

    shift_sigma = drift.get("mean_shift_sigma", 0.0)
    # Use 0.70 to avoid false positives on clean stream variance (up to 0.47)
    # while reliably catching subtle drift (>0.95) and obvious drift (>10.0)
    if shift_sigma > 0.70:
        return Verdict(alert=True, pillar="ai_infra", reason=f"mean_shift_sigma {shift_sigma} > 0.70")

    return Verdict(alert=False, pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    ref = payload.get("chunk_batch_id")
    drift = ctx.tools.embedding_drift(payload.get("corpus"), ref)
    if "error" in drift:
        return Verdict(alert=False, pillar="ai_infra")

    centroid_shift = drift.get("centroid_shift", 0.0)
    # Threshold tuned from 0.0435 to 0.039 to capture subtle centroid drift
    if centroid_shift > 0.039:
        return Verdict(alert=True, pillar="ai_infra", reason=f"centroid_shift {centroid_shift} > 0.039")

    avg_doc_age_days = drift.get("avg_doc_age_days", 0.0)
    # Threshold tuned from 49.8 to 45.0 to catch subtle corpus staleness
    if avg_doc_age_days > 45.0:
        return Verdict(alert=True, pillar="ai_infra", reason=f"avg_doc_age_days {avg_doc_age_days} > 45.0")

    return Verdict(alert=False, pillar="ai_infra")
