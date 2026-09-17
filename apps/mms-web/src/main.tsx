import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { watchVisualViewport } from "./viewport";
import "./styles.css";
import "./studio.css";
import "./states.css";
import "./transcript.css";
import "./side-questions.css";
import "./connections.css";
import "./artifacts.css";
import "./materials.css";
import "./recipes.css";
import "./remote-access.css";

watchVisualViewport();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
