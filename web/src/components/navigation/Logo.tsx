import { Link } from "react-router";

export function LogoMark({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--surface-2)" stroke="var(--border-strong)" />
      <path d="M10 7.5h8.5L23 12v12.5H10z" stroke="var(--accent)" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M18.5 7.5V12H23" stroke="var(--accent)" strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="14" cy="17" r="1.4" fill="var(--accent-2)" />
      <circle cx="19" cy="20.5" r="1.4" fill="var(--accent)" />
      <path d="M14 17l5 3.5" stroke="var(--accent)" strokeOpacity="0.7" strokeWidth="1" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-xl pr-2" aria-label="DocMind home">
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-tight">DocMind</span>
    </Link>
  );
}
