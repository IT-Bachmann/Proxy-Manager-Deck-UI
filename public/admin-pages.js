(() => {
  let page = document.querySelector("#adminPage");
  if (!page) {
    page = document.createElement("section");
    page.id = "adminPage";
    page.className = "content admin-page";
    page.hidden = true;
    document.querySelector("main").append(page);
  }
  const dialog = document.createElement("dialog");
  dialog.className = "manager-dialog admin-edit-dialog";
  dialog.innerHTML = '<div class="dialog-head"><div><h2 id="adminEditTitle">Bearbeiten</h2><p id="adminEditSubtitle"></p></div><button type="button" id="adminEditClose">×</button></div><form id="adminEditForm" class="manager-content"></form>';
  document.body.append(dialog);
  dialog.querySelector("#adminEditClose").onclick = () => dialog.close();

  function activate(link, title) {
    document.querySelectorAll("main>section.content").forEach(section => section.hidden = true);
    page.hidden = false;
    document.querySelectorAll(".sidebar nav a").forEach(item => item.classList.toggle("active", item === link));
    document.querySelector(".breadcrumbs span").textContent = title;
    document.querySelector(".breadcrumbs strong").textContent = "Übersicht";
  }
  function hideAdminPage() { page.hidden = true; }
  document.querySelector("#dashboardLink").addEventListener("click", hideAdminPage, true);
  document.querySelector("#proxyHostsLink").addEventListener("click", hideAdminPage, true);

  async function showUsers() {
    const link = document.querySelector("#usersLink");
    activate(link, "Benutzer");
    const data = await api("/api/users");
    page.innerHTML = `<div class="admin-page-head"><div><h1>Benutzerverwaltung</h1><p>Konten, Rollen, Zugang und Passwörter verwalten.</p></div><button class="button primary" id="newUserButton">＋ Benutzer anlegen</button></div>
      <div class="admin-grid-list">${data.items.map(user => `<article class="admin-list-card"><div class="admin-list-avatar">${escapeHtml(user.username.slice(0,2).toUpperCase())}</div><div class="admin-list-main"><strong>${escapeHtml(user.username)}</strong><small>Erstellt am ${new Date(user.created_at*1000).toLocaleDateString("de-DE")}</small></div><span class="tag">${escapeHtml(user.role)}</span><span class="tag">${user.enabled?"Aktiv":"Deaktiviert"}</span><div class="admin-list-actions"><button class="button user-edit" data-id="${user.id}">Bearbeiten</button><button class="button danger user-delete" data-id="${user.id}">Löschen</button></div></article>`).join("")||'<div class="card empty-state">Noch keine Benutzer vorhanden.</div>'}</div>`;
    page.querySelector("#newUserButton").onclick = () => openUserDialog(null);
    page.querySelectorAll(".user-edit").forEach(button => button.onclick = () => openUserDialog(data.items.find(user => user.id === Number(button.dataset.id))));
    page.querySelectorAll(".user-delete").forEach(button => button.onclick = async () => {
      const user = data.items.find(item => item.id === Number(button.dataset.id));
      if (!confirm(`Benutzer „${user.username}“ wirklich löschen? Alle Sitzungen dieses Benutzers werden beendet.`)) return;
      try { await api("/api/users/delete", {method:"POST", body:JSON.stringify({id:user.id})}); toast("Benutzer gelöscht", user.username); await showUsers(); }
      catch (error) { toast("Löschen fehlgeschlagen", error.message); }
    });
  }

  function openUserDialog(user) {
    dialog.querySelector("#adminEditTitle").textContent = user ? "Benutzer bearbeiten" : "Benutzer anlegen";
    dialog.querySelector("#adminEditSubtitle").textContent = user ? "Rolle, Status, Name oder Passwort ändern" : "Neues Konto mit einer Rolle erstellen";
    const form = dialog.querySelector("#adminEditForm");
    form.innerHTML = `<div class="admin-form-grid"><label><span>Benutzername</span><input name="username" value="${escapeHtml(user?.username||"")}" pattern="[A-Za-z0-9_.-]{3,64}" required></label><label><span>Rolle</span><select name="role"><option value="viewer" ${user?.role==="viewer"?"selected":""}>Betrachter</option><option value="operator" ${user?.role==="operator"?"selected":""}>Operator</option><option value="admin" ${user?.role==="admin"?"selected":""}>Administrator</option></select></label><label class="wide"><span>${user?"Neues Passwort (leer lassen zum Beibehalten)":"Passwort (mindestens 16 Zeichen)"}</span><input name="password" type="password" minlength="16" ${user?"":"required"} autocomplete="new-password"></label><label class="admin-check wide"><input name="enabled" type="checkbox" ${user?.enabled!==0?"checked":""}> Benutzer aktiv</label></div><div class="host-modal-actions"><button type="button" class="button" id="cancelAdminEdit">Abbrechen</button><button class="button primary">${user?"Änderungen speichern":"Benutzer anlegen"}</button></div>`;
    form.querySelector("#cancelAdminEdit").onclick = () => dialog.close();
    form.onsubmit = async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(form)); values.enabled = form.enabled.checked;
      try {
        await api(user?"/api/users/update":"/api/users", {method:"POST", body:JSON.stringify(user?{id:user.id,...values}:values)});
        dialog.close(); toast(user?"Benutzer aktualisiert":"Benutzer angelegt", values.username); await showUsers();
      } catch (error) { toast("Speichern fehlgeschlagen", error.message); }
    };
    dialog.showModal();
  }

  async function showCertificates() {
    const link = document.querySelector("#certificatesLink");
    activate(link, "Zertifikate");
    const [data, providers] = await Promise.all([api("/api/certificates"), state.role === "admin" ? api("/api/acme-providers") : Promise.resolve({items:[]})]);
    const status = {issued:"Gültig",requesting:"Wird angefordert",failed:"Fehler",pending:"Ausstehend"};
    page.innerHTML = `<div class="admin-page-head"><div><h1>SSL-Zertifikate</h1><p>Alle Zertifikate einzeln prüfen, herunterladen oder löschen.</p></div></div>
      <section class="card certificate-request-card"><div class="card-head"><div><h2>Neues Zertifikat anfordern</h2><p>Mehrere Domains mit Komma trennen; Wildcards benötigen DNS-01.</p></div></div><form id="pageCertificateForm" class="admin-form-grid"><label class="wide"><span>Domains / SANs</span><input name="domains" placeholder="example.com, www.example.com" required></label><label><span>ACME-E-Mail</span><input name="email" type="email" required></label><label><span>Challenge</span><select name="challenge"><option value="http-01">HTTP-01</option><option value="dns-01">DNS-01</option></select></label><label><span>DNS-Anbieter</span><select name="provider_id"><option value="">– Nicht benötigt –</option>${providers.items.map(provider=>`<option value="${provider.id}">${escapeHtml(provider.name)} · ${escapeHtml(provider.provider)}</option>`).join("")}</select></label><button class="button primary">Zertifikat anfordern</button></form></section>
      <div class="certificate-page-grid">${data.items.map(certificate => {let domains;try{domains=JSON.parse(certificate.domains_json||"null")||[certificate.domain]}catch{domains=[certificate.domain]}const expires=certificate.expires_at?new Date(certificate.expires_at*1000).toLocaleDateString("de-DE"):"–";return `<article class="card certificate-detail-card"><div class="certificate-detail-head"><div><span class="tag">${escapeHtml(status[certificate.status]||certificate.status)}</span><h2>${escapeHtml(certificate.domain)}</h2></div><span class="certificate-id">#${certificate.id}</span></div><dl><div><dt>Domains / SANs</dt><dd>${domains.map(domain=>`<code>${escapeHtml(domain)}</code>`).join(" ")}</dd></div><div><dt>Challenge</dt><dd>${escapeHtml((certificate.challenge||"http-01").toUpperCase())}</dd></div><div><dt>E-Mail</dt><dd>${escapeHtml(certificate.email)}</dd></div><div><dt>Gültig bis</dt><dd>${expires}</dd></div>${certificate.last_error?`<div class="wide error-detail"><dt>Letzter Fehler</dt><dd>${escapeHtml(certificate.last_error)}</dd></div>`:""}</dl><div class="certificate-actions">${certificate.status==="issued"&&state.role==="admin"?`<button class="button certificate-download" data-id="${certificate.id}" data-domain="${escapeHtml(certificate.domain)}">ZIP herunterladen</button>`:""}${state.role==="admin"?`<button class="button danger certificate-delete" data-id="${certificate.id}" data-domain="${escapeHtml(certificate.domain)}">Löschen</button>`:""}</div></article>`}).join("")||'<div class="card empty-state">Noch keine Zertifikate vorhanden.</div>'}</div>`;
    const form = page.querySelector("#pageCertificateForm");
    if (state.role !== "admin") form.closest(".certificate-request-card").remove();
    if (state.role !== "admin") return;
    form.challenge.onchange = () => { form.provider_id.required = form.challenge.value === "dns-01"; };
    form.onsubmit = async event => { event.preventDefault(); const values=Object.fromEntries(new FormData(form));values.domains=values.domains.split(/[;,\s]+/).filter(Boolean);if(values.provider_id)values.provider_id=Number(values.provider_id);try{await api("/api/certificates/request",{method:"POST",body:JSON.stringify(values)});toast("ACME gestartet",values.domains.join(" · "));setTimeout(showCertificates,800)}catch(error){toast("ACME fehlgeschlagen",error.message)} };
    page.querySelectorAll(".certificate-download").forEach(button => button.onclick = async () => { try { const response=await fetch(`/api/certificates/${button.dataset.id}/download`,{credentials:"same-origin"});if(!response.ok){const body=await response.json();throw new Error(body.error)}const blob=await response.blob(),url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download=`${button.dataset.domain.replace(/[^A-Za-z0-9._-]/g,"_")}-certificate.zip`;anchor.click();URL.revokeObjectURL(url)}catch(error){toast("Download fehlgeschlagen",error.message)} });
    page.querySelectorAll(".certificate-delete").forEach(button => button.onclick = async () => { if(!confirm(`Zertifikat „${button.dataset.domain}“ wirklich löschen? Zugewiesene Proxy Hosts verlieren dabei SSL.`))return;try{const result=await api("/api/certificates/delete",{method:"POST",body:JSON.stringify({id:Number(button.dataset.id)})});toast("Zertifikat gelöscht",result.warning||button.dataset.domain);await showCertificates()}catch(error){toast("Löschen fehlgeschlagen",error.message)} });
  }

  document.querySelector("#usersLink").onclick = event => { event.preventDefault(); showUsers().catch(error => toast("Benutzer nicht geladen", error.message)); };
  document.querySelector("#certificatesLink").onclick = event => { event.preventDefault(); showCertificates().catch(error => toast("Zertifikate nicht geladen", error.message)); };
})();
