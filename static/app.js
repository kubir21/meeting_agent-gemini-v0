(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("upload-form"), input = $("file-input"), dropzone = $("dropzone");
  const chip = $("file-chip"), chipName = $("file-name"), chipSize = $("file-size");
  const btn = $("generate-btn"), btnLabel = btn.querySelector(".btn-label");
  const stepsEl = $("steps"), alertBox = $("alert");
  const progressContainer = $("progress-container"), progressBar = $("progress-bar");
  const progressLabel = $("progress-label"), progressPct = $("progress-pct");
  const emptyEl = $("empty"), reportEl = $("report");
  const historyPanel = $("history-panel"), historyList = $("history-list");

  const ALLOWED = [".mp4", ".mov", ".webm", ".mkv", ".avi"];
  const HISTORY_KEY = "video_insights_history_v1";
  const HISTORY_MAX = 5;
  let selectedFile = null, timer = null, current = null;

  $("today").textContent = new Date().toLocaleDateString(undefined, {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtSize = (b) => (b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1e3)) + " KB");
  const slug = (s) => String(s || "report").replace(/[^\w\-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "report";
  const fmtDateTime = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) +
      ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  };

  function showAlert(type, msg) {
    alertBox.className = `alert ${type}`;
    alertBox.textContent = msg;
    alertBox.hidden = false;
  }

  // File selection
  function setFile(file) {
    alertBox.hidden = true;
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED.includes(ext) && !file.type.startsWith("video/")) {
      selectedFile = null; btn.disabled = true; chip.hidden = true;
      showAlert("error", `Unsupported file type. Please choose one of: ${ALLOWED.join(", ")}`);
      return;
    }
    selectedFile = file;
    chipName.textContent = file.name;
    chipSize.textContent = fmtSize(file.size);
    chip.hidden = false;
    btn.disabled = false;
  }
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault(); dropzone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault(); dropzone.classList.remove("drag"); }));
  dropzone.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

  // Progress steps & bar
  function setProgress(pct, label) {
    const val = Math.min(100, Math.max(0, Math.round(pct)));
    progressBar.style.width = `${val}%`;
    progressPct.textContent = `${val}%`;
    if (label) progressLabel.textContent = label;
  }

  function setStep(n) {
    stepsEl.querySelectorAll("li").forEach((li) => {
      const i = Number(li.dataset.step);
      li.className = i < n ? "done" : i === n ? "active" : "";
    });
  }

  function setLoading(on) {
    btn.disabled = on || !selectedFile;
    btn.classList.toggle("loading", on);
    btnLabel.textContent = on ? "Generating..." : "Generate Report";
    input.disabled = on;
    stepsEl.hidden = !on;
    progressContainer.hidden = !on;
    clearInterval(timer);
    if (on) {
      setProgress(0, "Starting upload...");
      setStep(0);
    }
  }

  // Downloads
  function saveBlob(name, blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }
  function pdfBlob(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: "application/pdf" });
  }
  function downloadPdf(r) {
    saveBlob(`Report_${slug(r.company)}_${r.generated_at.slice(0, 10)}.pdf`, pdfBlob(r.pdf_base64));
  }
  function downloadTranscript(r) {
    const header = [
      `Company: ${r.company}`,
      `Source video: ${r.source_file}`,
      `Date and time: ${fmtDateTime(r.generated_at)}`,
      `Report ID: ${r.report_id}`,
      "",
      "TRANSCRIPT",
      "----------",
      "",
    ].join("\r\n");
    const body = String(r.transcript || "").replace(/\r?\n/g, "\r\n");
    // BOM so Notepad opens Hindi and other non-Latin text correctly
    saveBlob(`Transcript_${slug(r.company)}_${r.generated_at.slice(0, 10)}.txt`,
      new Blob(["\ufeff", header, body, "\r\n"], { type: "text/plain;charset=utf-8" }));
  }
  $("dl-pdf").addEventListener("click", () => current && downloadPdf(current));
  $("dl-txt").addEventListener("click", () => current && downloadTranscript(current));

  // Render a report
  function renderReport(r) {
    current = r;
    emptyEl.hidden = true;
    reportEl.hidden = false;
    $("r-company").textContent = r.company;
    $("r-sub").textContent = `${fmtDateTime(r.generated_at)}  |  ${r.source_file}`;
    $("r-id").textContent = r.report_id;

    const tiles = [
      ["Date", new Date(r.generated_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })],
      ["Time", new Date(r.generated_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })],
      ["Duration", r.meta?.duration || "Not available"],
      ["Language", r.meta?.language || "Not available"],
    ];
    $("r-tiles").innerHTML = tiles.map(([k, v]) =>
      `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");

    const note = $("r-note");
    if (r.email && r.email.sent) {
      note.className = "note ok";
      note.textContent = `A copy of this report was emailed to ${r.email.recipient}.`;
      note.hidden = false;
    } else if (r.email && r.email.note) {
      note.className = "note";
      note.textContent = r.email.note;
      note.hidden = false;
    } else {
      note.hidden = true;
    }

    $("r-summary-wrap").hidden = !r.summary;
    $("r-summary").textContent = r.summary || "";
    $("r-qa").innerHTML = (r.qa || []).map((q, i) => `
      <div class="qa-card">
        <div class="qa-label q">Question ${i + 1}</div>
        <div class="qa-q">${esc(q.question)}</div>
        <div class="qa-label a">Answer ${i + 1}</div>
        <div class="qa-a">${esc(q.answer)}</div>
        ${q.reasoning ? `<div class="qa-e">Evidence: ${esc(q.reasoning)}</div>` : ""}
      </div>`).join("");
  }

  // History (browser only)
  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch { return []; }
  }
  function saveHistory(entry) {
    let list = [entry, ...loadHistory().filter((h) => h.report_id !== entry.report_id)].slice(0, HISTORY_MAX);
    while (list.length) {
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(list)); break; }
      catch { list = list.slice(0, -1); } // storage full: drop the oldest
    }
    renderHistory();
  }
  function renderHistory() {
    const list = loadHistory();
    historyPanel.hidden = list.length === 0;
    historyList.innerHTML = list.map((h) => `
      <li data-id="${esc(h.report_id)}">
        <div class="h-main">
          <div class="h-title">${esc(h.company)}</div>
          <div class="h-meta">${esc(fmtDateTime(h.generated_at))}  |  ${esc(h.source_file)}  |  ${esc(h.report_id)}</div>
        </div>
        <div class="h-actions">
          <button class="btn btn-secondary btn-sm" data-act="view" type="button">View</button>
          <button class="btn btn-secondary btn-sm" data-act="pdf" type="button">PDF</button>
          <button class="btn btn-secondary btn-sm" data-act="txt" type="button">Transcript</button>
        </div>
      </li>`).join("");
  }
  historyList.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const id = b.closest("li").dataset.id;
    const h = loadHistory().find((x) => x.report_id === id);
    if (!h) return;
    if (b.dataset.act === "view") { renderReport(h); window.scrollTo({ top: 0, behavior: "smooth" }); }
    if (b.dataset.act === "pdf") downloadPdf(h);
    if (b.dataset.act === "txt") downloadTranscript(h);
  });

  // Submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    alertBox.hidden = true;
    setLoading(true);

    const data = new FormData();
    data.append("file", selectedFile);

    try {
      const xhr = new XMLHttpRequest();

      const responsePromise = new Promise((resolve, reject) => {
        xhr.upload.addEventListener("progress", (ev) => {
          if (ev.lengthComputable) {
            // Upload takes first 0% - 40% of overall progress
            const uploadPct = (ev.loaded / ev.total) * 40;
            setProgress(uploadPct, `Uploading video (${fmtSize(ev.loaded)} / ${fmtSize(ev.total)})...`);
            if (uploadPct >= 38) {
              setStep(1);
            }
          }
        });

        xhr.upload.addEventListener("load", () => {
          setStep(1);
          setProgress(40, "Video uploaded. Gemini is processing audio and visual tracks...");
          // Animate progress smoothly from 40% to 92% while waiting for LLM
          let currentPct = 40;
          timer = setInterval(() => {
            if (currentPct < 75) {
              currentPct += 1.5;
              setProgress(currentPct, "Gemini is analyzing video and generating transcript...");
            } else if (currentPct < 92) {
              currentPct += 0.5;
              setStep(2);
              setProgress(currentPct, "Formatting PDF report and contextual Q&A...");
            }
          }, 1000);
        });

        xhr.addEventListener("load", () => {
          clearInterval(timer);
          try {
            const body = JSON.parse(xhr.responseText || "{}");
            if (xhr.status >= 200 && xhr.status < 300 && body.status === "success") {
              setProgress(100, "Done!");
              setStep(3);
              resolve(body);
            } else {
              reject(new Error(body.detail || `Server error (HTTP ${xhr.status}).`));
            }
          } catch (err) {
            reject(new Error(`Server error (HTTP ${xhr.status}).`));
          }
        });

        xhr.addEventListener("error", () => {
          clearInterval(timer);
          reject(new Error("Could not reach the server. Please make sure it is running."));
        });

        xhr.addEventListener("abort", () => {
          clearInterval(timer);
          reject(new Error("Upload aborted."));
        });
      });

      xhr.open("POST", "/generate-report");
      xhr.send(data);

      const body = await responsePromise;
      renderReport(body);
      saveHistory(body);
    } catch (err) {
      showAlert("error", err.message || "An error occurred.");
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  });

  renderHistory();
})();
