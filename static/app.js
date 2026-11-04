(() => {
  const form = document.getElementById("upload-form");
  const input = document.getElementById("file-input");
  const dropzone = document.getElementById("dropzone");
  const fileInfo = document.getElementById("file-info");
  const btn = document.getElementById("generate-btn");
  const btnLabel = btn.querySelector(".btn-label");
  const statusBox = document.getElementById("status");
  const statusText = document.getElementById("status-text");
  const elapsedEl = document.getElementById("elapsed");
  const alertBox = document.getElementById("alert");
  const results = document.getElementById("results");

  const ALLOWED = [".mp4", ".mov", ".webm", ".mkv", ".avi"];
  const STAGES = [
    [0, "Uploading video…"],
    [4, "Gemini is processing the video…"],
    [15, "Extracting transcript & answering questions…"],
    [45, "Building PDF & sending email…"],
    [90, "Still working — longer videos take more time…"],
  ];
  let selectedFile = null;
  let timer = null;

  const fmtSize = (b) => (b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : (b / 1e3).toFixed(0) + " KB");
  const escapeHtml = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function showAlert(type, msg) {
    alertBox.className = `alert ${type}`;
    alertBox.textContent = msg;
    alertBox.hidden = false;
  }

  function setFile(file) {
    alertBox.hidden = true;
    results.hidden = true;
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED.includes(ext) && !file.type.startsWith("video/")) {
      selectedFile = null;
      btn.disabled = true;
      fileInfo.hidden = true;
      showAlert("error", `Unsupported file type. Please choose: ${ALLOWED.join(", ")}`);
      return;
    }
    selectedFile = file;
    fileInfo.textContent = `🎬 ${file.name} · ${fmtSize(file.size)}`;
    fileInfo.hidden = false;
    btn.disabled = false;
  }

  function setLoading(on) {
    btn.disabled = on;
    btn.classList.toggle("loading", on);
    btnLabel.textContent = on ? "Generating Report…" : "Generate Report";
    input.disabled = on;
    statusBox.hidden = !on;
    clearInterval(timer);
    if (on) {
      const start = Date.now();
      const tick = () => {
        const s = Math.floor((Date.now() - start) / 1000);
        elapsedEl.textContent = `${s}s`;
        statusText.textContent = STAGES.filter(([t]) => s >= t).pop()[1];
      };
      tick();
      timer = setInterval(tick, 1000);
    }
  }

  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
  dropzone.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    alertBox.hidden = true;
    results.hidden = true;
    setLoading(true);

    const data = new FormData();
    data.append("file", selectedFile);
    try {
      const res = await fetch("/generate-report", { method: "POST", body: data });
      let body = {};
      try { body = await res.json(); } catch { /* non-JSON response */ }
      if (!res.ok || body.status !== "success") {
        throw new Error(body.detail || `Server error (HTTP ${res.status}).`);
      }
      showAlert("success", `✅ ${body.message || "Report generated and emailed successfully."}`);
      if (Array.isArray(body.qa) && body.qa.length) {
        results.innerHTML =
          "<h2>Quick preview</h2>" +
          body.qa.map((q) => `<div class="qa"><div class="q">${escapeHtml(q.question)}</div>` +
                             `<div class="a">${escapeHtml(q.answer)}</div></div>`).join("");
        results.hidden = false;
      }
    } catch (err) {
      const msg = err instanceof TypeError ? "Could not reach the server. Is it running?" : err.message;
      showAlert("error", `❌ ${msg}`);
    } finally {
      setLoading(false);
      btn.disabled = !selectedFile;
    }
  });
})();
