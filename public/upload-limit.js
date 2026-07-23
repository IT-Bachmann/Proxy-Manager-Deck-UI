(() => {
  const limit = 2 * 1024 * 1024;
  window.readImage = input => new Promise((resolve, reject) => {
    const file = input.files[0];
    if (!file) return resolve("");
    if (file.size > limit) return reject(new Error("Bild ist größer als 2 MB"));
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Bild konnte nicht gelesen werden"));
    reader.readAsDataURL(file);
  });
  const updateLabels = root => {
    root.querySelectorAll?.("label span").forEach(label => {
      if (label.textContent.includes("max. 500 KB")) label.textContent = label.textContent.replace("max. 500 KB", "max. 2 MB");
    });
  };
  new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => node.nodeType === 1 && updateLabels(node)))).observe(document.body, {subtree:true, childList:true});
  updateLabels(document);
})();
