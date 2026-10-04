/**
 * Static pseudo-3D version of the hero scene (CSS transforms only). Used on
 * small screens, without WebGL, with reduced motion, and while the 3D bundle
 * loads. It tells the same story: document sheets surrounded by connected
 * semantic nodes.
 */
const NODES = [
  [12, 22], [26, 8], [44, 14], [70, 10], [86, 26], [90, 52], [80, 78], [60, 90], [34, 88], [14, 72], [8, 46], [52, 4],
];
const LINKS = [[0, 1], [1, 2], [2, 11], [11, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 0], [2, 3]];
const BEAMS = [1, 4, 6, 9];

export function SceneFallback() {
  return (
    <div aria-hidden className="relative mx-auto aspect-square h-full max-h-[520px] w-full max-w-[520px]">
      <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full">
        {LINKS.map(([a, b]) => (
          <line key={`${a}-${b}`} x1={NODES[a][0]} y1={NODES[a][1]} x2={NODES[b][0]} y2={NODES[b][1]} stroke="var(--accent)" strokeOpacity="0.18" strokeWidth="0.25" />
        ))}
        {BEAMS.map((i) => (
          <line key={`beam-${i}`} x1={NODES[i][0]} y1={NODES[i][1]} x2="50" y2="50" stroke="var(--accent-2)" strokeOpacity="0.28" strokeWidth="0.25" strokeDasharray="1 1.4" />
        ))}
        {NODES.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="0.9" fill="var(--accent)" fillOpacity="0.85" />
        ))}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center [perspective:900px]">
        <div className="relative h-[46%] w-[34%] [transform:rotateX(52deg)_rotateZ(-32deg)] [transform-style:preserve-3d]">
          {[3, 2, 1, 0].map((i) => (
            <div
              key={i}
              className="glass absolute inset-0 rounded-lg border-accent/30"
              style={{ transform: `translate3d(${i * 6}px, ${i * -6}px, ${-i * 18}px)`, opacity: 1 - i * 0.18 }}
            >
              {i === 0 && (
                <div className="space-y-[7%] p-[12%]">
                  {[90, 75, 85, 55, 80, 65].map((w) => (
                    <div key={w} className="h-[3px] rounded-full bg-fg/25" style={{ width: `${w}%` }} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
