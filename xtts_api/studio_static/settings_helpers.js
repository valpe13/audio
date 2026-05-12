window.XTTSStudio = window.XTTSStudio || {};

(function registerSettingsHelpers(namespace) {
  const GROK_IMAGE_MODEL = "grok-imagine-image-quality";
  const LEGACY_GROK_IMAGE_MODELS = new Set(["grok-2-image", "grok-2-image-1212", "grok-imagine-image-pro"]);

  function normalizeImageProviderModel(rawProvider, rawModel, options = {}) {
    let provider = String(rawProvider || "comfyui").trim().toLowerCase();
    let model = String(rawModel || "realvisxl").trim().toLowerCase();
    if (provider === "xai") provider = "grok";
    if (!["placeholder", "comfyui", "grok"].includes(provider)) provider = "comfyui";
    if (provider === "grok") model = "grok";
    if (model === "grok" && provider !== "grok") {
      if (options.preferProvider) model = "realvisxl";
      else provider = "grok";
    }
    if (!["realvisxl", "sdxl", "juggernautxl", "dreamshaperxl", "flux", "custom", "grok"].includes(model)) model = "custom";
    return { provider, model };
  }

  function normalizeGrokImageModel(rawModel) {
    const model = String(rawModel || "").trim();
    return !model || LEGACY_GROK_IMAGE_MODELS.has(model.toLowerCase()) ? GROK_IMAGE_MODEL : model;
  }

  namespace.SettingsHelpers = { normalizeImageProviderModel, normalizeGrokImageModel };
})(window.XTTSStudio);
