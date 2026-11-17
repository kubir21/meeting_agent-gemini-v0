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

  // Theme toggle (initial theme is set by the inline script in index.html)
  const themeBtn = $("theme-toggle");
  function syncThemeBtn() {
    const dark = document.documentElement.dataset.theme === "dark";
    themeBtn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    themeBtn.title = themeBtn.getAttribute("aria-label");
  }
  themeBtn.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("vi_theme", next); } catch { /* ignore */ }
    syncThemeBtn();
  });
  syncThemeBtn();

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
    btnLabel.textContent = on ? "Generating..." : "Generate report";
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
    const cat = r.category && r.category !== "Not mentioned" ? r.category : "Employee Wellbeing Report";
    $("r-sub").textContent = cat;
    $("r-id").textContent = r.report_id;

    const tiles = [
      ["Category", r.category || "Not mentioned"],
      ["Duration", r.meta?.duration || "Not available"],
      ["Language", r.meta?.language || "Not available"],
      ["Report ID", r.report_id],
    ];
    $("r-tiles").innerHTML = tiles.map(([k, v]) =>
      `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");

    resetEmailBox();

    $("r-summary-wrap").hidden = !r.summary;
    $("r-summary").textContent = r.summary || "";

    const timelineWrap = $("r-timeline-wrap");
    const timelineEl = $("r-timeline");
    if (timelineWrap && timelineEl) {
      if (r.timeline && r.timeline.length > 0) {
        timelineWrap.hidden = false;
        timelineEl.innerHTML = r.timeline.map((item) => `
          <div class="timeline-item">
            <span class="timeline-ts">${esc(item.timestamp_range)}</span>
            <span class="timeline-title">${esc(item.topic)}</span>
            ${item.has_slides ? '<span class="timeline-badge">Presentation Slides</span>' : ''}
          </div>
        `).join("");
      } else {
        timelineWrap.hidden = true;
      }
    }

    $("r-qa").innerHTML = (r.qa || []).map((q, i) => `
      <div class="qa-card">
        <div class="qa-label q">
          Question ${i + 1}
          ${q.timestamp ? `<span class="qa-ts">${esc(q.timestamp)}</span>` : ""}
        </div>
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
    $("nav-history").hidden = list.length === 0;
    historyList.innerHTML = list.map((h) => `
      <li data-id="${esc(h.report_id)}">
        <div class="h-main">
          <div class="h-title">${esc(h.company)}</div>
          <div class="h-meta">${esc(h.category || "Wellbeing Report")}  |  ${esc(h.report_id)}</div>
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

  // Email section
  const EMAIL_KEY = "video_insights_last_email_v1";
  const EMAIL_RE = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$/;
  const emailInput = $("email-input"), emailBtn = $("email-send"), emailGroup = $("email-group");
  const emailHint = $("email-hint"), emailStatus = $("email-status");
  const HINT_DEFAULT = "Sent from rk26.ftw@gmail.com";
  let emailSending = false;

  const validEmail = (v) => v.length <= 254 && !v.includes("..") && EMAIL_RE.test(v);

  function refreshEmailUi() {
    const v = emailInput.value.trim();
    const ok = validEmail(v);
    const showInvalid = v.length > 0 && !ok;
    emailGroup.classList.toggle("invalid", showInvalid);
    emailHint.classList.toggle("error", showInvalid);
    emailHint.textContent = showInvalid ? "Please enter a valid email address." : HINT_DEFAULT;
    emailBtn.disabled = !ok || emailSending || !current;
  }
  function setEmailStatus(type, msg) {
    emailStatus.className = `email-status ${type}`;
    emailStatus.textContent = msg;
    emailStatus.hidden = false;
  }
  function resetEmailBox() {
    emailStatus.hidden = true;
    emailSending = false;
    emailBtn.classList.remove("loading");
    emailInput.disabled = false;
    try { emailInput.value = localStorage.getItem(EMAIL_KEY) || ""; } catch { emailInput.value = ""; }
    refreshEmailUi();
  }
  async function sendEmail() {
    const to = emailInput.value.trim();
    if (!current || emailSending || !validEmail(to)) return;
    emailSending = true;
    emailStatus.hidden = true;
    emailBtn.classList.add("loading");
    emailInput.disabled = true;
    refreshEmailUi();
    try {
      const res = await fetch("/send-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: to,
          report_id: current.report_id,
          company: current.company,
          source_file: current.source_file || "",
          pdf_base64: current.pdf_base64,
        }),
      });
      let body = {};
      try { body = await res.json(); } catch { /* non-JSON response */ }
      if (!res.ok || body.status !== "success") {
        throw new Error(body.detail || `Could not send the email (HTTP ${res.status}).`);
      }
      try { localStorage.setItem(EMAIL_KEY, to); } catch { /* ignore */ }
      setEmailStatus("ok", `Report sent to ${body.recipient || to}. If you do not see it, check the spam folder.`);
    } catch (err) {
      const msg = err instanceof TypeError ? "Could not reach the server. Please make sure it is running." : err.message;
      setEmailStatus("err", msg);
    } finally {
      emailSending = false;
      emailBtn.classList.remove("loading");
      emailInput.disabled = false;
      refreshEmailUi();
    }
  }
  emailInput.addEventListener("input", () => { emailStatus.hidden = true; refreshEmailUi(); });
  emailInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendEmail(); } });
  emailBtn.addEventListener("click", sendEmail);

  // S3 Multipart Upload helpers
  const PART_SIZE = 10 * 1024 * 1024; // 10MB per part

  async function checkAppConfig() {
    try {
      const res = await fetch("/app-config");
      if (res.ok) return await res.json();
    } catch { /* ignore */ }
    return { s3_enabled: false };
  }

  async function parseResponsePayload(res, fallbackText) {
    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      const text = await res.text().catch(() => "");
      data = { detail: text || `HTTP ${res.status} ${res.statusText || fallbackText}` };
    }
    return data;
  }

  function getErrorMessage(res, data, defaultMsg) {
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map(d => (typeof d === "object" ? d.msg || JSON.stringify(d) : String(d))).join("; ");
    }
    if (data.error && typeof data.error.message === "string") return data.error.message;
    if (typeof data.message === "string" && data.message.trim()) return data.message;
    if (typeof data.error === "string" && data.error.trim()) return data.error;
    return `${defaultMsg} (HTTP ${res.status})`;
  }

  function uploadPartWithProgress(url, chunk, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", url);
      xhr.upload.addEventListener("progress", (ev) => {
        if (ev.lengthComputable) onProgress(ev.loaded);
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const rawEtag = xhr.getResponseHeader("ETag") || xhr.getResponseHeader("etag") || "";
          const etag = rawEtag.trim().replace(/^"|"$/g, "");
          if (!etag) {
            reject(new Error("Missing ETag header from S3. Please verify S3 CORS includes ExposeHeaders: ['ETag']."));
          } else {
            resolve(etag);
          }
        } else {
          reject(new Error(`S3 upload error for part (HTTP ${xhr.status}).`));
        }
      });
      xhr.addEventListener("error", () => reject(new Error("Network error during S3 chunk upload.")));
      xhr.addEventListener("abort", () => reject(new Error("Upload aborted.")));
      xhr.send(chunk);
    });
  }

  async function uploadToS3AndAnalyze(file) {
    // 1. Initiate upload
    const initRes = await fetch("/s3/initiate-upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, content_type: file.type || "video/mp4" }),
    });
    const initData = await parseResponsePayload(initRes, "Initiate failed");
    if (!initRes.ok || initData.status !== "success") {
      throw new Error(getErrorMessage(initRes, initData, "Failed to initiate cloud storage upload."));
    }
    const { key, upload_id } = initData;

    try {
      // 2. Upload chunks in parallel/sequence
      const totalSize = file.size;
      const numParts = Math.max(1, Math.ceil(totalSize / PART_SIZE));
      const parts = [];
      const partLoaded = new Array(numParts).fill(0);

      const updateOverallProgress = () => {
        const totalUploaded = partLoaded.reduce((a, b) => a + b, 0);
        const uploadPct = Math.min(42, (totalUploaded / totalSize) * 42);
        setProgress(uploadPct, `Uploading directly to cloud storage (${fmtSize(totalUploaded)} / ${fmtSize(totalSize)})...`);
      };

      for (let i = 1; i <= numParts; i++) {
        const start = (i - 1) * PART_SIZE;
        const end = Math.min(start + PART_SIZE, totalSize);
        const chunk = file.slice(start, end);

        // Sign part URL
        const signRes = await fetch("/s3/sign-part", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key, upload_id, part_number: i }),
        });
        const signData = await parseResponsePayload(signRes, "Sign part failed");
        if (!signRes.ok || signData.status !== "success") {
          throw new Error(getErrorMessage(signRes, signData, `Failed to sign upload part ${i}.`));
        }

        // Upload chunk
        const etag = await uploadPartWithProgress(signData.url, chunk, (loaded) => {
          partLoaded[i - 1] = loaded;
          updateOverallProgress();
        });
        partLoaded[i - 1] = chunk.size;
        updateOverallProgress();
        parts.push({ PartNumber: i, ETag: etag });
      }

      // 3. Complete multipart upload
      setProgress(44, "Finalizing cloud storage transfer...");
      const compRes = await fetch("/s3/complete-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, upload_id, parts }),
      });
      const compData = await parseResponsePayload(compRes, "Complete failed");
      if (!compRes.ok || compData.status !== "success") {
        throw new Error(getErrorMessage(compRes, compData, "Failed to finalize cloud storage upload."));
      }

      // 4. Trigger Analysis
      setStep(1);
      setProgress(45, "Reviewing audio, video, and presentation slides...");
      let currentPct = 45;
      timer = setInterval(() => {
        if (currentPct < 75) {
          currentPct += 1.5;
          setProgress(currentPct, "Analysing video and identifying Six Pillars...");
        } else if (currentPct < 92) {
          currentPct += 0.5;
          setStep(2);
          setProgress(currentPct, "Synthesising findings and generating PDF...");
        }
      }, 1000);

      const analyzeRes = await fetch("/analyze-s3-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, original_filename: file.name }),
      });
      clearInterval(timer);
      const analyzeData = await parseResponsePayload(analyzeRes, "Analysis failed");
      if (!analyzeRes.ok || analyzeData.status !== "success") {
        throw new Error(getErrorMessage(analyzeRes, analyzeData, "Analysis failed."));
      }

      setProgress(100, "Done!");
      setStep(3);
      return analyzeData;
    } catch (err) {
      fetch("/s3/abort-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, upload_id }),
      }).catch(() => {});
      throw err;
    }
  }

  function uploadFallbackLocal(file) {
    const data = new FormData();
    data.append("file", file);

    const xhr = new XMLHttpRequest();
    return new Promise((resolve, reject) => {
      xhr.upload.addEventListener("progress", (ev) => {
        if (ev.lengthComputable) {
          const uploadPct = (ev.loaded / ev.total) * 40;
          setProgress(uploadPct, `Uploading video (${fmtSize(ev.loaded)} / ${fmtSize(ev.total)})...`);
          if (uploadPct >= 38) setStep(1);
        }
      });

      xhr.upload.addEventListener("load", () => {
        setStep(1);
        setProgress(40, "Upload complete. Reviewing audio and video...");
        let currentPct = 40;
        timer = setInterval(() => {
          if (currentPct < 75) {
            currentPct += 1.5;
            setProgress(currentPct, "Analysing video content...");
          } else if (currentPct < 92) {
            currentPct += 0.5;
            setStep(2);
            setProgress(currentPct, "Preparing your report...");
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
        } catch {
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

      xhr.open("POST", "/generate-report");
      xhr.send(data);
    });
  }

  // Phase 2: Client-side 360p video compression
  async function compressVideoTo360p(file, onProgress, signal) {
    if (typeof MediaRecorder === "undefined" || !file || file.size < 15 * 1024 * 1024) {
      return file;
    }
    const candidates = [
      "video/webm;codecs=vp8,opus",
      "video/webm;codecs=vp9,opus",
      "video/webm",
      "video/mp4",
    ];
    let mimeType = "";
    for (const c of candidates) {
      if (MediaRecorder.isTypeSupported(c)) {
        mimeType = c;
        break;
      }
    }
    if (!mimeType) return file;

    return new Promise((resolve) => {
      let aborted = false;
      let animId = null;
      const video = document.createElement("video");
      video.preload = "metadata";
      video.src = URL.createObjectURL(file);
      video.muted = true;
      video.playsInline = true;

      function cleanup() {
        aborted = true;
        if (animId) cancelAnimationFrame(animId);
        try { video.pause(); } catch {}
        try { URL.revokeObjectURL(video.src); } catch {}
      }

      if (signal) {
        signal.addEventListener("abort", () => {
          cleanup();
          resolve(file);
        });
      }

      video.onloadedmetadata = async () => {
        if (aborted) return;
        if (video.videoHeight <= 360) {
          cleanup();
          resolve(file);
          return;
        }

        const targetHeight = 360;
        const targetWidth = Math.round((video.videoWidth / video.videoHeight) * 360) & ~1;
        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        const ctx = canvas.getContext("2d");

        const canvasStream = canvas.captureStream ? canvas.captureStream(8) : null;
        if (!canvasStream) {
          cleanup();
          resolve(file);
          return;
        }

        try {
          const recorder = new MediaRecorder(canvasStream, {
            mimeType,
            videoBitsPerSecond: 350000,
          });
          const chunks = [];
          recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) chunks.push(e.data);
          };
          recorder.onstop = () => {
            cleanup();
            if (aborted) {
              resolve(file);
              return;
            }
            const blob = new Blob(chunks, { type: mimeType });
            if (blob.size > 0 && blob.size < file.size) {
              const ext = mimeType.includes("mp4") ? ".mp4" : ".webm";
              const newName = file.name.replace(/\.[^.]+$/, "") + "_360p" + ext;
              resolve(new File([blob], newName, { type: mimeType }));
            } else {
              resolve(file);
            }
          };

          recorder.start(500);
          video.playbackRate = 4.0;
          await video.play();

          const draw = () => {
            if (aborted || video.paused || video.ended) return;
            ctx.drawImage(video, 0, 0, targetWidth, targetHeight);
            if (onProgress && video.duration && !aborted) {
              const pct = (video.currentTime / video.duration) * 100;
              onProgress(pct);
            }
            if (!aborted) animId = requestAnimationFrame(draw);
          };
          animId = requestAnimationFrame(draw);

          video.onended = () => {
            try { recorder.stop(); } catch {}
          };
          video.onerror = () => { cleanup(); resolve(file); };
        } catch {
          cleanup();
          resolve(file);
        }
      };
      video.onerror = () => { cleanup(); resolve(file); };
    });
  }

  // Submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    alertBox.hidden = true;
    setLoading(true);

    try {
      let fileToUpload = selectedFile;
      const compressToggle = $("compress-toggle");
      if (compressToggle && compressToggle.checked && selectedFile.size > 20 * 1024 * 1024) {
        setProgress(3, "Optimizing video resolution to 360p...");
        const abortCtrl = new AbortController();
        try {
          const compTask = compressVideoTo360p(selectedFile, (pct) => {
            setProgress(3 + (pct * 0.12), `Optimizing video to 360p (${Math.round(pct)}%)...`);
          }, abortCtrl.signal);
          const timeoutTask = new Promise((res) => setTimeout(() => {
            abortCtrl.abort();
            res(selectedFile);
          }, 15000));
          fileToUpload = await Promise.race([compTask, timeoutTask]);
        } catch {
          abortCtrl.abort();
          fileToUpload = selectedFile;
        }
      }

      const cfg = await checkAppConfig();
      let body;
      if (cfg && cfg.s3_enabled) {
        body = await uploadToS3AndAnalyze(fileToUpload);
      } else {
        body = await uploadFallbackLocal(fileToUpload);
      }
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
