(() => {
  const DEBUG = false;
  const SCAN_FPS = 10;
  const REPEAT_DEBOUNCE_MS = 3000;

  const state = {
    stream: null,
    track: null,
    video: null,
    canvas: null,
    ctx: null,
    rafId: null,
    scanIntervalMs: Math.round(1000 / SCAN_FPS),
    lastScanAt: 0,
    lastCode: "",
    lastCodeAt: 0,
    detector: null,
    running: false,
  };

  const dom = {
    out: document.getElementById("out"),
    baseUrl: document.getElementById("baseUrl"),
    apiKey: document.getElementById("apiKey"),
    userEmail: document.getElementById("userEmail"),
    materialId: document.getElementById("materialId"),
    reader: document.getElementById("reader"),
    overlayCard: document.getElementById("overlayCard"),
    matName: document.getElementById("matName"),
    matLab: document.getElementById("matLab"),
    matLocation: document.getElementById("matLocation"),
    matPieces: document.getElementById("matPieces"),
    matStatus: document.getElementById("matStatus"),
    scanStatus: document.getElementById("scanStatus"),
    startBtn: document.getElementById("start-camera-btn"),
    stopBtn: document.getElementById("stop-camera-btn"),
    cameraSelect: document.getElementById("cameraSelect"),
    cameraHint: document.getElementById("cameraHint"),
  };

  const log = (...args) => {
    if (DEBUG) {
      console.log("[QR]", ...args);
    }
  };

  const out = (obj) => {
    if (!dom.out) return;
    dom.out.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  };

  const getBaseUrl = () => (dom.baseUrl?.value || "").trim().replace(/\/$/, "");
  const headers = () => ({ "X-API-Key": (dom.apiKey?.value || "").trim() });

  const ensureScanOverlay = () => {
    if (!dom.reader || document.getElementById("scanGuide")) return;
    dom.reader.style.position = "relative";
    dom.reader.style.minHeight = "220px";
    dom.reader.style.background = "#0b2c170f";
    dom.reader.style.border = "1px dashed #0F3D1F";
    dom.reader.style.borderRadius = "10px";

    const guide = document.createElement("div");
    guide.id = "scanGuide";
    guide.style.position = "absolute";
    guide.style.inset = "12px";
    guide.style.border = "2px solid #00BCD4";
    guide.style.borderRadius = "8px";
    guide.style.pointerEvents = "none";
    guide.style.boxShadow = "0 0 0 999px rgba(11,44,23,0.15) inset";

    const text = document.createElement("div");
    text.id = "scanGuideText";
    text.textContent = "Alinea el QR dentro del recuadro";
    text.style.position = "absolute";
    text.style.left = "50%";
    text.style.bottom = "16px";
    text.style.transform = "translateX(-50%)";
    text.style.background = "rgba(11,44,23,0.85)";
    text.style.color = "#fff";
    text.style.padding = "6px 10px";
    text.style.borderRadius = "6px";
    text.style.fontSize = "12px";
    text.style.pointerEvents = "none";

    dom.reader.appendChild(guide);
    dom.reader.appendChild(text);
  };

  const beep = () => {
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.value = 0.02;
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.start();
      setTimeout(() => {
        osc.stop();
        ac.close();
      }, 90);
    } catch (_) {
      // noop
    }
  };

  const feedbackDetected = () => {
    if ("vibrate" in navigator) navigator.vibrate(60);
    beep();
  };

  async function getMaterial() {
    const baseUrl = getBaseUrl();
    const id = dom.materialId?.value;

    try {
      const res = await fetch(`${baseUrl}/api/ra/materials/${id}`, {
        method: "GET",
        headers: headers(),
      });
      const data = await res.json().catch(() => null);
      out({ status: res.status, data });
    } catch (e) {
      out(String(e));
    }
  }

  async function postEvent() {
    const baseUrl = getBaseUrl();
    const id = Number(dom.materialId?.value);
    const userEmail = (dom.userEmail?.value || "").trim().toLowerCase();

    const body = {
      material_id: id,
      event_type: "scan",
      user_email: userEmail,
      metadata: { device: "web-client", marker: `manual:${id}` },
    };

    try {
      const res = await fetch(`${baseUrl}/api/ra/events`, {
        method: "POST",
        headers: { ...headers(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => null);
      out({ status: res.status, data });
    } catch (e) {
      out(String(e));
    }
  }

  function extractMaterialId(text) {
    const t = String(text || "").trim();
    if (/^\d+$/.test(t)) return Number(t);
    const m1 = t.match(/material\D*(\d+)/i);
    if (m1) return Number(m1[1]);
    const m2 = t.match(/[?&]id=(\d+)/i);
    if (m2) return Number(m2[1]);
    const m3 = t.match(/(\d+)(?!.*\d)/);
    if (m3) return Number(m3[1]);
    return null;
  }

  const isRepeatedCode = (code) => {
    const now = Date.now();
    if (state.lastCode === code && now - state.lastCodeAt < REPEAT_DEBOUNCE_MS) {
      return true;
    }
    state.lastCode = code;
    state.lastCodeAt = now;
    return false;
  };

  async function getMaterialById(id) {
    const baseUrl = getBaseUrl();
    const res = await fetch(`${baseUrl}/api/ra/materials/${id}`, {
      method: "GET",
      headers: headers(),
    });
    const data = await res.json().catch(() => null);
    return { status: res.status, data };
  }

  async function postScanEvent(id, markerText) {
    const baseUrl = getBaseUrl();
    const userEmail = (dom.userEmail?.value || "").trim().toLowerCase();
    const body = {
      material_id: id,
      event_type: "scan",
      user_email: userEmail,
      metadata: { device: "qr-web", marker: markerText },
    };

    const res = await fetch(`${baseUrl}/api/ra/events`, {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json().catch(() => null);
    return { status: res.status, data };
  }

  async function handleDecodedText(decodedText) {
    if (!decodedText || isRepeatedCode(decodedText)) return;

    const id = extractMaterialId(decodedText);
    if (!id || Number.isNaN(id)) {
      out({ warning: "QR inválido", decodedText });
      return;
    }

    feedbackDetected();

    try {
      const mat = await getMaterialById(id);
      const ev = await postScanEvent(id, decodedText);

      if (dom.overlayCard && dom.matName && dom.matLab && dom.matLocation && dom.matPieces && dom.matStatus && dom.scanStatus) {
        dom.overlayCard.style.display = "block";
      }

      if (mat.status === 200 && mat.data) {
        const m = mat.data;
        if (dom.matName) dom.matName.textContent = m.name || "Sin nombre";
        if (dom.matLab) dom.matLab.textContent = m.lab || "-";
        if (dom.matLocation) dom.matLocation.textContent = m.location || "-";
        if (dom.matPieces) dom.matPieces.textContent = m.pieces_qty || m.pieces_text || "-";
        if (dom.matStatus) dom.matStatus.textContent = m.status || "-";

        if (dom.scanStatus) {
          if (ev.status === 201) {
            dom.scanStatus.style.color = "green";
            dom.scanStatus.textContent = "✔ Escaneo registrado correctamente.";
          } else if (ev.status === 403) {
            dom.scanStatus.style.color = "red";
            dom.scanStatus.textContent = "⛔ Usuario con adeudo activo.";
          } else {
            dom.scanStatus.style.color = "orange";
            dom.scanStatus.textContent = "⚠ Evento no registrado.";
          }
        }
      } else {
        out({ error: "Material no encontrado", mat });
      }
    } catch (err) {
      out({ error: "Error procesando QR", detail: String(err) });
    }
  }

  const clearScanLoop = () => {
    if (state.rafId) {
      cancelAnimationFrame(state.rafId);
      state.rafId = null;
    }
  };

  const stopMediaTracks = () => {
    if (state.stream) {
      state.stream.getTracks().forEach((t) => t.stop());
    }
    state.stream = null;
    state.track = null;
  };

  async function scanLoop() {
    if (!state.running || !state.video || !state.ctx || !state.canvas || !state.detector) return;

    const now = performance.now();
    if (now - state.lastScanAt >= state.scanIntervalMs) {
      state.lastScanAt = now;
      try {
        if (state.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          state.canvas.width = state.video.videoWidth;
          state.canvas.height = state.video.videoHeight;
          state.ctx.drawImage(state.video, 0, 0, state.canvas.width, state.canvas.height);

          const barcodes = await state.detector.detect(state.canvas);
          if (barcodes && barcodes.length > 0) {
            const text = (barcodes[0].rawValue || "").trim();
            log("barcode detected", text);
            await handleDecodedText(text);
          }
        }
      } catch (e) {
        log("scan loop error", e);
      }
    }

    if (state.running) {
      state.rafId = requestAnimationFrame(scanLoop);
    }
  }

  async function populateCameraOptions() {
    if (!dom.cameraSelect) return;

    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videos = devices.filter((d) => d.kind === "videoinput");

      dom.cameraSelect.innerHTML = "";
      videos.forEach((d, idx) => {
        const option = document.createElement("option");
        option.value = d.deviceId;
        option.textContent = d.label || `Cámara ${idx + 1}`;
        dom.cameraSelect.appendChild(option);
      });

      if (dom.cameraHint) {
        dom.cameraHint.textContent = videos.length > 1
          ? "Puedes cambiar de cámara antes de iniciar."
          : "Se detectó una cámara.";
      }
    } catch (e) {
      log("enumerateDevices failed", e);
    }
  }

  function getPreferredConstraints() {
    const selectedDevice = dom.cameraSelect?.value;
    if (selectedDevice) {
      return { video: { deviceId: { exact: selectedDevice } }, audio: false };
    }
    return { video: { facingMode: { ideal: "environment" } }, audio: false };
  }

  async function startCamera() {
    if (state.running) {
      out({ ok: true, msg: "La cámara ya está activa." });
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      out("Este navegador no soporta acceso a cámara (getUserMedia).");
      return;
    }

    if (!window.BarcodeDetector) {
      out("Este navegador no soporta BarcodeDetector. Usa Chrome/Edge recientes.");
      return;
    }

    try {
      const formats = await window.BarcodeDetector.getSupportedFormats();
      if (!formats.includes("qr_code")) {
        out("El navegador no soporta formato qr_code en BarcodeDetector.");
        return;
      }
    } catch (e) {
      log("getSupportedFormats error", e);
    }

    try {
      ensureScanOverlay();
      state.detector = new window.BarcodeDetector({ formats: ["qr_code"] });
      state.stream = await navigator.mediaDevices.getUserMedia(getPreferredConstraints());
      state.track = state.stream.getVideoTracks()[0] || null;

      state.video = document.createElement("video");
      state.video.setAttribute("playsinline", "true");
      state.video.muted = true;
      state.video.autoplay = true;
      state.video.srcObject = state.stream;
      state.video.style.width = "100%";
      state.video.style.height = "auto";
      state.video.style.borderRadius = "10px";
      state.video.style.objectFit = "cover";

      if (dom.reader) {
        const oldVideo = dom.reader.querySelector("video");
        if (oldVideo) oldVideo.remove();
        dom.reader.insertBefore(state.video, dom.reader.firstChild);
      }

      await state.video.play();

      state.canvas = document.createElement("canvas");
      state.ctx = state.canvas.getContext("2d", { willReadFrequently: true });
      state.running = true;
      state.lastScanAt = 0;
      state.lastCode = "";
      state.lastCodeAt = 0;
      await populateCameraOptions();

      state.rafId = requestAnimationFrame(scanLoop);
      out({ ok: true, msg: "Cámara iniciada. Escanea un QR." });
    } catch (e) {
      clearScanLoop();
      stopMediaTracks();
      state.running = false;

      if (String(e.name || "").toLowerCase().includes("notallowed")) {
        out("Permiso de cámara bloqueado. Habilita el permiso del navegador para continuar.");
      } else if (String(e.name || "").toLowerCase().includes("notfound")) {
        out("No se encontró una cámara disponible en este dispositivo.");
      } else {
        out({ error: "No pude iniciar cámara", detail: String(e) });
      }
    }
  }

  async function stopCamera() {
    state.running = false;
    clearScanLoop();

    try {
      if (state.video) {
        state.video.pause();
        state.video.srcObject = null;
        if (state.video.parentElement) state.video.parentElement.removeChild(state.video);
      }
    } catch (e) {
      log("video stop error", e);
    }

    stopMediaTracks();

    state.video = null;
    state.canvas = null;
    state.ctx = null;
    state.detector = null;

    out({ ok: true, msg: "Cámara detenida" });
  }

  const wireEvents = () => {
    if (dom.startBtn) dom.startBtn.addEventListener("click", startCamera);
    if (dom.stopBtn) dom.stopBtn.addEventListener("click", stopCamera);

    const getBtn = document.getElementById("get-material-btn");
    const postBtn = document.getElementById("post-event-btn");
    if (getBtn) getBtn.addEventListener("click", getMaterial);
    if (postBtn) postBtn.addEventListener("click", postEvent);

    if (dom.cameraSelect) {
      dom.cameraSelect.addEventListener("change", async () => {
        if (state.running) {
          await stopCamera();
          await startCamera();
        }
      });
    }
  };

  wireEvents();
  populateCameraOptions();

  window.getMaterial = getMaterial;
  window.postEvent = postEvent;
  window.startCamera = startCamera;
  window.stopCamera = stopCamera;
})();
