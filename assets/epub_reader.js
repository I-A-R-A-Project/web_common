(function () {
  const pages = [...document.querySelectorAll(".page")];
  const total = pages.length;
  const chapterIndicator = document.getElementById("chapterIndicator");
  const prevBtn = document.getElementById("prevChapter");
  const nextBtn = document.getElementById("nextChapter");
  const zoomIndicator = document.getElementById("zoomIndicator");
  const stack = document.querySelector(".page-stack");
  const progressFill = document.getElementById("progress-fill");
  let current = 0;
  let zoom = 1;
  function updateButtons() {
    prevBtn.disabled = current <= 0;
    nextBtn.disabled = current >= total - 1;
    chapterIndicator.textContent = (current + 1) + " / " + total;
  }
  function goTo(index) {
    pages[Math.max(0, Math.min(total - 1, index))]
      .scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function setZoom(value) {
    zoom = Math.max(.6, Math.min(2, value));
    stack.style.zoom = zoom;
    zoomIndicator.textContent = Math.round(zoom * 100) + "%";
  }
  prevBtn.addEventListener("click", () => goTo(current - 1));
  nextBtn.addEventListener("click", () => goTo(current + 1));
  document.getElementById("zoomIn").addEventListener("click", () => setZoom(zoom + .1));
  document.getElementById("zoomOut").addEventListener("click", () => setZoom(zoom - .1));
  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting && entry.intersectionRatio > .5) {
      current = Number(entry.target.dataset.index);
      updateButtons();
    }
  }), { threshold: [.5] });
  pages.forEach((page) => observer.observe(page));
  addEventListener("scroll", () => {
    const max = document.body.scrollHeight - innerHeight;
    progressFill.style.width = (max > 0 ? scrollY / max : 0) * 100 + "%";
  }, { passive: true });
  addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowRight", "PageDown", " "].includes(event.key)) {
      event.preventDefault(); scrollBy({ top: innerHeight * .85, behavior: "smooth" });
    } else if (["ArrowUp", "ArrowLeft", "PageUp"].includes(event.key)) {
      event.preventDefault(); scrollBy({ top: -innerHeight * .85, behavior: "smooth" });
    } else if (event.key === "Home") {
      event.preventDefault(); scrollTo({ top: 0, behavior: "smooth" });
    } else if (event.key === "End") {
      event.preventDefault(); scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    } else if (event.key === "]") goTo(current + 1);
    else if (event.key === "[") goTo(current - 1);
    else if ((event.ctrlKey || event.metaKey) && ["+", "="].includes(event.key)) {
      event.preventDefault(); setZoom(zoom + .1);
    } else if ((event.ctrlKey || event.metaKey) && event.key === "-") {
      event.preventDefault(); setZoom(zoom - .1);
    } else if ((event.ctrlKey || event.metaKey) && event.key === "0") {
      event.preventDefault(); setZoom(1);
    }
  });
  updateButtons();
})();
