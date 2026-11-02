(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const DEFAULTS = {
    server: "http://xserver:9931/v1",
    model: "default",
    modalities: "text,audio",
    voice: "female",
    lang: "pt",
    instructions: "",
    vad: false,
    threshold: 25,
    transcribe: true,
    vadBargeIn: true,
  };

  const STORAGE_KEY = "naji.settings.v1";
  const VAD_MIN_SPEECH_MS = 180;
  const VAD_RELEASE_MS = 600;
  const VAD_PREROLL_MS = 500;
  const VAD_ONSET_GAP_MS = 200;
  const VAD_BARGE_GAP_MS = 140;
  const VAD_BARGE_FACTOR = 1.35;
  const MAX_TURN_MS = 30000;
  const MAX_OUTPUT_TOKENS = 512;
  const MAX_RESPONSE_MS = 60000;
  const RESPONSE_STALL_MS = 25000;
  const CANCEL_GRACE_MS = 5000;

  const state = {
    cfg: null,
    settings: { ...DEFAULTS },
    ws: null,
    ready: false,
    readyPromise: null,
    resolveReady: null,
    rejectReady: null,
    session: null,
    inRate: 24000,
    outRate: 24000,
    captureCtx: null,
    captureNode: null,
    captureTask: null,
    captureTargetRate: 0,
    mediaStream: null,
    resampler: null,
    pending: new Int16Array(0),
    sending: false,
    turnSamples: 0,
    tLast: 0,
    turnCount: 0,
    bytesSent: 0,
    muted: false,
    pttHeld: false,
    starting: false,
    vadActive: false,
    lastVoice: 0,
    responding: false,
    current: null,
    outCtx: null,
    sources: new Set(),
    playing: false,
    nextPlayAt: 0,
    level: 0,
    wave: [],
    events: [],
    ttsChunks: [],
    ttsRate: 0,
    ttsController: null,
    fileAbort: false,
    lastLatency: null,
    turnAudio: [],
    collectAudio: false,
    preroll: [],
    prerollSamples: 0,
    vadSince: 0,
    bargeSince: 0,
    noiseFloor: 0.002,
    levelHistory: [],
    levelCount: 0,
    vadReadyAt: 0,
    turnStartedAt: 0,
    responseStartedAt: 0,
    lastEventAt: 0,
    cancelSentAt: 0,
    waitingSince: 0,
    responseId: null,
    reconnectTimer: null,
    reconnectTries: 0,
  };

  const els = {
    badges: {
      health: $("badge-health"),
      build: $("badge-build"),
      model: $("badge-model"),
      realtime: $("badge-realtime"),
      tts: $("badge-tts"),
    },
    check: $("btn-check"),
    settingsBtn: $("btn-settings"),
    settings: $("settings"),
    settingsClose: $("btn-settings-close"),
    settingsSave: $("btn-settings-save"),
    settingsReset: $("btn-settings-reset"),
    setServer: $("set-server"),
    setModel: $("set-model"),
    setModalities: $("set-modalities"),
    setVoice: $("set-voice"),
    setLang: $("set-lang"),
    setInstructions: $("set-instructions"),
    setTranscribe: $("set-transcribe"),
    setBarge: $("set-barge"),
    messages: $("messages"),
    emptyChat: $("empty-chat"),
    ptt: $("ptt"),
    vad: $("vad"),
    threshold: $("threshold"),
    thresholdVal: $("threshold-val"),
    mute: $("btn-mute"),
    cancel: $("btn-cancel"),
    wave: $("wave"),
    stateLabel: $("state-label"),
    pulse: $("pulse"),
    checkDetails: $("check-details"),
    metrics: $("metrics"),
    events: $("events"),
    clearEvents: $("btn-clear-events"),
    ttsText: $("tts-text"),
    ttsVoice: $("tts-voice"),
    ttsLang: $("tts-lang"),
    ttsBtn: $("btn-tts"),
    ttsStop: $("btn-tts-stop"),
    ttsSave: $("btn-tts-save"),
    ttsMeta: $("tts-meta"),
    fileInput: $("file-input"),
    fileBtn: $("btn-file"),
    fileStop: $("btn-file-stop"),
    fileMeta: $("file-meta"),
    toast: $("toast"),
  };

  function readStored() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    } catch (err) {
      return {};
    }
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.settings));
    } catch (err) {
      /* ignore */
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function rms(samples) {
    if (!samples || !samples.length) return 0;
    let sum = 0;
    const step = Math.max(1, Math.floor(samples.length / 512));
    let count = 0;
    for (let i = 0; i < samples.length; i += step) {
      const value = samples[i] / 32768;
      sum += value * value;
      count++;
    }
    return Math.sqrt(sum / Math.max(1, count));
  }

  function thresholdValue() {
    return 0.002 + ((Number(state.settings.threshold) - 1) / 99) * 0.078;
  }

  function effectiveThreshold() {
    return Math.max(thresholdValue(), Math.min(state.noiseFloor * 1.8, 0.02));
  }

  function updateNoiseFloor(level) {
    state.levelHistory.push(level);
    if (state.levelHistory.length > 250) state.levelHistory.shift();
    state.levelCount += 1;
    if (state.levelCount % 48 !== 0 || state.levelHistory.length < 32) return;
    const sorted = state.levelHistory.slice().sort((a, b) => a - b);
    state.noiseFloor = clamp(sorted[Math.floor(sorted.length * 0.2)], 0.0005, 0.05);
  }

  function pushPreroll(samples) {
    if (!samples || !samples.length) return;
    state.preroll.push(samples);
    state.prerollSamples += samples.length;
    const cap = Math.max(1, Math.round((state.inRate * VAD_PREROLL_MS) / 1000));
    while (state.prerollSamples > cap && state.preroll.length > 1) {
      state.prerollSamples -= state.preroll[0].length;
      state.preroll.shift();
    }
  }

  function flushPreroll() {
    const parts = state.preroll;
    state.preroll = [];
    state.prerollSamples = 0;
    for (const part of parts) appendPending(part);
  }

  function resetVad() {
    state.vadActive = false;
    state.vadSince = 0;
    state.bargeSince = 0;
    state.preroll = [];
    state.prerollSamples = 0;
    state.levelHistory = [];
    state.levelCount = 0;
    state.noiseFloor = 0.002;
    state.vadReadyAt = performance.now() + 600;
  }

  function modalities() {
    return String(state.settings.modalities || "text,audio")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function int16FromB64(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
  }

  function b64FromInt16(view) {
    const bytes = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
    let binary = "";
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    }
    return btoa(binary);
  }

  function floatToInt16(input) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      out[i] = clamp(Math.round(input[i] * 32767), -32768, 32767);
    }
    return out;
  }

  function concatInt16(parts) {
    const total = parts.reduce((sum, part) => sum + part.length, 0);
    const out = new Int16Array(total);
    let offset = 0;
    for (const part of parts) {
      out.set(part, offset);
      offset += part.length;
    }
    return out;
  }

  function concatBytes(a, b) {
    const out = new Uint8Array(a.length + b.length);
    out.set(a);
    out.set(b, a.length);
    return out;
  }

  function resampleArray(samples, srcRate, dstRate) {
    if (srcRate === dstRate || !samples.length) return samples;
    const count = Math.round((samples.length * dstRate) / srcRate);
    const out = new Int16Array(count);
    const ratio = srcRate / dstRate;
    for (let i = 0; i < count; i++) {
      const pos = i * ratio;
      const index = Math.floor(pos);
      const frac = pos - index;
      const a = samples[Math.min(index, samples.length - 1)];
      const b = samples[Math.min(index + 1, samples.length - 1)];
      out[i] = clamp(Math.round(a * (1 - frac) + b * frac), -32768, 32767);
    }
    return out;
  }

  class Resampler {
    constructor(srcRate, dstRate) {
      this.ratio = srcRate / dstRate;
      this.buffer = new Float32Array(0);
      this.pos = 0;
    }

    process(samples) {
      const incoming = new Float32Array(samples.length);
      for (let i = 0; i < samples.length; i++) incoming[i] = samples[i];
      const buffer = new Float32Array(this.buffer.length + incoming.length);
      buffer.set(this.buffer);
      buffer.set(incoming, this.buffer.length);
      const out = [];
      let pos = this.pos;
      while (pos + 1 < buffer.length) {
        const index = Math.floor(pos);
        const frac = pos - index;
        out.push(buffer[index] * (1 - frac) + buffer[index + 1] * frac);
        pos += this.ratio;
      }
      const drop = Math.floor(pos);
      this.buffer = buffer.slice(drop);
      this.pos = pos - drop;
      const result = new Int16Array(out.length);
      for (let i = 0; i < out.length; i++) {
        result[i] = clamp(Math.round(out[i]), -32768, 32767);
      }
      return result;
    }
  }

  function wavBlob(samples, rate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const write = (offset, text) => {
      for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
    };
    write(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    write(8, "WAVE");
    write(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, rate, true);
    view.setUint32(28, rate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, "data");
    view.setUint32(40, samples.length * 2, true);
    new Int16Array(buffer, 44).set(samples);
    return new Blob([buffer], { type: "audio/wav" });
  }

  function download(blob, name) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.classList.remove("hidden");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => els.toast.classList.add("hidden"), 5000);
  }

  function setBadge(key, status, text) {
    const el = els.badges[key];
    if (!el) return;
    el.className = "badge " + status;
    el.textContent = text;
  }

  function setStateLabel(text) {
    els.stateLabel.textContent = text;
  }

  function setPulse(active) {
    els.pulse.classList.toggle("active", active);
  }

  function logEvent(direction, type, detail) {
    const entry = {
      time: new Date().toISOString(),
      direction,
      type,
      detail: detail || "",
    };
    state.events.push(entry);
    if (state.events.length > 300) state.events.shift();
    const line = document.createElement("div");
    line.className = "event";
    line.innerHTML =
      '<span class="t">' +
      entry.time.slice(11, 19) +
      "</span><span class=\"d " +
      (direction === "<-" ? "in" : direction === "->" ? "out" : "sys") +
      '">' +
      direction +
      "</span><span class=\"ty\">" +
      type +
      "</span>" +
      (detail ? '<span class="det">' + detail + "</span>" : "");
    els.events.appendChild(line);
    while (els.events.children.length > 300) els.events.removeChild(els.events.firstChild);
    els.events.scrollTop = els.events.scrollHeight;
    refreshMetrics();
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = text;
    }
    if (!response.ok) {
      const detail = data && data.detail ? data.detail : text || response.statusText;
      throw new Error(detail);
    }
    return data;
  }

  function renderCheck(result) {
    const rows = [];
    const health = result.health || {};
    const props = result.props || {};
    const model = result.model || {};
    const realtime = result.realtime || {};
    const tts = result.tts || null;

    const row = (label, value, status) =>
      '<div class="kv-row"><span>' + label + '</span><b class="' + (status || "") + '">' + value + "</b></div>";

    rows.push(row("endpoint", result.server || "—", ""));
    rows.push(
      row(
        "health",
        health.status === 200 ? "200 ok" : health.status || health.error || "erro",
        health.status === 200 ? "ok" : "err"
      )
    );
    if (props.build_info || props.version) {
      const build = props.build_info || props.version;
      const numbers = String(build).match(/b(\d{4,})/g) || [];
      const value = numbers.length ? numbers[numbers.length - 1] : build;
      rows.push(row("build", value, numbers.length && parseInt(numbers[numbers.length - 1].slice(1), 10) >= 11941 ? "ok" : "warn"));
    }
    if (props.model_path || props.model_alias) {
      rows.push(row("modelo", props.model_path || props.model_alias, ""));
    }
    if (model.id) {
      rows.push(row("model id", model.id, ""));
    }
    if (model.input_modalities) {
      rows.push(row("entrada", model.input_modalities.join(", "), ""));
    }
    if (model.output_modalities) {
      const hasAudio = model.output_modalities.includes("audio");
      rows.push(row("saída", model.output_modalities.join(", "), hasAudio ? "ok" : "warn"));
    }
    if (realtime.ok) {
      rows.push(
        row(
          "realtime",
          (realtime.in_rate || "?") + " Hz -> " + (realtime.out_rate || "?") + " Hz · " + realtime.ms + " ms",
          "ok"
        )
      );
    } else {
      rows.push(row("realtime", realtime.error || "falhou", "err"));
    }
    if (tts) {
      rows.push(row("tts", tts.ok ? tts.seconds + " s · " + tts.ms + " ms" : tts.error, tts.ok ? "ok" : "err"));
    }
    if (result.warnings && result.warnings.length) {
      for (const warning of result.warnings) rows.push(row("aviso", warning, "warn"));
    }
    if (result.errors && result.errors.length) {
      for (const error of result.errors) rows.push(row("erro", error, "err"));
    }
    els.checkDetails.innerHTML = rows.join("");

    setBadge("health", health.status === 200 ? "ok" : "err", health.status === 200 ? "health ok" : "health falhou");
    const build = String(props.build_info || props.version || "");
    const numbers = build.match(/b(\d{4,})/g) || [];
    if (!numbers.length) {
      setBadge("build", props.build_info ? "ok" : "warn", props.build_info ? "build ?" : "build ?");
    } else {
      const value = numbers[numbers.length - 1];
      const ok = parseInt(value.slice(1), 10) >= 11941;
      setBadge("build", ok ? "ok" : "warn", value);
    }
    if (model.id) {
      const short = model.id.split(/[\\/]/).pop().slice(0, 26);
      const hasAudio = (model.output_modalities || []).includes("audio");
      setBadge("model", hasAudio ? "ok" : "warn", short);
    } else {
      setBadge("model", "warn", "modelo ?");
    }
    setBadge("realtime", realtime.ok ? "ok" : "err", realtime.ok ? "realtime ok" : "realtime falhou");
    if (tts) {
      setBadge("tts", tts.ok ? "ok" : "err", tts.ok ? "tts ok" : "tts falhou");
    } else {
      setBadge("tts", "warn", "tts ?");
    }

    if (realtime.ok) {
      if (realtime.in_rate) state.inRate = realtime.in_rate;
      if (realtime.out_rate) state.outRate = realtime.out_rate;
      if (!state.settings.vad) primeCapture();
    }
    refreshMetrics();
  }

  async function runCheck() {
    els.check.disabled = true;
    els.check.textContent = "Verificando...";
    for (const key of Object.keys(els.badges)) setBadge(key, "pending", key);
    try {
      const params = new URLSearchParams({
        server: state.settings.server,
        model: state.settings.model || "default",
        tts: "true",
        wait: "15",
      });
      const result = await api("/api/check?" + params.toString());
      renderCheck(result);
      if (result.ok) toast("Servidor pronto para voz em tempo real.");
      else toast("Preflight com falhas: veja o painel lateral.");
    } catch (err) {
      els.checkDetails.innerHTML = '<div class="kv-row"><span>erro</span><b class="err">' + err.message + "</b></div>";
      for (const key of Object.keys(els.badges)) setBadge(key, "err", key + " falhou");
      toast("Falha ao verificar: " + err.message);
    } finally {
      els.check.disabled = false;
      els.check.textContent = "Verificar";
    }
  }

  function applySessionRates(session) {
    const audio = session && session.audio;
    if (!audio) return;
    const inRate = audio.input && audio.input.format && audio.input.format.rate;
    const outRate = audio.output && audio.output.format && audio.output.format.rate;
    if (inRate) state.inRate = inRate;
    if (outRate) state.outRate = outRate;
    refreshMetrics();
  }

  function resetSession() {
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
    state.ready = false;
    state.session = null;
    state.responding = false;
    state.responseStartedAt = 0;
    state.cancelSentAt = 0;
    state.waitingSince = 0;
    state.responseId = null;
    state.sending = false;
    state.turnStartedAt = 0;
    state.collectAudio = false;
    state.turnAudio = [];
    state.pending = new Int16Array(0);
    stopPlayback();
    if (state.ws) {
      try {
        state.ws.close();
      } catch (err) {
        /* ignore */
      }
    }
    state.ws = null;
    if (state.rejectReady) state.rejectReady(new Error("canal reiniciado"));
    state.resolveReady = null;
    state.rejectReady = null;
    state.readyPromise = null;
  }

  function connect() {
    if (state.ws && (state.ws.readyState === WebSocket.CONNECTING || state.ws.readyState === WebSocket.OPEN)) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const params = new URLSearchParams({
      server: state.settings.server,
      model: state.settings.model || "default",
    });
    const ws = new WebSocket(scheme + "://" + location.host + "/ws/realtime?" + params.toString());
    state.ws = ws;
    state.ready = false;
    state.readyPromise = new Promise((resolve, reject) => {
      state.resolveReady = resolve;
      state.rejectReady = reject;
    });
    ws.onopen = () => {
      if (state.ws !== ws) return;
      logEvent("sistema", "canal aberto");
    };
    ws.onclose = () => {
      if (state.ws !== ws) return;
      state.ws = null;
      state.ready = false;
      state.session = null;
      state.responding = false;
      state.responseStartedAt = 0;
      state.cancelSentAt = 0;
      state.waitingSince = 0;
      state.responseId = null;
      state.sending = false;
      state.turnStartedAt = 0;
      state.collectAudio = false;
      state.turnAudio = [];
      state.pending = new Int16Array(0);
      stopPlayback();
      resetVad();
      if (state.rejectReady) state.rejectReady(new Error("canal fechado"));
      state.resolveReady = null;
      state.rejectReady = null;
      state.readyPromise = null;
      setStateLabel("desconectado");
      setPulse(false);
      refreshMetrics();
      scheduleVadReconnect();
    };
    ws.onerror = () => {
      if (state.ws !== ws) return;
      logEvent("erro", "falha no canal");
    };
    ws.onmessage = (event) => {
      if (state.ws !== ws) return;
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        return;
      }
      handleEvent(data);
    };
  }

  function send(payload) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return false;
    state.ws.send(JSON.stringify(payload));
    return true;
  }

  async function ensureSession() {
    if (state.ready) return;
    connect();
    if (!state.readyPromise) {
      state.readyPromise = new Promise((resolve, reject) => {
        state.resolveReady = resolve;
        state.rejectReady = reject;
      });
    }
    const ready = state.readyPromise;
    try {
      await Promise.race([
        ready,
        sleep(20000).then(() => {
          throw new Error("timeout ao abrir a sessão");
        }),
      ]);
    } catch (err) {
      if (state.readyPromise === ready) resetSession();
      throw err;
    }
  }

  function handleEvent(event) {
    const type = event.type;
    state.lastEventAt = performance.now();
    logEvent("<-", type, describe(event));
    switch (type) {
      case "session.created": {
        state.session = event.session || {};
        applySessionRates(state.session);
        const sessionUpdate = { type: "realtime", max_output_tokens: MAX_OUTPUT_TOKENS };
        if (state.settings.instructions) sessionUpdate.instructions = state.settings.instructions;
        sessionUpdate.output_modalities = modalities();
        send({ type: "session.update", session: sessionUpdate });
        break;
      }
      case "session.updated": {
        state.ready = true;
        state.reconnectTries = 0;
        if (state.reconnectTimer) {
          clearTimeout(state.reconnectTimer);
          state.reconnectTimer = null;
        }
        setStateLabel("pronto");
        if (state.resolveReady) state.resolveReady();
        state.resolveReady = null;
        state.rejectReady = null;
        refreshMetrics();
        break;
      }
      case "response.created": {
        startAssistant();
        state.responding = true;
        state.responseId = (event.response && event.response.id) || null;
        state.responseStartedAt = performance.now();
        state.waitingSince = 0;
        state.cancelSentAt = 0;
        setStateLabel("falando");
        break;
      }
      case "response.output_text.delta": {
        if (!state.current || state.current.done) break;
        if (event.response_id && state.responseId && event.response_id !== state.responseId) break;
        markFirstDelta();
        state.current.text += event.delta || "";
        updateAssistantText();
        break;
      }
      case "response.output_audio.delta": {
        if (!state.current || state.current.done) break;
        if (event.response_id && state.responseId && event.response_id !== state.responseId) break;
        if (!event.delta) break;
        markFirstDelta();
        const samples = int16FromB64(event.delta);
        state.current.chunks.push(samples);
        schedule(samples, state.outRate);
        setStateLabel("falando");
        break;
      }
      case "response.done": {
        const doneId = (event.response && event.response.id) || null;
        if (doneId && state.responseId && doneId !== state.responseId) break;
        state.cancelSentAt = 0;
        state.responseId = null;
        finishResponse(false);
        break;
      }
      case "error": {
        const message = (event.error && event.error.message) || "erro no servidor";
        if (!state.ready && state.rejectReady) state.rejectReady(new Error(message));
        if (state.current) finishResponse(true, message);
        toast(message);
        setStateLabel("erro");
        break;
      }
      default:
        break;
    }
    refreshMetrics();
  }

  function describe(event) {
    if (event.type === "error") return (event.error && event.error.message) || "";
    if (event.type === "response.output_audio.delta") return event.delta ? Math.round((event.delta.length * 3) / 4) + " bytes" : "";
    if (event.type === "response.output_text.delta") return JSON.stringify(event.delta || "");
    if (event.type === "session.created" || event.type === "session.updated") {
      const session = event.session || {};
      return session.model ? String(session.model) : "";
    }
    return "";
  }

  function markFirstDelta() {
    if (!state.current || state.current.first) return;
    state.current.first = performance.now();
    if (state.tLast) {
      state.current.latency = state.current.first - state.tLast;
      state.lastLatency = state.current.latency;
    }
  }

  function startAssistant() {
    if (state.current && !state.current.done) finishResponse(false);
    stopPlayback();
    state.preroll = [];
    state.prerollSamples = 0;
    const wrapper = document.createElement("div");
    wrapper.className = "msg assistant";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const text = document.createElement("div");
    text.className = "text";
    text.innerHTML = '<span class="typing">...</span>';
    const meta = document.createElement("div");
    meta.className = "meta";
    bubble.appendChild(text);
    bubble.appendChild(meta);
    wrapper.appendChild(bubble);
    els.messages.appendChild(wrapper);
    els.emptyChat.classList.add("hidden");
    els.messages.scrollTop = els.messages.scrollHeight;
    state.current = {
      text: "",
      chunks: [],
      el: bubble,
      textEl: text,
      metaEl: meta,
      first: null,
      done: false,
      error: null,
      latency: null,
    };
  }

  function updateAssistantText() {
    if (!state.current) return;
    state.current.textEl.textContent = state.current.text || "...";
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function finishResponse(failed, message) {
    if (!state.current) {
    state.responding = false;
    state.responseStartedAt = 0;
    state.waitingSince = 0;
    return;
  }
    const current = state.current;
    if (current.done) return;
    current.done = true;
    current.error = failed ? message || "erro" : null;
    state.responding = false;
    state.responseStartedAt = 0;
    state.waitingSince = 0;
    if (!current.text) {
      current.textEl.textContent = failed ? "erro: " + current.error : "(sem texto)";
    }
    const metaParts = [];
    if (current.latency !== null && current.latency !== undefined) {
      metaParts.push((current.latency >= 0 ? "+" : "") + current.latency.toFixed(0) + " ms");
    }
    if (current.chunks.length) {
      const seconds = current.chunks.reduce((sum, part) => sum + part.length, 0) / state.outRate;
      metaParts.push(seconds.toFixed(2) + " s de áudio");
      const button = document.createElement("button");
      button.className = "btn ghost tiny";
      button.textContent = "salvar wav";
      button.addEventListener("click", () => {
        download(wavBlob(concatInt16(current.chunks), state.outRate), "resposta-" + Date.now() + ".wav");
      });
      current.metaEl.appendChild(button);
    }
    if (failed) metaParts.push("erro");
    current.metaEl.prepend(document.createTextNode(metaParts.join(" · ")));
    current.el.classList.toggle("errored", !!failed);
    setStateLabel(failed ? "erro" : "pronto");
  }

  function addUserMessage(label, seconds) {
    const wrapper = document.createElement("div");
    wrapper.className = "msg user";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const text = document.createElement("div");
    text.className = "text";
    text.textContent = label;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = seconds.toFixed(2) + " s";
    bubble.appendChild(text);
    bubble.appendChild(meta);
    wrapper.appendChild(bubble);
    els.messages.appendChild(wrapper);
    els.emptyChat.classList.add("hidden");
    els.messages.scrollTop = els.messages.scrollHeight;
    return text;
  }

  async function transcribeTurn(samples, textEl) {
    if (!textEl || !samples.length) return;
    const previous = textEl.textContent;
    textEl.textContent = "transcrevendo...";
    textEl.classList.add("dim");
    try {
      const result = await api("/api/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio: b64FromInt16(samples),
          rate: state.inRate,
          language: state.settings.lang || null,
          server: state.settings.server,
          model: state.settings.model,
        }),
      });
      const text = ((result && result.text) || "").trim();
      textEl.textContent = text || "(não entendi a fala)";
    } catch (err) {
      textEl.textContent = previous;
    } finally {
      textEl.classList.remove("dim");
      els.messages.scrollTop = els.messages.scrollHeight;
    }
  }

  async function initCapture() {
    if (state.captureCtx && state.captureNode && state.captureTargetRate === state.inRate) return;
    if (state.captureTask) return state.captureTask;
    state.captureTask = initCaptureNow();
    try {
      await state.captureTask;
    } finally {
      state.captureTask = null;
    }
  }

  function primeCapture() {
    initCapture().catch(() => {
      /* permissão negada ou contexto ainda bloqueado: tentamos de novo no primeiro turno */
    });
  }

  async function startMonitoring() {
    try {
      await ensureSession();
      await initCapture();
      if (state.captureCtx && state.captureCtx.state === "suspended") await state.captureCtx.resume();
      state.vadReadyAt = performance.now() + 600;
    } catch (err) {
      toast("VAD: " + (err.message || String(err)));
    }
  }

  function scheduleVadReconnect() {
    if (!state.settings.vad || state.reconnectTimer) return;
    if (state.reconnectTries >= 3) {
      toast("VAD: reconexão pausada; altere o VAD para tentar de novo");
      return;
    }
    state.reconnectTries += 1;
    state.reconnectTimer = setTimeout(() => {
      state.reconnectTimer = null;
      if (!state.settings.vad || state.ws) return;
      startMonitoring();
    }, 2000);
  }

  async function initCaptureNow() {
    if (state.captureCtx && state.captureNode && state.captureTargetRate === state.inRate) return;
    if (state.captureCtx) {
      try {
        await state.captureCtx.close();
      } catch (err) {
        /* ignore */
      }
      state.captureCtx = null;
      state.captureNode = null;
      state.resampler = null;
      state.captureTargetRate = 0;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("este navegador não expõe microfone (use http://127.0.0.1)");
    }
    if (!state.mediaStream) {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    }
    const context = new AudioContext({ sampleRate: state.inRate });
    await context.audioWorklet.addModule("pcm-worklet.js");
    const source = context.createMediaStreamSource(state.mediaStream);
    const node = new AudioWorkletNode(context, "pcm-capture");
    node.port.onmessage = (event) => onPcm(event.data);
    source.connect(node);
    const sink = context.createGain();
    sink.gain.value = 0;
    node.connect(sink);
    sink.connect(context.destination);
    state.captureCtx = context;
    state.captureNode = node;
    state.captureTargetRate = state.inRate;
    state.resampler = context.sampleRate === state.inRate ? null : new Resampler(context.sampleRate, state.inRate);
    refreshMetrics();
  }

  function onPcm(samples) {
    const level = rms(samples);
    state.level = level;
    pushWave(level);
    if (state.muted) {
      state.vadSince = 0;
      state.bargeSince = 0;
      return;
    }

    const vadOn = !!state.settings.vad && !state.pttHeld;
    const now = performance.now();
    const active = state.responding || state.playing || state.sources.size > 0;

    if (vadOn && !state.vadActive && !active) updateNoiseFloor(level);

    if (vadOn) {
      const threshold = effectiveThreshold();
      if (active) {
        if (state.settings.vadBargeIn) {
          const bargeThreshold = Math.max(threshold * VAD_BARGE_FACTOR, state.noiseFloor * 1.5, 0.008);
          if (level > bargeThreshold) {
            state.lastVoice = now;
            if (!state.bargeSince) {
              state.bargeSince = now;
              state.vadSince = now;
              interruptResponse();
              state.preroll = [];
              state.prerollSamples = 0;
            }
          } else if (state.bargeSince && now - state.lastVoice > VAD_BARGE_GAP_MS) {
            state.bargeSince = 0;
            state.vadSince = 0;
            state.preroll = [];
            state.prerollSamples = 0;
          }
        }
      } else if (level > threshold) {
        state.lastVoice = now;
        if (!state.vadActive && !state.sending) {
          if (!state.vadSince) state.vadSince = now;
          if (now >= state.vadReadyAt && now - state.vadSince >= VAD_MIN_SPEECH_MS) {
            state.vadActive = true;
            state.vadSince = 0;
            state.bargeSince = 0;
            beginTurn();
          }
        }
      } else {
        if (state.vadSince && now - state.lastVoice > VAD_ONSET_GAP_MS) {
          state.vadSince = 0;
          state.bargeSince = 0;
          state.preroll = [];
          state.prerollSamples = 0;
        }
        if (state.vadActive && state.sending && !state.starting && now - state.lastVoice > VAD_RELEASE_MS) {
          state.vadActive = false;
          endTurn();
        }
      }
    } else {
      state.vadSince = 0;
      state.bargeSince = 0;
    }

    if (!state.sending && !vadOn) return;
    const converted = state.resampler ? state.resampler.process(samples) : samples;
    if (!state.sending) {
      if (!state.responding && !state.playing) pushPreroll(converted);
      return;
    }
    appendPending(converted);
  }

  function appendPending(samples) {
    if (!samples || !samples.length) return;
    const merged = new Int16Array(state.pending.length + samples.length);
    merged.set(state.pending);
    merged.set(samples, state.pending.length);
    const step = Math.max(1, Math.round(state.inRate * 0.1));
    let offset = 0;
    while (merged.length - offset >= step) {
      sendChunk(merged.subarray(offset, offset + step));
      offset += step;
    }
    state.pending = merged.slice(offset);
  }

  function sendChunk(samples) {
    if (!samples.length) return;
    if (!send({ type: "input_audio_buffer.append", audio: b64FromInt16(samples) })) return;
    if (state.collectAudio) state.turnAudio.push(samples.slice());
    state.turnSamples += samples.length;
    state.bytesSent += samples.length * 2;
    if (state._lastSend && performance.now() - state._lastSend > 500) refreshMetrics();
    state._lastSend = performance.now();
  }

  function interruptResponse() {
    const playing = state.playing || state.sources.size > 0;
    const responding = state.responding;
    if (!playing && !responding) return;
    stopPlayback();
    if (state.ttsController) {
      state.ttsController.abort();
      state.ttsController = null;
    }
    if (responding) {
      send({ type: "response.cancel" });
      state.cancelSentAt = performance.now();
    }
    send({ type: "input_audio_buffer.clear" });
    if (state.current && !state.current.done) finishResponse(false, "interrompido");
    state.responding = false;
    state.responseStartedAt = 0;
    state.waitingSince = 0;
  }

  function clearInputBuffer() {
    send({ type: "input_audio_buffer.clear" });
  }

  async function beginTurn() {
    interruptResponse();
    if (state.sending || state.starting) return;
    state.starting = true;
    try {
      await ensureSession();
      await initCapture();
      if (state.captureCtx && state.captureCtx.state === "suspended") await state.captureCtx.resume();
      ensureOutCtx();
      clearInputBuffer();
      state.sending = true;
      state.turnStartedAt = performance.now();
      state.turnSamples = 0;
      state.turnAudio = [];
      state.collectAudio = true;
      state.pending = new Int16Array(0);
      if (!state.pttHeld && !state.vadActive) {
        endTurn();
        return;
      }
      if (state.vadActive && state.preroll.length) flushPreroll();
      setPulse(true);
      setStateLabel("gravando");
    } catch (err) {
      state.sending = false;
      state.collectAudio = false;
      state.turnAudio = [];
      state.pending = new Int16Array(0);
      setPulse(false);
      resetVad();
      toast(err.message || String(err));
      setStateLabel("erro");
    } finally {
      state.starting = false;
    }
  }

  function endTurn() {
    setPulse(false);
    state.vadActive = false;
    if (!state.sending) return;
    if (state.pending.length) {
      sendChunk(state.pending);
      state.pending = new Int16Array(0);
    }
    state.sending = false;
    state.turnStartedAt = 0;
    const seconds = state.turnSamples / state.inRate;
    state.turnSamples = 0;
    const audio = concatInt16(state.turnAudio);
    state.turnAudio = [];
    state.collectAudio = false;
    state.preroll = [];
    state.prerollSamples = 0;
    if (seconds < 0.15 || audio.length === 0) {
      clearInputBuffer();
      setStateLabel("pronto");
      return;
    }
    const textEl = addUserMessage("microfone", seconds);
    state.tLast = performance.now();
    state.waitingSince = performance.now();
    send({ type: "response.create" });
    state.turnCount += 1;
    setStateLabel("aguardando");
    refreshMetrics();
    if (state.settings.transcribe) transcribeTurn(audio, textEl);
  }

  function ensureOutCtx() {
    if (!state.outCtx) {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      state.outCtx = new Ctor();
    }
    if (state.outCtx.state === "suspended") state.outCtx.resume();
    return state.outCtx;
  }

  function schedule(samples, rate) {
    const ctx = ensureOutCtx();
    if (!ctx || !samples.length) return;
    const audioBuffer = ctx.createBuffer(1, samples.length, rate);
    const channel = audioBuffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 32768;
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + 0.1, state.nextPlayAt || 0);
    source.start(at);
    state.nextPlayAt = at + audioBuffer.duration;
    state.sources.add(source);
    state.playing = true;
    source.onended = () => {
      state.sources.delete(source);
      if (!state.sources.size) state.playing = false;
    };
  }

  function stopPlayback() {
    for (const source of state.sources) {
      try {
        source.stop();
      } catch (err) {
        /* ignore */
      }
    }
    state.sources.clear();
    state.playing = false;
    state.nextPlayAt = 0;
  }

  function cancelResponse() {
    interruptResponse();
    state.waitingSince = 0;
    state.fileAbort = true;
    state.sending = false;
    state.collectAudio = false;
    state.turnAudio = [];
    state.pending = new Int16Array(0);
    state.turnSamples = 0;
    state.turnStartedAt = 0;
    setPulse(false);
    resetVad();
    setStateLabel("pronto");
  }

  async function hardReconnect(reason) {
    resetSession();
    if (reason) toast(reason);
    try {
      await ensureSession();
    } catch (err) {
      toast("reconectar: " + (err.message || String(err)));
    }
  }

  function watchdogTick() {
    const now = performance.now();
    if (state.settings.vad && state.sending && state.turnStartedAt && now - state.turnStartedAt > MAX_TURN_MS) {
      toast("turno longo encerrado");
      endTurn();
    }
    if (state.responding) {
      if (state.responseStartedAt && now - state.responseStartedAt > MAX_RESPONSE_MS) {
        toast("resposta longa cancelada");
        cancelResponse();
        return;
      }
      if (state.lastEventAt && now - state.lastEventAt > RESPONSE_STALL_MS) {
        hardReconnect("resposta travada; reiniciando canal");
        return;
      }
    }
    if (state.waitingSince && now - state.waitingSince > RESPONSE_STALL_MS) {
      hardReconnect("resposta não iniciou; reiniciando canal");
      return;
    }
    if (state.cancelSentAt && now - state.cancelSentAt > CANCEL_GRACE_MS) {
      hardReconnect("cancelamento sem resposta; reiniciando canal");
    }
  }

  function pushWave(level) {
    state.wave.push(level);
    if (state.wave.length > 64) state.wave.shift();
  }

  function drawLoop() {
    const canvas = els.wave;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    const bars = state.wave.length;
    const barWidth = Math.max(2, width / 64);
    for (let i = 0; i < bars; i++) {
      const level = state.wave[i];
      const barHeight = Math.max(2, Math.min(1, level * 6) * height);
      const x = i * barWidth;
      ctx.fillStyle = state.sending ? "#4ade80" : state.playing ? "#60a5fa" : "#334155";
      ctx.fillRect(x, (height - barHeight) / 2, barWidth - 1, barHeight);
    }
    requestAnimationFrame(drawLoop);
  }

  function refreshMetrics() {
    const rows = [
      ["canal", state.ready ? "pronto" : state.ws && state.ws.readyState === 1 ? "conectando" : "fechado"],
      ["modelo", (state.session && state.session.model) || state.settings.model || "—"],
      ["entrada", state.inRate + " Hz"],
      ["saída", state.outRate + " Hz"],
      ["turnos", String(state.turnCount)],
      ["enviado", (state.bytesSent / 1024).toFixed(1) + " KiB"],
      ["latência", state.lastLatency === null ? "—" : state.lastLatency.toFixed(0) + " ms"],
      ["eventos", String(state.events.length)],
    ];
    els.metrics.innerHTML = rows
      .map(([label, value]) => '<div class="metric"><span>' + label + "</span><b>" + value + "</b></div>")
      .join("");
  }

  function syncSettingsInputs() {
    els.setServer.value = state.settings.server;
    els.setModel.value = state.settings.model;
    els.setModalities.value = state.settings.modalities;
    els.setVoice.value = state.settings.voice;
    els.setLang.value = state.settings.lang;
    els.setInstructions.value = state.settings.instructions;
    els.vad.checked = !!state.settings.vad;
    els.threshold.value = state.settings.threshold;
    els.thresholdVal.textContent = state.settings.threshold;
    els.setTranscribe.checked = !!state.settings.transcribe;
    els.setBarge.checked = !!state.settings.vadBargeIn;
    els.ttsVoice.value = state.settings.voice;
    els.ttsLang.value = state.settings.lang;
  }

  function openSettings() {
    syncSettingsInputs();
    els.settings.classList.remove("hidden");
  }

  function closeSettings() {
    els.settings.classList.add("hidden");
  }

  function saveSettings() {
    const previous = { ...state.settings };
    state.settings.server = els.setServer.value.trim() || DEFAULTS.server;
    state.settings.model = els.setModel.value.trim() || "default";
    state.settings.modalities = els.setModalities.value;
    state.settings.voice = els.setVoice.value;
    state.settings.lang = els.setLang.value.trim() || "pt";
    state.settings.instructions = els.setInstructions.value;
    state.settings.transcribe = els.setTranscribe.checked;
    state.settings.vadBargeIn = els.setBarge.checked;
    persist();
    syncSettingsInputs();
    closeSettings();
    if (previous.server !== state.settings.server || previous.model !== state.settings.model) {
      resetSession();
      setBadge("health", "pending", "health");
      setBadge("realtime", "pending", "realtime");
      runCheck();
    } else if (
      previous.modalities !== state.settings.modalities ||
      previous.instructions !== state.settings.instructions
    ) {
      resetSession();
    }
    refreshMetrics();
  }

  function resetSettings() {
    const cfg = state.cfg;
    state.settings = {
      ...DEFAULTS,
      ...(cfg
        ? {
            server: cfg.server,
            model: cfg.model,
            instructions: cfg.instructions,
            modalities: (cfg.modalities || ["text", "audio"]).join(","),
            voice: cfg.voice,
            lang: cfg.lang,
          }
        : {}),
    };
    persist();
    syncSettingsInputs();
    resetSession();
    runCheck();
  }

  function setupTabs() {
    const tabs = document.querySelectorAll(".tab");
    const panes = {
      chat: $("pane-chat"),
      tts: $("pane-tts"),
      file: $("pane-file"),
    };
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((item) => item.classList.toggle("active", item === tab));
        Object.entries(panes).forEach(([name, pane]) => pane.classList.toggle("active", name === tab.dataset.tab));
      });
    });
  }

  function setupPtt() {
    els.ptt.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      els.ptt.setPointerCapture(event.pointerId);
      state.pttHeld = true;
      els.ptt.classList.add("active");
      if (!state.sending) beginTurn();
    });
    const release = (event) => {
      if (!state.pttHeld) return;
      state.pttHeld = false;
      els.ptt.classList.remove("active");
      endTurn();
      if (event && event.pointerId !== undefined && els.ptt.hasPointerCapture(event.pointerId)) {
        els.ptt.releasePointerCapture(event.pointerId);
      }
    };
    els.ptt.addEventListener("pointerup", release);
    els.ptt.addEventListener("pointercancel", release);
    els.ptt.addEventListener("pointerleave", (event) => {
      if (state.pttHeld) release(event);
    });

    document.addEventListener("keydown", (event) => {
      if (event.code !== "Space" || event.repeat) return;
      const target = event.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select" || (target && target.isContentEditable)) return;
      if (!els.settings.classList.contains("hidden")) return;
      event.preventDefault();
      state.pttHeld = true;
      els.ptt.classList.add("active");
      beginTurn();
    });

    document.addEventListener("keyup", (event) => {
      if (event.code !== "Space") return;
      const target = event.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select" || (target && target.isContentEditable)) return;
      if (!state.pttHeld) return;
      event.preventDefault();
      state.pttHeld = false;
      els.ptt.classList.remove("active");
      endTurn();
    });
  }

  async function runTts() {
    const text = els.ttsText.value.trim();
    if (!text) {
      toast("Digite um texto para sintetizar.");
      return;
    }
    stopPlayback();
    state.ttsChunks = [];
    state.ttsRate = 0;
    els.ttsSave.disabled = true;
    els.ttsBtn.disabled = true;
    els.ttsMeta.textContent = "gerando...";
    const controller = new AbortController();
    state.ttsController = controller;
    const started = performance.now();
    try {
      const response = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input: text,
          voice: els.ttsVoice.value,
          lang: els.ttsLang.value.trim() || null,
          response_format: "pcm",
          stream: true,
          server: state.settings.server,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        let detail = await response.text();
        try {
          const parsed = JSON.parse(detail);
          detail = parsed.detail || detail;
        } catch (err) {
          /* ignore */
        }
        throw new Error(detail || response.statusText);
      }
      const contentType = response.headers.get("content-type") || "";
      const match = contentType.match(/rate=(\d+)/);
      const rate = match ? parseInt(match[1], 10) : 24000;
      state.ttsRate = rate;
      const reader = response.body.getReader();
      let pending = new Uint8Array(0);
      let firstByte = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!firstByte) {
          firstByte = performance.now();
          els.ttsMeta.textContent = "primeiro byte em " + (firstByte - started).toFixed(0) + " ms · " + rate + " Hz";
        }
        pending = concatBytes(pending, value);
        const usable = pending.length - (pending.length % 4);
        if (usable > 0) {
          const slice = pending.slice(0, usable);
          pending = pending.slice(usable);
          const floats = new Float32Array(slice.buffer);
          const samples = floatToInt16(floats);
          state.ttsChunks.push(samples);
          schedule(samples, rate);
        }
      }
      const total = state.ttsChunks.reduce((sum, part) => sum + part.length, 0);
      const seconds = total / rate;
      els.ttsMeta.textContent =
        "pronto · " +
        seconds.toFixed(2) +
        " s · " +
        rate +
        " Hz · primeiro byte em " +
        (firstByte ? (firstByte - started).toFixed(0) : "?") +
        " ms";
      els.ttsSave.disabled = total === 0;
    } catch (err) {
      if (err.name === "AbortError") {
        els.ttsMeta.textContent = "cancelado";
      } else {
        els.ttsMeta.textContent = "erro: " + err.message;
        toast("TTS: " + err.message);
      }
    } finally {
      state.ttsController = null;
      els.ttsBtn.disabled = false;
    }
  }

  function saveTts() {
    if (!state.ttsChunks.length) return;
    download(wavBlob(concatInt16(state.ttsChunks), state.ttsRate || 24000), "tts-" + Date.now() + ".wav");
  }

  async function sendFile() {
    const file = els.fileInput.files && els.fileInput.files[0];
    if (!file) {
      toast("Escolha um arquivo de áudio.");
      return;
    }
    els.fileBtn.disabled = true;
    els.fileMeta.textContent = "decodificando " + file.name + "...";
    try {
      const data = await file.arrayBuffer();
      const Ctor = window.AudioContext || window.webkitAudioContext;
      const decoder = new Ctor();
      const decoded = await decoder.decodeAudioData(data);
      await decoder.close();
      let samples = floatToInt16(decoded.getChannelData(0));
      if (decoded.sampleRate !== state.inRate) {
        samples = resampleArray(samples, decoded.sampleRate, state.inRate);
      }
      await beginFileTurn(file.name, samples);
    } catch (err) {
      els.fileMeta.textContent = "erro: " + err.message;
      toast("Arquivo: " + err.message);
    } finally {
      els.fileBtn.disabled = false;
    }
  }

  async function beginFileTurn(name, samples) {
    interruptResponse();
    els.fileMeta.textContent = "conectando...";
    await ensureSession();
    ensureOutCtx();
    clearInputBuffer();
    state.sending = false;
    state.pending = new Int16Array(0);
    state.fileAbort = false;
    state.turnSamples = 0;
    state.collectAudio = false;
    state.turnAudio = [];
    resetVad();
    const seconds = samples.length / state.inRate;
    addUserMessage("arquivo " + name, seconds);
    els.fileMeta.textContent = "enviando " + seconds.toFixed(2) + " s...";
    const step = Math.max(1, Math.round(state.inRate * 0.1));
    for (let i = 0; i < samples.length; i += step) {
      if (state.fileAbort) {
        els.fileMeta.textContent = "cancelado";
        return;
      }
      sendChunk(samples.subarray(i, i + step));
      await sleep(100);
    }
    state.tLast = performance.now();
    state.waitingSince = performance.now();
    send({ type: "response.create" });
    state.turnCount += 1;
    setStateLabel("aguardando");
    els.fileMeta.textContent = "aguardando resposta...";
  }

  async function boot() {
    setupTabs();
    setupPtt();
    els.check.addEventListener("click", runCheck);
    els.settingsBtn.addEventListener("click", openSettings);
    els.settingsClose.addEventListener("click", closeSettings);
    els.settingsSave.addEventListener("click", saveSettings);
    els.settingsReset.addEventListener("click", resetSettings);
    els.settings.addEventListener("click", (event) => {
      if (event.target === els.settings) closeSettings();
    });
    els.vad.addEventListener("change", () => {
      state.settings.vad = els.vad.checked;
      persist();
      if (state.settings.vad) {
        startMonitoring();
      } else {
        resetVad();
      }
    });
    els.threshold.addEventListener("input", () => {
      state.settings.threshold = Number(els.threshold.value);
      els.thresholdVal.textContent = els.threshold.value;
      persist();
    });
    els.mute.addEventListener("click", () => {
      state.muted = !state.muted;
      els.mute.classList.toggle("active", state.muted);
      els.mute.textContent = state.muted ? "Mudo: sim" : "Mudo";
    });
    els.cancel.addEventListener("click", cancelResponse);
    els.clearEvents.addEventListener("click", () => {
      state.events = [];
      els.events.innerHTML = "";
      refreshMetrics();
    });
    els.ttsBtn.addEventListener("click", runTts);
    els.ttsStop.addEventListener("click", () => {
      if (state.ttsController) state.ttsController.abort();
      stopPlayback();
    });
    els.ttsSave.addEventListener("click", saveTts);
    els.fileBtn.addEventListener("click", sendFile);
    els.fileStop.addEventListener("click", () => {
      state.fileAbort = true;
      cancelResponse();
    });

    try {
      state.cfg = await api("/api/config");
    } catch (err) {
      toast("Falha ao ler a configuração: " + err.message);
    }
    const stored = readStored();
    const base = state.cfg
      ? {
          server: state.cfg.server,
          model: state.cfg.model,
          instructions: state.cfg.instructions,
          modalities: (state.cfg.modalities || ["text", "audio"]).join(","),
          voice: state.cfg.voice,
          lang: state.cfg.lang,
        }
      : {};
    state.settings = { ...DEFAULTS, ...base, ...stored };
    syncSettingsInputs();
    if (state.settings.vad) {
      state.vadReadyAt = performance.now() + 600;
      startMonitoring();
    }
    refreshMetrics();
    setInterval(watchdogTick, 1000);
    drawLoop();
    runCheck();
  }

  window.addEventListener("beforeunload", () => {
    if (state.ws) state.ws.close();
    if (state.mediaStream) state.mediaStream.getTracks().forEach((track) => track.stop());
  });

  boot();
})();
