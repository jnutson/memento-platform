"use client";

import { useEffect, useRef } from "react";
import { toWorld } from "@/lib/attention/presentation";
import type { AttentionScene } from "@/lib/attention/scene";
import type { AttentionPrediction } from "@/lib/attention/schema";
import styles from "./Attention.module.css";

type Props = {
  predictions: AttentionPrediction[];
  selectedId: string | null;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  onSelect: (id: string | null) => void;
};

export default function AttentionSceneView({ predictions, selectedId, hoveredId, onHover, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<AttentionScene | null>(null);
  const callbacks = useRef({ onHover, onSelect });
  const initial = useRef({ predictions, selectedId, hoveredId });

  useEffect(() => { callbacks.current = { onHover, onSelect }; }, [onHover, onSelect]);

  useEffect(() => {
    let active = true;
    let mountedScene: AttentionScene | null = null;
    void import("@/lib/attention/scene").then(({ createScene }) => {
      if (!active || !host.current) return;
      mountedScene = createScene(host.current, {
        onHover: (id) => callbacks.current.onHover(id),
        onSelect: (id) => callbacks.current.onSelect(id),
      });
      mountedScene.setItems(initial.current.predictions.map((prediction) => ({
        id: prediction.prediction_id,
        title: `${prediction.identity.item_name} · out by ${prediction.predicted_oos_date}`,
        world: toWorld(prediction),
      })));
      mountedScene.focus(initial.current.selectedId);
      mountedScene.setHover(initial.current.hoveredId);
      scene.current = mountedScene;
    });
    return () => { active = false; mountedScene?.dispose(); scene.current = null; };
  }, []);

  useEffect(() => {
    scene.current?.setItems(predictions.map((prediction) => ({
      id: prediction.prediction_id,
      title: `${prediction.identity.item_name} · out by ${prediction.predicted_oos_date}`,
      world: toWorld(prediction),
    })));
  }, [predictions]);
  useEffect(() => { scene.current?.focus(selectedId); }, [selectedId]);
  useEffect(() => { scene.current?.setHover(hoveredId); }, [hoveredId]);

  return (
    <section className={styles.stage} aria-label="Interactive Impact, Reaction, and Confidence score scene">
      <div ref={host} className={styles.sceneHost} data-testid="attention-scene" />
      <button className={styles.resetButton} onClick={() => scene.current?.reset()}>Reset view</button>
      <p className={styles.sceneHelp}>Drag to rotate · scroll to zoom · select a point or ranked row</p>
    </section>
  );
}
