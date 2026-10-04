/**
 * Hero scene: documents -> knowledge -> retrieval.
 *
 * A small stack of document sheets floats in the centre (the corpus). Around
 * it sits a shell of semantic nodes connected to their nearest neighbours
 * (the embedding space). A few "retrieval beams" link nodes back to the stack
 * and brighten whenever the app emits a scene pulse (upload, search, answer).
 *
 * Performance: one canvas, shared geometries/materials, one instanced mesh
 * for nodes, one LineSegments for all links, one Points cloud, no
 * post-processing, no React state inside the render loop, and the loop is
 * paused when the canvas is off-screen.
 */
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import * as THREE from "three";

import { lastPulse } from "@/lib/events";

const ACCENT = new THREE.Color("#67d0f5");
const VIOLET = new THREE.Color("#b7a6f5");
const NODE_COUNT = 38;
const PARTICLE_COUNT = 240;

/** Deterministic pseudo-random numbers so the scene looks the same on every load. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function fibonacciShell(count: number, radius: number, rand: () => number): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    const jitter = radius * (0.85 + rand() * 0.3);
    points.push(new THREE.Vector3(Math.cos(theta) * r * jitter, y * jitter * 0.8, Math.sin(theta) * r * jitter));
  }
  return points;
}

function useSceneData() {
  return useMemo(() => {
    const rand = mulberry32(7);
    const nodes = fibonacciShell(NODE_COUNT, 2.05, rand);

    // Each node links to its two nearest neighbours (deduplicated).
    const seen = new Set<string>();
    const linkPositions: number[] = [];
    nodes.forEach((a, i) => {
      nodes
        .map((b, j) => ({ j, d: a.distanceTo(b) }))
        .filter(({ j }) => j !== i)
        .sort((x, y) => x.d - y.d)
        .slice(0, 2)
        .forEach(({ j }) => {
          const key = i < j ? `${i}-${j}` : `${j}-${i}`;
          if (seen.has(key)) return;
          seen.add(key);
          linkPositions.push(a.x, a.y, a.z, nodes[j].x, nodes[j].y, nodes[j].z);
        });
    });

    // Retrieval beams: a handful of nodes connected to the document stack.
    const beamPositions: number[] = [];
    [3, 11, 17, 24, 33].forEach((i) => {
      const n = nodes[i];
      beamPositions.push(n.x, n.y, n.z, 0, 0, 0);
    });

    const particles = new Float32Array(PARTICLE_COUNT * 3);
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const r = 2.4 + rand() * 1.3;
      const theta = rand() * Math.PI * 2;
      const phi = Math.acos(2 * rand() - 1);
      particles.set([r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi) * 0.7, r * Math.sin(phi) * Math.sin(theta)], i * 3);
    }
    return { nodes, links: new Float32Array(linkPositions), beams: new Float32Array(beamPositions), particles };
  }, []);
}

function DocumentStack() {
  const group = useRef<THREE.Group>(null);
  const { sheet, edges, sheetMaterial, edgeMaterial, line, lineMaterial } = useMemo(() => {
    const sheet = new THREE.BoxGeometry(1.45, 1.9, 0.02);
    return {
      sheet,
      edges: new THREE.EdgesGeometry(sheet),
      // Lit, slightly emissive glass so the pages read as pages from any angle.
      sheetMaterial: new THREE.MeshStandardMaterial({
        color: "#3a4a5c",
        emissive: "#12303f",
        emissiveIntensity: 0.9,
        roughness: 0.25,
        metalness: 0.1,
        transparent: true,
        opacity: 0.9,
        side: THREE.DoubleSide,
      }),
      edgeMaterial: new THREE.LineBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.85 }),
      line: new THREE.PlaneGeometry(1, 0.035),
      lineMaterial: new THREE.MeshBasicMaterial({ color: "#e3edf6", transparent: true, opacity: 0.55 }),
    };
  }, []);

  // Text lines on the top sheet: varying widths, like a page of prose.
  const lines = useMemo(() => [0.95, 0.8, 0.9, 0.6, 0.85, 0.92, 0.7, 0.5].map((w, i) => ({ w, y: 0.62 - i * 0.16 })), []);

  useFrame((state) => {
    const g = group.current;
    if (!g) return;
    const t = state.clock.elapsedTime;
    g.position.y = Math.sin(t * 0.8) * 0.06;
    // Face the viewer, with a small tilt toward the pointer (never edge-on).
    g.rotation.y = THREE.MathUtils.lerp(g.rotation.y, 0.22 + state.pointer.x * 0.18, 0.05);
    g.rotation.x = THREE.MathUtils.lerp(g.rotation.x, -0.1 - state.pointer.y * 0.12, 0.05);
    // The sheets fan out slightly, like pages being read.
    g.children.forEach((child, i) => {
      if (child.userData.sheet) child.position.z = -i * 0.16 - Math.sin(t * 0.6 + i) * 0.015;
    });
  });

  return (
    <group ref={group} rotation={[-0.1, 0.22, 0.04]}>
      {[0, 1, 2, 3].map((i) => (
        <group key={i} userData={{ sheet: true }} position={[i * 0.09, -i * 0.07, -i * 0.16]}>
          <mesh geometry={sheet} material={sheetMaterial} />
          <lineSegments geometry={edges} material={edgeMaterial} />
          {i === 0 &&
            lines.map(({ w, y }) => (
              <mesh key={y} geometry={line} material={lineMaterial} position={[-0.55 + (w * 1.1) / 2, y, 0.012]} scale={[w * 1.1, 1, 1]} />
            ))}
        </group>
      ))}
    </group>
  );
}

function SemanticField() {
  const { nodes, links, beams, particles } = useSceneData();
  const nodeMesh = useRef<THREE.InstancedMesh>(null);

  const geo = useMemo(() => {
    const link = new THREE.BufferGeometry();
    link.setAttribute("position", new THREE.BufferAttribute(links, 3));
    const beam = new THREE.BufferGeometry();
    beam.setAttribute("position", new THREE.BufferAttribute(beams, 3));
    const dust = new THREE.BufferGeometry();
    dust.setAttribute("position", new THREE.BufferAttribute(particles, 3));
    return { link, beam, dust, node: new THREE.IcosahedronGeometry(0.045, 1) };
  }, [links, beams, particles]);

  const mat = useMemo(
    () => ({
      node: new THREE.MeshBasicMaterial({ color: ACCENT }),
      link: new THREE.LineBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.16 }),
      beam: new THREE.LineBasicMaterial({ color: VIOLET, transparent: true, opacity: 0.2 }),
      dust: new THREE.PointsMaterial({ color: "#9fb4c8", size: 0.022, transparent: true, opacity: 0.55, depthWrite: false }),
    }),
    [],
  );

  useEffect(() => {
    const mesh = nodeMesh.current;
    if (!mesh) return;
    const m = new THREE.Matrix4();
    nodes.forEach((p, i) => mesh.setMatrixAt(i, m.makeTranslation(p.x, p.y, p.z)));
    mesh.instanceMatrix.needsUpdate = true;
  }, [nodes]);

  useFrame(() => {
    // Pulse decays over ~0.8s after an upload/search/answer.
    const k = Math.exp(-(performance.now() - lastPulse.at) / 800);
    mat.beam.opacity = 0.2 + 0.65 * k;
    mat.link.opacity = 0.16 + 0.2 * k;
    mat.node.color.copy(ACCENT).lerp(VIOLET, k * 0.6);
  });

  return (
    <group>
      <instancedMesh ref={nodeMesh} args={[geo.node, mat.node, NODE_COUNT]} />
      <lineSegments geometry={geo.link} material={mat.link} />
      <lineSegments geometry={geo.beam} material={mat.beam} />
      <points geometry={geo.dust} material={mat.dust} />
    </group>
  );
}

/** Rotates the knowledge shell slowly; the document stack stays put and faces the viewer. */
function ShellRig({ children }: { children: ReactNode }) {
  const outer = useRef<THREE.Group>(null);
  const inner = useRef<THREE.Group>(null);
  useFrame((state, delta) => {
    if (outer.current) outer.current.rotation.y += delta * 0.06;
    if (inner.current) {
      // Gentle parallax toward the pointer.
      inner.current.rotation.x = THREE.MathUtils.lerp(inner.current.rotation.x, -state.pointer.y * 0.15, 0.05);
      inner.current.rotation.z = THREE.MathUtils.lerp(inner.current.rotation.z, state.pointer.x * 0.1, 0.05);
    }
  });
  return (
    <group ref={inner}>
      <group ref={outer}>{children}</group>
    </group>
  );
}

export default function KnowledgeScene({ active }: { active: boolean }) {
  return (
    <Canvas
      frameloop={active ? "always" : "never"}
      dpr={[1, 1.75]}
      // Framed so the whole shell fits; the container also fades the edges.
      camera={{ position: [0, 0.2, 8], fov: 42 }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      aria-hidden
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={[3, 4, 5]} intensity={1.1} />
      <pointLight position={[-2.5, 1.2, 2]} intensity={7} distance={9} color={ACCENT} />
      <DocumentStack />
      <ShellRig>
        <SemanticField />
      </ShellRig>
    </Canvas>
  );
}
