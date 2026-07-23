(() => {
  const replaceName = root => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while (node = walker.nextNode()) {
      if (node.parentElement?.closest("script,style")) continue;
      node.nodeValue = node.nodeValue.replaceAll("ProxyDeck", "Proxy Manager Deck");
    }
  };
  replaceName(document.body);
  new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
    if (node.nodeType === Node.TEXT_NODE) node.nodeValue = node.nodeValue.replaceAll("ProxyDeck", "Proxy Manager Deck");
    else if (node.nodeType === Node.ELEMENT_NODE) replaceName(node);
  }))).observe(document.body, {subtree:true, childList:true});
})();
