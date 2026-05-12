window.XTTSStudio = window.XTTSStudio || {};

(function registerSettingsHelpers(namespace) {
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

  namespace.SettingsHelpers = { normalizeImageProviderModel };
})(window.XTTSStudio);
