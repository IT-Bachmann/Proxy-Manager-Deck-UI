/* Demo 2 feature completion: real multi-target proxy editor and page coverage. */
data.proxies = [
  {
    id: 1, domain: "paperless.example.com", status: true, ssl: "Gültig",
    scheme: "http", port: 8000, strategy: "round_robin", certificate: "paperless.example.com",
    websocket: true, forceSsl: true,
    targets: [
      { address: "192.0.2.42", type: "IPv4", weight: 100, mode: "Aktiv", path: "/" },
      { address: "2001:db8:42::10", type: "IPv6", weight: 100, mode: "Aktiv", path: "/" }
    ]
  },
  {
    id: 2, domain: "home.example.com", status: true, ssl: "Gültig",
    scheme: "https", port: 8123, strategy: "least_conn", certificate: "*.example.com",
    websocket: true, forceSsl: true,
    targets: [{ address: "homeassistant.internal", type: "Hostname", weight: 100, mode: "Aktiv", path: "/" }]
  },
  {
    id: 3, domain: "cloud.example.com", status: false, ssl: "Kein SSL",
    scheme: "http", port: 8080, strategy: "weighted", certificate: "",
    websocket: false, forceSsl: false,
    targets: [{ address: "10.20.0.12", type: "IPv4", weight: 50, mode: "Backup", path: "/status.php" }]
  }
];

const strategyLabels = {
  round_robin: "Round Robin",
  least_conn: "Wenigste Verbindungen",
  ip_hash: "IP-Hash (Client-Bindung)",
  weighted: "Gewichtete Verteilung",
  random: "Zufällige Verteilung"
};

function targetSummary(proxy) {
  const active = proxy.targets.filter(target => target.mode !== "Deaktiviert").length;
  return `${active} / ${proxy.targets.length} Ziele`;
}

function proxyTargets(proxy) {
  return proxy.targets.map(target =>
    `<span class="target-chip"><b>${esc(target.type)}</b>${esc(target.address)}<small>${target.mode} · Gewicht ${target.weight}</small></span>`
  ).join("");
}

views.proxies = function proxyOverview() {
  return head("Proxy Hosts", "Eine Domain kann beliebig viele IPv4-, IPv6- und Hostname-Ziele verwenden.", "new-proxy", "Proxy Host") +
    `<div class="proxy-list">${data.proxies.map(proxy => `
      <article class="card proxy-full-card">
        <div class="proxy-card-head">
          <div><h2>${esc(proxy.domain)}</h2><small>${esc(proxy.scheme.toUpperCase())}:${proxy.port} · ${strategyLabels[proxy.strategy]}</small></div>
          <span class="pill ${proxy.status ? "" : "off"}">${proxy.status ? "Aktiv" : "Deaktiviert"}</span>
        </div>
        <div class="target-chips">${proxyTargets(proxy)}</div>
        <div class="proxy-meta">
          <span>${targetSummary(proxy)}</span><span>SSL: ${esc(proxy.ssl)}</span>
          <button class="button" data-edit-proxy="${proxy.id}">Bearbeiten</button>
        </div>
      </article>`).join("")}</div>`;
};

function targetRow(target = {}) {
  return `<div class="target-editor-row">
    <span class="target-number"></span>
    <label class="target-address">Zieladresse<input class="js-target-address" value="${esc(target.address || "")}" placeholder="192.0.2.10, 2001:db8::10 oder server.local"></label>
    <label>Typ<select class="js-target-type">
      ${["IPv4", "IPv6", "Hostname"].map(type => `<option ${target.type === type ? "selected" : ""}>${type}</option>`).join("")}
    </select></label>
    <label>Gewicht<input class="js-target-weight" type="number" min="1" max="1000" value="${Number(target.weight || 100)}"></label>
    <label>Modus<select class="js-target-mode">
      ${["Aktiv", "Backup", "Deaktiviert"].map(mode => `<option ${target.mode === mode ? "selected" : ""}>${mode}</option>`).join("")}
    </select></label>
    <label>Healthcheck-Pfad<input class="js-target-path" value="${esc(target.path || "/")}" placeholder="/"></label>
    <button type="button" class="button danger remove-target" title="Ziel entfernen">×</button>
  </div>`;
}

function renumberTargets() {
  document.querySelectorAll(".target-editor-row").forEach((row, index) => {
    row.querySelector(".target-number").textContent = index + 1;
    row.querySelector(".remove-target").disabled = document.querySelectorAll(".target-editor-row").length === 1;
  });
}

function validateAddress(value, type) {
  const ipv4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
  const ipv6 = /^[0-9a-f:]+$/i;
  const hostname = /^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;
  return type === "IPv4" ? ipv4.test(value) : type === "IPv6" ? value.includes(":") && ipv6.test(value) : hostname.test(value);
}

const openModalBeforeFeatures = openModal;
views.design = function designPage() {
  const saved = JSON.parse(localStorage.getItem("proxy-manager-deck-design") || "{}");
  const scale = localStorage.getItem("proxy-manager-deck-ui-scale") || "1";
  const fontSize = localStorage.getItem("proxy-manager-deck-font-size") || "14";
  return head("Design", "Farben, Bilder und Größe der gesamten Oberfläche anpassen.") +
    `<section class="card design-card">
      <div class="design-grid">
        <label>Akzentfarbe<input id="designAccent" type="color" value="${esc(saved.accent || "#1bad79")}"></label>
        <label>Hintergrundfarbe<input id="designBackground" type="color" value="${esc(saved.background || "#f4f7f6")}"></label>
        <label>Schriftgröße<select id="fontSize">${[10,11,12,13,14,15,16].map(size => `<option value="${size}" ${fontSize === String(size) ? "selected" : ""}>${size} px</option>`).join("")}</select><small>Legt die allgemeine Textgröße fest.</small></label>
        <label>Skalierung der Oberfläche<select id="uiScale"><option value="0.5" ${scale === "0.5" ? "selected" : ""}>0,5× · Klein</option><option value="1" ${scale === "1" ? "selected" : ""}>1,0× · Standard</option><option value="1.5" ${scale === "1.5" ? "selected" : ""}>1,5× · Groß</option></select><small>Skaliert Menüs, Tabellen und Dialoge gemeinsam.</small></label>
        <label>Logo (PNG/JPG, max. 2 MB)<input id="designLogo" type="file" accept="image/png,image/jpeg"></label>
        <label>Favicon (PNG/JPG/ICO, max. 2 MB)<input id="designFavicon" type="file" accept="image/png,image/jpeg,image/x-icon"></label>
      </div>
      <div class="design-actions"><button class="button primary" id="saveDesign">Design speichern</button><button class="button" id="resetDesign">Standard wiederherstellen</button></div>
    </section>`;
};
openModal = function enhancedModal(kind, item) {
  if (!kind.includes("proxy") && kind !== "create") {
    $("#modal").classList.remove("proxy-modal");
    return openModalBeforeFeatures(kind, item);
  }
  if (kind === "create" && current !== "proxies" && current !== "dashboard") {
    $("#modal").classList.remove("proxy-modal");
    return openModalBeforeFeatures(kind, item);
  }
  item = item && typeof item === "object" ? item : null;

  const modal = $("#modal");
  modal.classList.add("proxy-modal");
  $("#modalTitle").textContent = item ? "Proxy Host bearbeiten" : "Proxy Host anlegen";
  $("#modalSubtitle").textContent = "Domain, Load Balancing und beliebig viele Ziele";
  $("#modalBody").innerHTML = `
    <div class="modal-grid proxy-general">
      <label class="wide">Domainname<input id="proxyDomain" value="${esc(item?.domain || "")}" placeholder="app.example.com"></label>
      <label>Schema<select id="proxyScheme"><option ${item?.scheme === "http" ? "selected" : ""}>http</option><option ${item?.scheme === "https" ? "selected" : ""}>https</option></select></label>
      <label>Weiterleitungs-Port<input id="proxyPort" type="number" min="1" max="65535" value="${item?.port || 80}"></label>
      <label>Load-Balancing-Verfahren<select id="proxyStrategy">
        ${Object.entries(strategyLabels).map(([value, label]) => `<option value="${value}" ${item?.strategy === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>
      <label>Zertifikat<select id="proxyCertificate"><option value="">Kein Zertifikat</option>${data.certificates.map(cert => `<option ${item?.certificate === cert.domain ? "selected" : ""}>${esc(cert.domain)}</option>`).join("")}</select></label>
    </div>
    <div class="option-checks">
      <label><input id="proxyEnabled" type="checkbox" ${item?.status !== false ? "checked" : ""}> Proxy Host aktiv</label>
      <label><input id="proxyWebsocket" type="checkbox" ${item?.websocket ? "checked" : ""}> WebSocket-Unterstützung</label>
      <label><input id="proxyForceSsl" type="checkbox" ${item?.forceSsl ? "checked" : ""}> HTTP automatisch auf HTTPS umleiten</label>
    </div>
    <div class="targets-heading"><div><strong>Upstream-Ziele</strong><small>IPv4, IPv6 und Hostnamen können gemischt werden.</small></div><button type="button" class="button primary" id="addTarget">+ Ziel hinzufügen</button></div>
    <div id="targetRows">${(item?.targets?.length ? item.targets : [{ type: "IPv4", weight: 100, mode: "Aktiv", path: "/" }]).map(targetRow).join("")}</div>`;

  $("#addTarget").onclick = () => {
    $("#targetRows").insertAdjacentHTML("beforeend", targetRow({ type: "IPv4", weight: 100, mode: "Aktiv", path: "/" }));
    renumberTargets();
  };
  $("#targetRows").onclick = event => {
    const remove = event.target.closest(".remove-target");
    if (!remove || document.querySelectorAll(".target-editor-row").length === 1) return;
    remove.closest(".target-editor-row").remove();
    renumberTargets();
  };
  renumberTargets();

  $("#modalSave").onclick = () => {
    const domain = $("#proxyDomain").value.trim().toLowerCase();
    const rows = [...document.querySelectorAll(".target-editor-row")];
    const targets = rows.map(row => ({
      address: row.querySelector(".js-target-address").value.trim(),
      type: row.querySelector(".js-target-type").value,
      weight: Number(row.querySelector(".js-target-weight").value),
      mode: row.querySelector(".js-target-mode").value,
      path: row.querySelector(".js-target-path").value.trim() || "/"
    }));
    const invalid = targets.find(target => !validateAddress(target.address, target.type));
    if (!/^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/i.test(domain)) {
      notify("Domain ungültig", "Bitte einen gültigen Domainnamen eingeben."); return;
    }
    if (invalid) {
      notify("Zieladresse ungültig", `${invalid.address || "Leeres Feld"} passt nicht zum Typ ${invalid.type}.`); return;
    }
    const record = {
      id: item?.id || Date.now(), domain, status: $("#proxyEnabled").checked,
      scheme: $("#proxyScheme").value, port: Number($("#proxyPort").value),
      strategy: $("#proxyStrategy").value, certificate: $("#proxyCertificate").value,
      ssl: $("#proxyCertificate").value ? "Gültig" : "Kein SSL",
      websocket: $("#proxyWebsocket").checked, forceSsl: $("#proxyForceSsl").checked, targets
    };
    const index = data.proxies.findIndex(proxy => proxy.id === record.id);
    if (index >= 0) data.proxies[index] = record; else data.proxies.push(record);
    modal.close(); current = "proxies"; render();
    notify("Proxy Host gespeichert", `${targets.length} Ziel${targets.length === 1 ? "" : "e"} konfiguriert.`);
  };
  modal.showModal();
};
