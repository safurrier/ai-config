window.mermaid.initialize({ startOnLoad: false });

const renderMermaid = () => {
  window.mermaid.run({ querySelector: ".mermaid" });
};

if (typeof document$ === "undefined") {
  window.addEventListener("DOMContentLoaded", renderMermaid);
} else {
  document$.subscribe(renderMermaid);
}
