import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Suppress unhandled rejections from browser extensions (e.g. MetaMask)
window.addEventListener("unhandledrejection", (event) => {
  const msg = event.reason?.message ?? String(event.reason ?? "");
  if (msg.toLowerCase().includes("metamask") || msg.toLowerCase().includes("chrome-extension")) {
    event.preventDefault();
  }
});

createRoot(document.getElementById("root")!).render(<App />);
