"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AttentionApiError, fetchAttentionDetail, fetchAttentionQueue } from "@/lib/attention/client";
import { deterministicExplanation, displayDate, displayMoney, displayNumber, scoreLabel, scorePercent } from "@/lib/attention/presentation";
import type { AttentionDetail, AttentionPrediction, AttentionQueue } from "@/lib/attention/schema";
import AttentionSceneView from "./AttentionScene";
import EvidenceExplorer from "./EvidenceExplorer";
import styles from "./Attention.module.css";

export default function AttentionView() {
  const [queue, setQueue] = useState<AttentionQueue | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AttentionDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [planningOpen, setPlanningOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchAttentionQueue(controller.signal)
      .then((response) => setQueue(response))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setQueueError(error instanceof AttentionApiError ? error.message : "Attention could not be loaded.");
      });
    return () => controller.abort();
  }, [reloadToken]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    fetchAttentionDetail(selectedId, controller.signal)
      .then((response) => setDetail(response))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDetailError(error instanceof AttentionApiError ? error.message : "Prediction detail could not be loaded.");
      })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selectedId]);

  const select = useCallback((id: string | null, preservePlanning = false) => {
    setSelectedId(id);
    if (!preservePlanning) setPlanningOpen(false);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(id !== null);
  }, []);
  const step = useCallback((direction: 1 | -1) => {
    const predictions = queue?.predictions ?? [];
    if (!predictions.length) return;
    const index = predictions.findIndex((prediction) => prediction.prediction_id === selectedId);
    const next = index < 0 ? (direction > 0 ? 0 : predictions.length - 1) : (index + direction + predictions.length) % predictions.length;
    select(predictions[next].prediction_id, planningOpen);
  }, [planningOpen, queue, select, selectedId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (/INPUT|TEXTAREA|BUTTON/.test((event.target as HTMLElement).tagName)) return;
      if (["ArrowRight", "ArrowDown"].includes(event.key)) { event.preventDefault(); step(1); }
      if (["ArrowLeft", "ArrowUp"].includes(event.key)) { event.preventDefault(); step(-1); }
      if (event.key === "Escape") {
        if (planningOpen) setPlanningOpen(false);
        else select(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [planningOpen, select, step]);

  const selected = useMemo(() => queue?.predictions.find((prediction) => prediction.prediction_id === selectedId) ?? null, [queue, selectedId]);

  if (queueError) return <LoadState title="Attention release unavailable" message={queueError} action="Retry" onAction={() => { setQueue(null); setQueueError(null); setReloadToken((value) => value + 1); }} />;
  if (!queue) return <LoadState title="Loading Attention" message="Validating the current immutable prediction release…" />;
  if (!queue.predictions.length) return <LoadState title="No eligible predictions in this run." message={`Run ${queue.run.prediction_set_id.slice(0, 18)}… completed with no displayable candidates.`} />;

  if (planningOpen && selected) {
    return (
      <PlanningPane
        prediction={selected}
        detail={detail}
        loading={detailLoading}
        error={detailError}
        onBack={() => setPlanningOpen(false)}
        onStep={step}
        position={queue.predictions.findIndex((prediction) => prediction.prediction_id === selected.prediction_id) + 1}
        total={queue.predictions.length}
      />
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div><p className={styles.eyebrow}>Current prediction run</p><h1>Attention</h1></div>
        <div className={styles.runMeta}><span>Cutoff {new Date(queue.run.prediction_as_of).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}</span><span>{queue.run.metric_contract_version}</span></div>
      </header>
      <section className={styles.summary} aria-label="Attention run summary">
        <Summary label="Eligible candidates" value={String(queue.summary.eligible_candidate_count)} />
        <Summary label="Displayed predictions" value={String(queue.summary.displayed_prediction_count)} />
        <Summary label="Estimated lost units · 28 days" value={displayNumber(queue.summary.estimated_lost_units)} />
        <Summary label="Estimated lost sales · 28 days" value={displayMoney(queue.summary.estimated_lost_sales_amount)} />
      </section>
      <div className={styles.workspace}>
        <AttentionSceneView predictions={queue.predictions} selectedId={selectedId} hoveredId={hoveredId} onHover={setHoveredId} onSelect={select} />
        <aside className={styles.aside}>
          {selected ? (
            <PredictionCard prediction={selected} detail={detail} loading={detailLoading} error={detailError} onOpen={() => setPlanningOpen(true)} onStep={step} position={queue.predictions.findIndex((item) => item.prediction_id === selected.prediction_id) + 1} total={queue.predictions.length} />
          ) : <div className={styles.hint}>Select a point or ranked row to inspect its published scores and planning context. Use arrow keys to step through the immutable queue.</div>}
          <section className={styles.rankedList} aria-labelledby="ranked-title">
            <div className={styles.listHeader}><div><h2 id="ranked-title">Ranked by engine</h2><span>Impact · Reaction · Confidence</span></div></div>
            <div className={styles.listBody}>
              {queue.predictions.map((prediction) => (
                <button key={prediction.prediction_id} className={`${styles.row} ${selectedId === prediction.prediction_id ? styles.selectedRow : ""} ${hoveredId === prediction.prediction_id ? styles.hoveredRow : ""}`} onClick={() => select(prediction.prediction_id)} onPointerEnter={() => setHoveredId(prediction.prediction_id)} onPointerLeave={() => setHoveredId(null)}>
                  <span className={styles.rank}>{prediction.rank_position}</span>
                  <span className={styles.rowCopy}><strong>{prediction.identity.item_name}</strong><span>{prediction.identity.company_item_id} · {prediction.identity.store_name}</span><span>Out by {displayDate(prediction.predicted_oos_date)} · {displayNumber(prediction.estimated_lost_units)} estimated lost units</span></span>
                  <span className={styles.rankScore}>{scoreLabel(prediction.rank_score)}</span>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className={styles.summaryItem}><span>{label}</span><strong>{value}</strong></div>;
}

function Pager({ position, total, onStep }: { position: number; total: number; onStep: (direction: 1 | -1) => void }) {
  return <div className={styles.pager}><button aria-label="Previous prediction" onClick={() => onStep(-1)}>‹</button><span>{position} of {total}</span><button aria-label="Next prediction" onClick={() => onStep(1)}>›</button></div>;
}

function PredictionCard({ prediction, detail, loading, error, onOpen, onStep, position, total }: { prediction: AttentionPrediction; detail: AttentionDetail | null; loading: boolean; error: string | null; onOpen: () => void; onStep: (direction: 1 | -1) => void; position: number; total: number }) {
  return (
    <article className={styles.card}>
      <div className={styles.cardTop}><span>{prediction.identity.store_name} · {prediction.identity.source_location_id}</span><Pager position={position} total={total} onStep={onStep} /></div>
      <h2><span>{prediction.identity.company_item_id}</span>{prediction.identity.item_name} out of stock by <strong>{displayDate(prediction.predicted_oos_date)}</strong></h2>
      <div className={styles.meters}>
        <Meter label="Impact" score={prediction.impact_score} context={displayMoney(prediction.estimated_lost_sales_amount)} />
        <Meter label="Reaction" score={prediction.reaction_score} context={detail ? `${detail.prediction.action_slack_days}d slack` : "Published score"} />
        <Meter label="Confidence" score={prediction.prediction_confidence_score} context="Score · not probability" />
      </div>
      <div className={styles.cardFacts}><Fact label="Estimated lost units" value={displayNumber(prediction.estimated_lost_units)} /><Fact label="Rank score" value={scoreLabel(prediction.rank_score)} /></div>
      {error && <p className={styles.inlineError} role="alert">{error}</p>}
      <button className={styles.drillButton} disabled={loading || !detail} onClick={onOpen}><span>{loading ? "Loading planning context…" : "Open planning context"}</span><span>→</span></button>
    </article>
  );
}

function Meter({ label, score, context }: { label: string; score: string; context: string }) {
  return <div className={styles.meter}><span>{label}</span><div><i style={{ width: `${scorePercent(score)}%` }} /></div><strong>{scoreLabel(score)}</strong><small>{context}</small></div>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className={styles.fact}><span>{label}</span><strong>{value}</strong></div>;
}

function LoadState({ title, message, action, onAction }: { title: string; message: string; action?: string; onAction?: () => void }) {
  return <section className={styles.loadState} role="status"><p className={styles.eyebrow}>Attention</p><h1>{title}</h1><p>{message}</p>{action && onAction && <button className={styles.secondaryButton} onClick={onAction}>{action}</button>}</section>;
}

function PlanningPane({ prediction, detail, loading, error, onBack, onStep, position, total }: { prediction: AttentionPrediction; detail: AttentionDetail | null; loading: boolean; error: string | null; onBack: () => void; onStep: (direction: 1 | -1) => void; position: number; total: number }) {
  if (loading) return <LoadState title="Loading planning context" message="Validating the 28-day evidence trace…" />;
  if (error || !detail) return <LoadState title="Planning context unavailable" message={error ?? "The prediction detail is unavailable."} action="Back to queue" onAction={onBack} />;
  const p = detail.prediction;
  return (
    <div className={styles.page}>
      <header className={styles.detailHeader}>
        <div><button className={styles.backButton} onClick={onBack}>← Attention queue</button><p className={styles.eyebrow}>{prediction.identity.store_name} · {prediction.identity.company_item_id}</p><h1>{prediction.identity.item_name}</h1><p>Base path out of stock by <strong>{displayDate(p.predicted_oos_date)}</strong></p></div>
        <Pager position={position} total={total} onStep={onStep} />
      </header>
      <section className={styles.detailStats} aria-label="Prediction planning context">
        <Summary label="Starting on hand" value={displayNumber(p.starting_on_hand_units, 1)} />
        <Summary label="Estimated lost units · 28 days" value={displayNumber(p.estimated_lost_units)} />
        <Summary label="Estimated lost sales · 28 days" value={displayMoney(p.estimated_lost_sales_amount)} />
        <Summary label="Minimum reaction days" value={String(p.minimum_reaction_days)} />
        <Summary label="Action slack days" value={String(p.action_slack_days)} />
        <Summary label="Sensitivity span" value={p.oos_date_span_days === null ? "Open" : `${p.oos_date_span_days} days`} />
      </section>
      <section className={styles.contextGrid}>
        <article className={styles.panel}><div className={styles.panelHeader}><div><p className={styles.eyebrow}>Timing</p><h2>Depletion range</h2></div></div><dl className={styles.definitionList}><div><dt>Earliest · high demand</dt><dd>{displayDate(p.earliest_oos_date)}</dd></div><div><dt>Base path</dt><dd>{displayDate(p.predicted_oos_date)}</dd></div><div><dt>Latest · low demand</dt><dd>{displayDate(p.latest_oos_date)}</dd></div></dl></article>
        <article className={styles.panel}><div className={styles.panelHeader}><div><p className={styles.eyebrow}>Confidence components</p><h2>Published evidence quality</h2></div></div><dl className={styles.definitionList}><div><dt>Forecast quality</dt><dd>{scoreLabel(p.forecast_quality)}</dd></div><div><dt>Data completeness</dt><dd>{scoreLabel(p.data_completeness)}</dd></div><div><dt>Timing stability</dt><dd>{scoreLabel(p.timing_stability_score)}</dd></div><div><dt>Forecast WAPE</dt><dd>{p.forecast_wape === null ? "Unavailable" : displayNumber(String(Number(p.forecast_wape) * 100), 1) + "%"}</dd></div></dl></article>
        <article className={styles.panel}><div className={styles.panelHeader}><div><p className={styles.eyebrow}>Scheduled inbound</p><h2>Dated receipts in horizon</h2></div></div>{detail.scheduled_inbound.length ? <dl className={styles.definitionList}>{detail.scheduled_inbound.map((row) => <div key={row.expected_store_receipt_date}><dt>{displayDate(row.expected_store_receipt_date)}</dt><dd>{displayNumber(row.scheduled_inbound_units)} units</dd></div>)}</dl> : <p className={styles.mutedCopy}>No scheduled inbound appears in the published evidence trace.</p>}</article>
      </section>
      <EvidenceExplorer detail={detail} />
      <section className={styles.explanation}><p className={styles.eyebrow}>Deterministic explanation</p><p>{deterministicExplanation(detail)}</p></section>
      <section className={styles.lineage}><div><strong>Prediction set</strong><span>{detail.prediction.source_release_set_id}</span></div><div><strong>Metric contract</strong><span>{detail.prediction.metric_contract_version}</span></div><div><strong>Demand forecast</strong><span>{detail.prediction.demand_forecast_version}</span></div><div><strong>Inventory projection</strong><span>{detail.prediction.inventory_projection_version}</span></div><div><strong>Ranker</strong><span>{detail.prediction.ranker_version}</span></div><div><strong>Configuration</strong><span title={detail.prediction.configuration_hash}>{detail.prediction.configuration_hash.slice(0, 16)}…</span></div></section>
    </div>
  );
}
