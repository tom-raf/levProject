// Dashboard shell interactions (ticket #9). Live/Simulated SSE wiring lands
// in tickets #10-#11 -- these two buttons are inert placeholders for now.

const transcriptToggle = document.getElementById("transcript-toggle");
const transcriptBody = document.getElementById("transcript-body");
const transcriptLabel = document.getElementById("transcript-toggle-label");

transcriptToggle.addEventListener("click", () => {
  const collapsed = transcriptBody.style.display === "none";
  transcriptBody.style.display = collapsed ? "" : "none";
  transcriptLabel.textContent = collapsed ? "[ − COLLAPSE ]" : "[ + EXPAND ]";
});

document.getElementById("btn-live").addEventListener("click", () => {
  console.log("Live run -- not wired yet (ticket #11)");
});

document.getElementById("btn-simulated").addEventListener("click", () => {
  console.log("Simulated run -- not wired yet (ticket #10)");
});
