(() => {
  const replacements = [
    ["ProxyManagerDeck2", "Proxy Manager Deck"],
    ["ProxyDeck", "Proxy Manager Deck"]
  ];

  const clean = value => replacements.reduce(
    (result, [source, target]) => result.replaceAll(source, target),
    value
  );

  const update = root => {
    if (root.nodeType === Node.TEXT_NODE) {
      root.nodeValue = clean(root.nodeValue);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    for (const attribute of ["title", "aria-label", "placeholder"]) {
      if (root.hasAttribute(attribute)) {
        root.setAttribute(attribute, clean(root.getAttribute(attribute)));
      }
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.parentElement?.closest("script,style")) node.nodeValue = clean(node.nodeValue);
    }
  };

  update(document.body);
  document.title = clean(document.title);
  new MutationObserver(records => records.forEach(record =>
    record.addedNodes.forEach(update)
  )).observe(document.body, {subtree: true, childList: true});
})();
