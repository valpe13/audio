window.XTTSStudio = window.XTTSStudio || {};

(function(namespace) {
  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value) || 0));
  }

  function roundTime(value, precision = 0.01) {
    const step = Math.max(0.001, Number(precision) || 0.01);
    return Math.round((Number(value) || 0) / step) * step;
  }

  function formatTime(seconds) {
    const safe = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safe / 60);
    const secs = Math.floor(safe % 60);
    const ms = Math.floor((safe - Math.floor(safe)) * 1000);
    return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
  }

  function shortPath(value) {
    return String(value || "").split(/[\\/]/).filter(Boolean).pop() || String(value || "");
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
  }

  function groupMediaUrl(item) {
    const raw = item?.url || item?.path || "";
    if (/^https?:\/\//i.test(raw) || String(raw).startsWith("/api/")) return raw;
    if (!raw) return "";
    return item.type === "video" ? `/api/video?path=${encodeURIComponent(raw)}` : `/api/image?path=${encodeURIComponent(raw)}`;
  }

  function audioUrlForPath(path) {
    const value = String(path || "").trim();
    if (/^https?:\/\//i.test(value)) return value;
    return value ? `/api/audio?path=${encodeURIComponent(value)}` : "";
  }

  function groupImageStatusLabel(status) {
    return ({ missing: "missing", queued: "queued", running: "running", done: "done", fallback: "fallback", failed: "failed" })[status] || status || "missing";
  }

  function formatVersionDate(value) {
    if (!value) return "unknown time";
    const ms = Number(value) * 1000;
    if (!Number.isFinite(ms)) return "unknown time";
    return new Date(ms).toLocaleString();
  }

  function chunkBoundaryType(chunk) {
    return ["sentence", "paragraph", "section"].includes(chunk?.boundary_type) ? chunk.boundary_type : "sentence";
  }

  namespace.AppHelpers = { clamp, roundTime, formatTime, shortPath, escapeHtml, groupMediaUrl, audioUrlForPath, groupImageStatusLabel, formatVersionDate, chunkBoundaryType };
})(window.XTTSStudio);
