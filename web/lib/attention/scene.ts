import * as THREE from "three";

export type SceneItem = { id: string; title: string; world: [number, number, number] };
export type SceneCallbacks = {
  onHover?: (id: string | null) => void;
  onSelect?: (id: string | null) => void;
};
export type AttentionScene = {
  setItems(items: SceneItem[]): void;
  focus(id: string | null): void;
  setHover(id: string | null): void;
  reset(): void;
  dispose(): void;
};

const SIZE = 1.55;
const HOME = { yaw: 0.72, pitch: 0.42, distance: 8.4 };

export function createScene(host: HTMLElement, callbacks: SceneCallbacks = {}): AttentionScene {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xffffff);
  scene.fog = new THREE.Fog(0xffffff, 8, 15);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 40);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.domElement.style.cssText = "position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:grab";
  host.appendChild(renderer.domElement);

  const overlay = document.createElement("div");
  overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;font:600 12px Inter,system-ui;color:#1d1d1f";
  host.appendChild(overlay);

  const origin = new THREE.Vector3(-SIZE, -SIZE, -SIZE);
  const axisMaterial = new THREE.LineBasicMaterial({ color: 0x1d1d1f });
  const axes: { label: HTMLSpanElement; point: THREE.Vector3 }[] = [];
  ([
    [new THREE.Vector3(1, 0, 0), "Confidence"],
    [new THREE.Vector3(0, 1, 0), "Impact"],
    [new THREE.Vector3(0, 0, 1), "Reaction"],
  ] as const).forEach(([direction, text]) => {
    const point = origin.clone().addScaledVector(direction, SIZE * 2 + 0.28);
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([origin, point]), axisMaterial));
    const label = document.createElement("span");
    label.textContent = text;
    label.style.cssText = "position:absolute;white-space:nowrap;transform:translate(-50%,-50%)";
    overlay.appendChild(label);
    axes.push({ label, point });
  });

  const grid = new THREE.GridHelper(SIZE * 2, 4, 0xdcdce0, 0xececef);
  grid.position.y = -SIZE;
  scene.add(grid);

  const orbGeometry = new THREE.SphereGeometry(0.105, 28, 20);
  const hitGeometry = new THREE.SphereGeometry(0.2, 12, 8);
  const orbs = new Map<string, { group: THREE.Group; material: THREE.MeshBasicMaterial; hit: THREE.Mesh; title: string }>();
  let selected: string | null = null;
  let hovered: string | null = null;
  let yaw = HOME.yaw;
  let pitch = HOME.pitch;
  let distance = HOME.distance;
  let target = new THREE.Vector3(0, -0.08, 0);
  let pointerStart: { x: number; y: number; moved: boolean } | null = null;
  let alive = true;
  let animationFrame = 0;

  const refreshStyles = () => {
    for (const [id, orb] of orbs) {
      const active = id === selected;
      const over = id === hovered;
      orb.group.scale.setScalar(active ? 1.7 : over ? 1.35 : 1);
      orb.material.color.setHex(active ? 0x063b86 : over ? 0x0a4fb0 : 0x0a7aff);
    }
  };

  const setItems = (items: SceneItem[]) => {
    for (const orb of orbs.values()) scene.remove(orb.group);
    orbs.clear();
    for (const item of items) {
      const group = new THREE.Group();
      group.position.set(item.world[0] * SIZE, item.world[1] * SIZE, item.world[2] * SIZE);
      const material = new THREE.MeshBasicMaterial({ color: 0x0a7aff });
      const core = new THREE.Mesh(orbGeometry, material);
      const halo = new THREE.Mesh(new THREE.SphereGeometry(0.17, 20, 14), new THREE.MeshBasicMaterial({ color: 0x77b8ff, transparent: true, opacity: 0.2, depthWrite: false }));
      const hit = new THREE.Mesh(hitGeometry, new THREE.MeshBasicMaterial({ visible: false }));
      hit.userData.id = item.id;
      group.add(halo, core, hit);
      scene.add(group);
      orbs.set(item.id, { group, material, hit, title: item.title });
    }
    if (selected && !orbs.has(selected)) selected = null;
    refreshStyles();
  };

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const pick = (event: PointerEvent): string | null => {
    const bounds = renderer.domElement.getBoundingClientRect();
    pointer.set(((event.clientX - bounds.left) / bounds.width) * 2 - 1, -((event.clientY - bounds.top) / bounds.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects([...orbs.values()].map((orb) => orb.hit), false)[0];
    return hit ? String(hit.object.userData.id) : null;
  };

  const onPointerDown = (event: PointerEvent) => {
    pointerStart = { x: event.clientX, y: event.clientY, moved: false };
    renderer.domElement.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent) => {
    if (pointerStart) {
      const dx = event.clientX - pointerStart.x;
      const dy = event.clientY - pointerStart.y;
      if (Math.hypot(dx, dy) >= 3) pointerStart.moved = true;
      if (pointerStart.moved) {
        yaw -= dx * 0.006;
        pitch = Math.max(0.12, Math.min(1.35, pitch + dy * 0.005));
        pointerStart.x = event.clientX;
        pointerStart.y = event.clientY;
        renderer.domElement.style.cursor = "grabbing";
      }
      return;
    }
    const id = pick(event);
    if (id !== hovered) {
      hovered = id;
      callbacks.onHover?.(id);
      renderer.domElement.title = id ? orbs.get(id)?.title ?? "" : "";
      refreshStyles();
    }
    renderer.domElement.style.cursor = id ? "pointer" : "grab";
  };
  const onPointerUp = (event: PointerEvent) => {
    const start = pointerStart;
    pointerStart = null;
    renderer.domElement.style.cursor = "grab";
    if (start && !start.moved) callbacks.onSelect?.(pick(event));
  };
  const onWheel = (event: WheelEvent) => {
    event.preventDefault();
    distance = Math.max(3.2, Math.min(12, distance * Math.exp(event.deltaY * 0.0012)));
  };
  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerup", onPointerUp);
  renderer.domElement.addEventListener("pointercancel", onPointerUp);
  renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

  const resizeObserver = new ResizeObserver(() => {
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  });
  resizeObserver.observe(host);

  const projected = new THREE.Vector3();
  const render = () => {
    if (!alive) return;
    animationFrame = requestAnimationFrame(render);
    camera.position.set(
      target.x + distance * Math.cos(pitch) * Math.sin(yaw),
      target.y + distance * Math.sin(pitch),
      target.z + distance * Math.cos(pitch) * Math.cos(yaw),
    );
    camera.lookAt(target);
    for (const axis of axes) {
      projected.copy(axis.point).project(camera);
      axis.label.style.left = `${(projected.x + 1) * 50}%`;
      axis.label.style.top = `${(1 - projected.y) * 50}%`;
      axis.label.style.visibility = projected.z < 1 ? "visible" : "hidden";
    }
    renderer.render(scene, camera);
  };
  render();

  return {
    setItems,
    focus(id) {
      selected = id;
      const orb = id ? orbs.get(id) : undefined;
      target = orb ? orb.group.position.clone().multiplyScalar(0.28) : new THREE.Vector3(0, -0.08, 0);
      refreshStyles();
    },
    setHover(id) { hovered = id; refreshStyles(); },
    reset() { yaw = HOME.yaw; pitch = HOME.pitch; distance = HOME.distance; target.set(0, -0.08, 0); selected = null; refreshStyles(); },
    dispose() {
      alive = false;
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointercancel", onPointerUp);
      renderer.domElement.removeEventListener("wheel", onWheel);
      renderer.dispose();
      orbGeometry.dispose();
      hitGeometry.dispose();
      host.replaceChildren();
    },
  };
}
