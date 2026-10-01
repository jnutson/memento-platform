"use client";

import { useMemo, useState } from "react";
import { displayDate, displayNumber } from "@/lib/attention/presentation";
import type { AttentionDetail, EvidenceRow } from "@/lib/attention/schema";
import styles from "./Attention.module.css";

const WIDTH = 980;
const HEIGHT = 310;
const LEFT = 58;
const RIGHT = 18;
const TOP = 24;
const BOTTOM = 42;
const COLORS = { low: "#79aef2", base: "#0a4fb0", high: "#082f6d" } as const;

type PathName = keyof typeof COLORS;

function linePath(rows: EvidenceRow[], xAt: (index: number) => number, yAt: (value: number) => number): string {
  return rows.map((row, index) => `${index ? "L" : "M"}${xAt(index).toFixed(1)},${yAt(Number(row.projected_ending_on_hand_units)).toFixed(1)}`).join(" ");
}

export default function EvidenceExplorer({ detail }: { detail: AttentionDetail }) {
  const [visible, setVisible] = useState<Record<PathName, boolean>>({ low: true, base: true, high: true });
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const paths = useMemo(() => {
    const grouped = { low: [] as EvidenceRow[], base: [] as EvidenceRow[], high: [] as EvidenceRow[] };
    for (const row of detail.evidence) grouped[row.path].push(row);
    for (const name of Object.keys(grouped) as PathName[]) grouped[name].sort((a, b) => a.projection_date.localeCompare(b.projection_date));
    return grouped;
  }, [detail.evidence]);
  const base = paths.base;
  const maximum = Math.max(1, ...detail.evidence.flatMap((row) => [
    Number(row.projected_ending_on_hand_units), Number(row.demand_units),
    Number(row.scheduled_inbound_units), Number(row.lost_units),
  ]));
  const xAt = (index: number) => LEFT + (index / 27) * (WIDTH - LEFT - RIGHT);
  const yAt = (value: number) => TOP + (1 - value / maximum) * (HEIGHT - TOP - BOTTOM);
  const activeIndex = hoverIndex ?? 0;
  const active = base[activeIndex];

  return (
    <section className={styles.panel} aria-labelledby="evidence-title">
      <div className={styles.panelHeader}>
        <div>
          <p className={styles.eyebrow}>Calculation evidence</p>
          <h2 id="evidence-title">Daily inventory paths</h2>
        </div>
        <span className={styles.panelNote}>28 days · units · fixed sensitivity paths</span>
      </div>
      <div className={styles.legend} aria-label="Path visibility">
        {(Object.keys(COLORS) as PathName[]).map((path) => (
          <button key={path} aria-pressed={visible[path]} onClick={() => setVisible((current) => ({ ...current, [path]: !current[path] }))}>
            <i style={{ background: COLORS[path], opacity: visible[path] ? 1 : .25 }} />{path[0].toUpperCase() + path.slice(1)} path
          </button>
        ))}
        <span className={styles.readout}>
          {displayDate(active.projection_date)} · base ending on hand <b>{displayNumber(active.projected_ending_on_hand_units, 1)}</b> · demand <b>{displayNumber(active.demand_units, 1)}</b> · inbound <b>{displayNumber(active.scheduled_inbound_units, 1)}</b> · lost <b>{displayNumber(active.lost_units, 1)}</b>
        </span>
      </div>
      <svg
        className={styles.evidenceChart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Low, base, and high projected ending on hand with base demand, scheduled inbound, and lost units"
        onPointerMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const x = ((event.clientX - bounds.left) / bounds.width) * WIDTH;
          setHoverIndex(Math.max(0, Math.min(27, Math.round(((x - LEFT) / (WIDTH - LEFT - RIGHT)) * 27))));
        }}
        onPointerLeave={() => setHoverIndex(null)}
      >
        {[0, .25, .5, .75, 1].map((ratio) => {
          const value = maximum * ratio;
          return <g key={ratio}><line x1={LEFT} x2={WIDTH - RIGHT} y1={yAt(value)} y2={yAt(value)} stroke="#ececef" /><text x={LEFT - 9} y={yAt(value) + 4} textAnchor="end" className={styles.svgLabel}>{displayNumber(String(value), 0)}</text></g>;
        })}
        {base.map((row, index) => {
          const width = Math.max(3, (WIDTH - LEFT - RIGHT) / 28 * .32);
          const inbound = Number(row.scheduled_inbound_units);
          const lost = Number(row.lost_units);
          return <g key={row.projection_date}>{inbound > 0 && <rect x={xAt(index) - width - 1} y={yAt(inbound)} width={width} height={HEIGHT - BOTTOM - yAt(inbound)} fill="#b8d6ff" />}{lost > 0 && <rect x={xAt(index) + 1} y={yAt(lost)} width={width} height={HEIGHT - BOTTOM - yAt(lost)} fill="rgba(201,55,60,.28)" />}</g>;
        })}
        <path d={base.map((row, index) => `${index ? "L" : "M"}${xAt(index).toFixed(1)},${yAt(Number(row.demand_units)).toFixed(1)}`).join(" ")} fill="none" stroke="#8e8e93" strokeDasharray="5 4" strokeWidth="1.5" />
        {(Object.keys(paths) as PathName[]).map((path) => visible[path] && <path key={path} d={linePath(paths[path], xAt, yAt)} fill="none" stroke={COLORS[path]} strokeWidth={path === "base" ? 2.7 : 1.8} strokeLinejoin="round" />)}
        <line x1={LEFT} x2={WIDTH - RIGHT} y1={HEIGHT - BOTTOM} y2={HEIGHT - BOTTOM} stroke="#c7c7cc" />
        {[0, 6, 13, 20, 27].map((index) => <text key={index} x={xAt(index)} y={HEIGHT - 17} textAnchor="middle" className={styles.svgLabel}>{base[index].projection_date.slice(5)}</text>)}
        {hoverIndex !== null && <><line x1={xAt(hoverIndex)} x2={xAt(hoverIndex)} y1={TOP} y2={HEIGHT - BOTTOM} stroke="#aeaeb2" /><circle cx={xAt(hoverIndex)} cy={yAt(Number(base[hoverIndex].projected_ending_on_hand_units))} r="4" fill="#fff" stroke={COLORS.base} strokeWidth="2" /></>}
      </svg>
      <div className={styles.chartKey}><span><i className={styles.demandLine} />Base demand</span><span><i style={{ background: "#b8d6ff" }} />Scheduled inbound</span><span><i style={{ background: "rgba(201,55,60,.28)" }} />Base lost units</span></div>
      <div className={styles.tableScroll}>
        <div className={styles.evidenceTable} role="table" aria-label="Daily calculation evidence">
          <EvidenceTableRow label="Date" values={base.map((row) => row.projection_date.slice(5))} hoverIndex={hoverIndex} onHover={setHoverIndex} header />
          <EvidenceTableRow label="Low ending OH" values={paths.low.map((row) => displayNumber(row.projected_ending_on_hand_units, 1))} hoverIndex={hoverIndex} onHover={setHoverIndex} />
          <EvidenceTableRow label="Base ending OH" values={base.map((row) => displayNumber(row.projected_ending_on_hand_units, 1))} hoverIndex={hoverIndex} onHover={setHoverIndex} />
          <EvidenceTableRow label="High ending OH" values={paths.high.map((row) => displayNumber(row.projected_ending_on_hand_units, 1))} hoverIndex={hoverIndex} onHover={setHoverIndex} />
          <EvidenceTableRow label="Base demand" values={base.map((row) => displayNumber(row.demand_units, 1))} hoverIndex={hoverIndex} onHover={setHoverIndex} />
          <EvidenceTableRow label="Scheduled inbound" values={base.map((row) => displayNumber(row.scheduled_inbound_units, 1))} hoverIndex={hoverIndex} onHover={setHoverIndex} />
          <EvidenceTableRow label="Base lost units" values={base.map((row) => displayNumber(row.lost_units, 1))} hoverIndex={hoverIndex} onHover={setHoverIndex} />
        </div>
      </div>
    </section>
  );
}

function EvidenceTableRow({ label, values, hoverIndex, onHover, header = false }: { label: string; values: string[]; hoverIndex: number | null; onHover: (value: number | null) => void; header?: boolean }) {
  return (
    <div className={`${styles.tableRow} ${header ? styles.tableHeader : ""}`} role="row">
      <span className={styles.tableLabel} role={header ? "columnheader" : "rowheader"}>{label}</span>
      {values.map((value, index) => <span key={index} role="cell" className={hoverIndex === index ? styles.hoverCell : ""} onPointerEnter={() => onHover(index)} onPointerLeave={() => onHover(null)}>{value}</span>)}
    </div>
  );
}
