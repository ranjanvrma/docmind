/**
 * Chooses between the WebGL scene and a static CSS fallback.
 *
 * The 3D scene is used only when: WebGL is available, the user has not asked
 * for reduced motion, and the viewport is at least tablet-sized. The scene's
 * JavaScript (three.js) is lazy-loaded, so other pages never download it.
 */
import { Component, lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";

import { usePreferences } from "@/components/layout/PreferencesProvider";
import { SceneFallback } from "./SceneFallback";

const KnowledgeScene = lazy(() => import("./KnowledgeScene"));

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function HeroVisual() {
  const { reducedMotion } = usePreferences();
  const container = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const [wideEnough, setWideEnough] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  const [canWebgl] = useState(webglAvailable);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 768px)");
    const update = () => setWideEnough(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  // Pause rendering when the hero scrolls out of view or the tab is hidden.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.05 });
    observer.observe(el);
    const onVisibility = () => setVisible(!document.hidden && el.getBoundingClientRect().bottom > 0);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const use3d = canWebgl && !reducedMotion && wideEnough;
  const fallback = <SceneFallback />;

  return (
    <div
      ref={container}
      className="relative h-full w-full"
      style={{
        maskImage: "radial-gradient(closest-side, #000 78%, transparent 100%)",
        WebkitMaskImage: "radial-gradient(closest-side, #000 78%, transparent 100%)",
      }}
    >
      {use3d ? (
        <SceneBoundary fallback={fallback}>
          <Suspense fallback={fallback}>
            <KnowledgeScene active={visible} />
          </Suspense>
        </SceneBoundary>
      ) : (
        fallback
      )}
    </div>
  );
}
