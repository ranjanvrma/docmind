import { MotionConfig } from "motion/react";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  applyMotion,
  applyTheme,
  getMotion,
  getTheme,
  prefersReducedMotion,
  type MotionPreference,
  type ThemePreference,
} from "@/lib/preferences";

interface PreferencesValue {
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  motion: MotionPreference;
  setMotion: (motion: MotionPreference) => void;
  /** Effective value: in-app setting, else the OS preference. */
  reducedMotion: boolean;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(getTheme);
  const [motion, setMotionState] = useState<MotionPreference>(getMotion);
  const [systemReduced, setSystemReduced] = useState(() => prefersReducedMotion("system"));

  useEffect(() => applyTheme(theme), [theme]);
  useEffect(() => applyMotion(motion), [motion]);

  // Follow OS changes for "system" theme and motion.
  useEffect(() => {
    const scheme = window.matchMedia("(prefers-color-scheme: light)");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onScheme = () => theme === "system" && applyTheme("system");
    const onReduce = () => setSystemReduced(reduce.matches);
    scheme.addEventListener("change", onScheme);
    reduce.addEventListener("change", onReduce);
    return () => {
      scheme.removeEventListener("change", onScheme);
      reduce.removeEventListener("change", onReduce);
    };
  }, [theme]);

  const reducedMotion = motion === "reduced" || (motion === "system" && systemReduced);

  const value = useMemo(
    () => ({ theme, setTheme: setThemeState, motion, setMotion: setMotionState, reducedMotion }),
    [theme, motion, reducedMotion],
  );

  return (
    <PreferencesContext.Provider value={value}>
      <MotionConfig reducedMotion={reducedMotion ? "always" : "never"}>{children}</MotionConfig>
    </PreferencesContext.Provider>
  );
}

export function usePreferences(): PreferencesValue {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("usePreferences must be used inside PreferencesProvider");
  return value;
}
