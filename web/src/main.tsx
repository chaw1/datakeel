import React from "react";
import { createRoot } from "react-dom/client";

import App from "./app/App";
import { I18nProvider } from "./i18n/I18nProvider";
import "./styles.css";

const root = document.getElementById("root");
if (root)
  createRoot(root).render(
    <React.StrictMode>
      <I18nProvider>
        <App />
      </I18nProvider>
    </React.StrictMode>,
  );
