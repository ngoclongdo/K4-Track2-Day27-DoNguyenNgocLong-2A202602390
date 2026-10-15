# Reflection (≤1 page)

**Student:** Đỗ Nguyễn Ngọc Long (MSSV: 2A202602390)

## 1. Which fault types were hardest to catch, and why?

1. **Subtle distribution & volume shifts (`distribution_shift`, `volume_drop`, `null_spike`):**
   - Obvious faults (e.g., schema breaks, type errors, missing upstream dependencies, or 15σ feature shifts) are deterministic and cleanly separated from normal traffic.
   - In contrast, subtle faults in `data_batch` (such as `volume_drop` at 469–474 rows vs. clean mean 500.0, or subtle `distribution_shift` with mean amount at 85.7–88.9 vs. clean mean 82.8) sit within the 1.5σ–2.5σ envelope of natural stream variance.
   - Lowering static thresholds to capture these subtle shifts introduces substantial risk of false positives. Since the scoring metric severely penalizes false alarms ($-0.3 \cdot \text{FPR}$ vs. $+0.5 \cdot \text{TPR}$), a single false alarm on a clean event erodes more points than missing an ambiguous subtle fault gains.

2. **Subtle runtime anomalies in lineage (`lineage_duration_ms`):**
   - Clean pipeline execution durations exhibit non-trivial variance (ranging from 3470 ms to 4805 ms with a standard deviation of ~270 ms).
   - Subtle runtime faults inject durations around 4480–4740 ms, which fall directly inside the empirical range of observed clean executions. Without historical job-level context, distinguishing a genuine minor delay from transient infrastructure jitter on a single event is fundamentally ambiguous.

3. **Subtle corpus staleness & embedding drift:**
   - Calibrating the thresholds (e.g., tightening `centroid_shift` from 0.0435 to 0.039 and `avg_doc_age_days` from 49.8 to 45.0) allowed catching public subtle faults cleanly. However, in the private phase, very subtle staleness (e.g., doc age 35–37 days vs. clean max 41.0) remains tightly intertwined with clean batches.

---

## 2. What would you change about your cost/coverage tradeoff, if you had another pass?

1. **Dynamic / Multi-stage Probing:**
   - In the current single-pass architecture, we issue one metered RPC per event, expending 180.0 credits in practice, 240.0 in public, and 300.0 in private (well within the private budget of 320.0, yielding zero cost overage penalty).
   - If granted another pass, we could implement a multi-stage triage: for low-risk events or producers with an immaculate track record stored in `ctx.state`, we could sample intermittently or defer expensive 2.0-credit tools (`feature_drift`, `embedding_drift`), allocating saved budget to higher-variance event types.

2. **Online Sequential State Tracking (CUSUM / EWMA):**
   - Currently, each decision is evaluated predominantly on the instantaneous batch metrics.
   - Using `ctx.state` (which has zero RPC cost), we could maintain an online Exponentially Weighted Moving Average (EWMA) or Cumulative Sum (CUSUM) detector across sequential batches. This would allow detecting persistent, low-amplitude shifts (e.g., five consecutive batches slightly below mean volume) with high confidence, turning elusive subtle faults into statistically robust detections without triggering false positives.
