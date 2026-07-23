(() => {
  const defaults = { accent: "#1bad79", background: "#f4f7f6", logo: "", favicon: "" };
  const allowedScales = ["0.5", "1", "1.5"];
  const allowedFontSizes = ["10", "11", "12", "13", "14", "15", "16"];
  const rgb = hex => [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16));
  const mix = (first, second, weight) => {
    const a = rgb(first), b = rgb(second);
    return "#" + a.map((channel, index) => Math.round(channel * (1 - weight) + b[index] * weight).toString(16).padStart(2, "0")).join("");
  };
  const readDesign = () => ({ ...defaults, ...JSON.parse(localStorage.getItem("proxy-manager-deck-design") || "{}") });
  const applyScale = value => {
    const scale = allowedScales.includes(String(value)) ? String(value) : "1";
    localStorage.setItem("proxy-manager-deck-ui-scale", scale);
    applyDisplaySize(scale, localStorage.getItem("proxy-manager-deck-font-size") || "14");
  };
  const applyFontSize = value => {
    const fontSize = allowedFontSizes.includes(String(value)) ? String(value) : "14";
    localStorage.setItem("proxy-manager-deck-font-size", fontSize);
    applyDisplaySize(localStorage.getItem("proxy-manager-deck-ui-scale") || "1", fontSize);
  };
  function applyDisplaySize(scale, fontSize) {
    document.documentElement.style.zoom = String(Number(scale) * Number(fontSize) / 14);
  }
  const applyDesign = design => {
    const accentDark = mix(design.accent, "#000000", 0.28);
    document.documentElement.style.setProperty("--accent", design.accent);
    document.documentElement.style.setProperty("--accent-dark", accentDark);
    document.documentElement.style.setProperty("--soft", mix("#ffffff", design.accent, 0.13));
    document.documentElement.style.setProperty("--bg", mix(design.background, design.accent, 0.08));
    document.documentElement.style.setProperty("--panel", mix("#ffffff", design.accent, 0.025));
    document.documentElement.style.setProperty("--line", mix("#e4e8e6", design.accent, 0.16));
    document.documentElement.style.setProperty("--nav", mix("#050807", design.accent, 0.13));
    document.documentElement.style.setProperty("--tint-dark-bg", mix("#040706", design.accent, 0.13));
    document.documentElement.style.setProperty("--tint-dark-panel", mix("#09100d", design.accent, 0.18));
    document.documentElement.style.setProperty("--tint-dark-line", mix("#17201c", design.accent, 0.28));
    document.documentElement.style.setProperty("--tint-dark-soft", mix("#112019", design.accent, 0.30));
    document.querySelectorAll(".brand-mark").forEach(mark => {
      mark.classList.toggle("has-custom-logo", Boolean(design.logo));
      mark.style.backgroundImage = design.logo ? `url("${design.logo}")` : "";
      mark.style.backgroundSize = "contain";
      mark.style.backgroundPosition = "center";
      mark.style.backgroundRepeat = "no-repeat";
      mark.textContent = design.logo ? "" : "PM";
    });
    let icon = document.querySelector('link[rel="icon"]');
    if (design.favicon) {
      if (!icon) { icon = document.createElement("link"); icon.rel = "icon"; document.head.append(icon); }
      icon.href = design.favicon;
    } else if (icon) icon.remove();
  };
  const readImage = input => new Promise((resolve, reject) => {
    const file = input?.files?.[0];
    if (!file) return resolve("");
    if (file.size > 2_000_000) return reject(new Error("Die Bilddatei ist größer als 2 MB."));
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Die Bilddatei konnte nicht gelesen werden."));
    reader.readAsDataURL(file);
  });
  document.addEventListener("change", event => {
    if (event.target.id === "uiScale") applyScale(event.target.value);
    if (event.target.id === "fontSize") applyFontSize(event.target.value);
  });
  document.addEventListener("click", async event => {
    if (event.target.closest("#saveDesign")) {
      try {
        const previous = readDesign();
        const design = {
          accent: document.querySelector("#designAccent").value,
          background: document.querySelector("#designBackground").value,
          logo: await readImage(document.querySelector("#designLogo")) || previous.logo,
          favicon: await readImage(document.querySelector("#designFavicon")) || previous.favicon
        };
        localStorage.setItem("proxy-manager-deck-design", JSON.stringify(design));
        applyScale(document.querySelector("#uiScale").value);
        applyDesign(design);
        notify("Design gespeichert", "Farben, Bilder und Größe wurden übernommen.");
      } catch (error) { notify("Design nicht gespeichert", error.message); }
    }
    if (event.target.closest("#resetDesign")) {
      localStorage.removeItem("proxy-manager-deck-design");
      localStorage.removeItem("proxy-manager-deck-ui-scale");
      localStorage.removeItem("proxy-manager-deck-font-size");
      applyFontSize("14"); applyScale("1"); applyDesign(defaults); render();
      notify("Design zurückgesetzt", "Das Standarddesign ist wieder aktiv.");
    }
  });
  applyFontSize(localStorage.getItem("proxy-manager-deck-font-size") || "14");
  applyScale(localStorage.getItem("proxy-manager-deck-ui-scale") || "1");
  applyDesign(readDesign());
})();
