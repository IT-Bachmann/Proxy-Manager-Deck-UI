(() => {
  const sync = () => {
    const source = document.querySelector(".brand .custom-logo");
    const vortexLogo = document.querySelector(".book-cover .logo");
    const hasLogo = Boolean(source?.src && !source.hidden);
    document.body.classList.toggle("has-custom-logo", hasLogo);
    if (!vortexLogo) return;
    vortexLogo.textContent = hasLogo ? "" : "P";
    vortexLogo.style.backgroundImage = hasLogo ? `url("${source.src.replaceAll('"', '%22')}")` : "";
  };
  const observer = new MutationObserver(sync);
  document.querySelectorAll(".custom-logo").forEach(image => observer.observe(image, {attributes:true, attributeFilter:["src", "hidden"]}));
  sync();
})();
