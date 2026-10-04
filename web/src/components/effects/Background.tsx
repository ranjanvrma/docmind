/**
 * Page atmosphere: ambient radial lighting, a faint top grid and a static
 * grain texture. All three are fixed, pointer-events-free layers drawn once
 * by the compositor; nothing here animates.
 */
export function AppBackground() {
  return (
    <>
      <div aria-hidden className="ambient" />
      <div aria-hidden className="grid-pattern pointer-events-none fixed inset-x-0 top-0 z-0 h-[42rem] opacity-60" />
      <div aria-hidden className="noise-overlay" />
    </>
  );
}

/** Soft spotlight cone used behind the hero heading (Aceternity Spotlight-style, static SVG). */
export function Spotlight({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={`pointer-events-none absolute z-0 h-[150%] w-[140%] opacity-0 motion-safe:animate-[spotlight_1.6s_ease_0.2s_forwards] motion-reduce:opacity-60 ${className}`}
      viewBox="0 0 3787 2842"
      fill="none"
    >
      <g filter="url(#spotlight-blur)">
        <ellipse
          cx="1924.71"
          cy="273.501"
          rx="1924.71"
          ry="273.501"
          transform="matrix(-0.822377 -0.568943 -0.568943 0.822377 3631.88 2291.09)"
          fill="var(--accent)"
          fillOpacity="0.09"
        />
      </g>
      <defs>
        <filter id="spotlight-blur" x="0.86" y="0.84" width="3785.16" height="2840.26" filterUnits="userSpaceOnUse">
          <feGaussianBlur stdDeviation="151" />
        </filter>
      </defs>
    </svg>
  );
}

/**
 * A thin conic-gradient line that travels around a rounded panel (Moving
 * Border-style). Pure CSS: one rotating gradient, masked to a 1px ring.
 */
export function MovingBorder({ active = false }: { active?: boolean }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute -inset-px overflow-hidden rounded-[inherit]"
      style={{
        padding: 1,
        mask: "linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0)",
        WebkitMask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
        WebkitMaskComposite: "xor",
      }}
    >
      <div
        className={`absolute left-1/2 top-1/2 aspect-square w-[200%] -translate-x-1/2 -translate-y-1/2 animate-spin-slow transition-opacity duration-500 ${active ? "opacity-100" : "opacity-60"}`}
        style={{
          background: "conic-gradient(from 0deg, transparent 0deg, var(--accent) 40deg, var(--accent-2) 80deg, transparent 120deg)",
        }}
      />
    </div>
  );
}
