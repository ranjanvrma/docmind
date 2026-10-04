/**
 * Shared motion tokens. Every animation in the app draws its timing from here
 * so movement feels consistent: fast for interactions, slower for entrances,
 * springs for physical things (hover lift, layout), eases for simple fades.
 */
import type { Transition, Variants } from "motion/react";

export const duration = { fast: 0.18, normal: 0.32, slow: 0.6 } as const;
export const ease = [0.22, 1, 0.36, 1] as const; // ease-out-quint-ish

export const spring: Transition = { type: "spring", stiffness: 380, damping: 32, mass: 0.8 };

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14, filter: "blur(6px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: duration.slow, ease } },
};

export const stagger = (step = 0.06, delay = 0): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: step, delayChildren: delay } },
});

export const listItem: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: duration.normal, ease } },
  exit: { opacity: 0, scale: 0.97, transition: { duration: duration.fast } },
};
