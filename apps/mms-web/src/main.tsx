import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import "./studio.css";
import "./states.css";
import "./transcript.css";
import "./connections.css";
import "./artifacts.css";
import "./materials.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

import "./recipes.css";
