(() => {
  const originalOpenModal = openModal;
  const modal = document.querySelector("#modal");
  const title = document.querySelector("#modalTitle");
  const subtitle = document.querySelector("#modalSubtitle");
  const body = document.querySelector("#modalBody");
  const definitions = {
    redirects: {
      title: "Weiterleitung anlegen",
      subtitle: "Eine Domain auf eine andere Adresse umleiten",
      form: '<div class="modal-grid"><label class="wide">Domain<input placeholder="www.example.com"></label><label class="wide">Ziel-URL<input type="url" placeholder="https://example.com"></label><label>Statuscode<select><option>301 · Dauerhaft</option><option>302 · Temporär</option><option>307 · Temporär</option><option>308 · Dauerhaft</option></select></label><label>Status<select><option>Aktiv</option><option>Deaktiviert</option></select></label></div>'
    },
    streams: {
      title: "Stream anlegen",
      subtitle: "TCP- oder UDP-Dienst über das Gateway veröffentlichen",
      form: '<div class="modal-grid"><label>Listen-Port<input type="number" value="9000"></label><label>Protokoll<select><option>TCP</option><option>UDP</option></select></label><label class="wide">Zieladresse<input placeholder="192.168.1.50"></label><label>Ziel-Port<input type="number" value="9000"></label><label>Status<select><option>Aktiv</option><option>Deaktiviert</option></select></label></div>'
    },
    dns: {
      title: "DNS-Anbieter anlegen",
      subtitle: "Zugangsdaten verschlüsselt für ACME DNS-01 speichern",
      form: '<div class="modal-grid"><label>Name<input placeholder="DNS Produktion"></label><label>Anbieter<select><option>Cloudflare</option><option>IONOS</option><option>Hetzner DNS</option><option>IPv64.net</option><option>STRATO</option><option>PowerDNS</option></select></label><label class="wide">API-Token<input type="password"></label><label class="wide">Aktuelles Proxy-Manager-Deck-Passwort<input type="password"></label></div>'
    },
    health: {
      title: "Healthcheck konfigurieren",
      subtitle: "Prüfintervall und Antwortverhalten festlegen",
      form: '<div class="modal-grid"><label class="wide">Proxy Host<select><option>paperless.example.com</option><option>home.example.com</option><option>cloud.example.com</option></select></label><label>Prüfpfad<input value="/"></label><label>Intervall<select><option>30 Sekunden</option><option>60 Sekunden</option><option>5 Minuten</option></select></label><label>Timeout<select><option>5 Sekunden</option><option>10 Sekunden</option></select></label><label>Status<select><option>Aktiv</option><option>Deaktiviert</option></select></label></div>'
    },
    traffic: {
      title: "Traffic-Bericht",
      subtitle: "Zeitraum und Datenumfang für den Export wählen",
      form: '<div class="modal-grid"><label>Zeitraum<select><option>Letzte 24 Stunden</option><option>7 Tage</option><option>30 Tage</option></select></label><label>Format<select><option>CSV</option><option>JSON</option></select></label><label class="wide">Proxy Host<select><option>Alle Proxy Hosts</option><option>paperless.example.com</option><option>home.example.com</option></select></label></div>'
    },
    notifications: {
      title: "Benachrichtigung anlegen",
      subtitle: "E-Mail, Telegram oder WhatsApp konfigurieren",
      form: '<div class="modal-grid"><label>Name<input placeholder="Bereitschaft"></label><label>Kanal<select><option>E-Mail / SMTP</option><option>Telegram</option><option>WhatsApp</option></select></label><label class="wide">Server, Token oder API-Zugang<input type="password"></label><label class="wide">Empfänger<input placeholder="admin@example.com"></label></div>'
    },
    logs: {
      title: "Protokolle exportieren",
      subtitle: "Systemereignisse für die Diagnose herunterladen",
      form: '<div class="modal-grid"><label>Zeitraum<select><option>Letzte Stunde</option><option>24 Stunden</option><option>7 Tage</option></select></label><label>Stufe<select><option>Alle</option><option>Warnungen</option><option>Fehler</option></select></label><label class="wide">Quelle<select><option>Alle Komponenten</option><option>Control</option><option>Gateway</option><option>Updater</option><option>ACME</option></select></label></div>'
    }
  };
  openModal = (kind, item) => {
    if (kind !== "create") return originalOpenModal(kind, item);
    if (current === "proxies") return originalOpenModal("new-proxy");
    if (current === "certificates") return originalOpenModal("new-cert");
    if (current === "users") return originalOpenModal("new-user");
    const definition = definitions[current];
    if (!definition) return originalOpenModal("new-proxy");
    title.textContent = definition.title;
    subtitle.textContent = definition.subtitle;
    body.innerHTML = definition.form;
    document.querySelector("#modalSave").onclick = () => {
      modal.close();
      notify("Gespeichert", `${definition.title} wurde in der Demo übernommen.`);
    };
    modal.showModal();
  };
})();
