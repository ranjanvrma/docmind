import "@fontsource-variable/geist";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyMotion, applyTheme, getMotion, getTheme } from "./lib/preferences";

// Apply stored theme/motion before the first paint to avoid a flash.
applyTheme(getTheme());
applyMotion(getMotion());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
