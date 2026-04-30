(function () {
  "use strict";

  // Même script pour deux familles de composants :
  // - les accordéons, qui peuvent faire varier la hauteur globale ;
  // - les carrousels, qui restent localisés à leur propre bloc.
  const PAGE_SELECTOR = ".page";
  const SECTION_SELECTOR = ".page-section";
  const LAYOUT_NODE_SELECTOR = ".content-node, .content-text, .content-asset";
  const EPSILON = 0.5;
  let relayoutFrame = 0;
  let pendingRelayoutPage = null;
  let pendingRelayoutSection = null;

  function toNumber(value, fallback) {
    const parsed = Number.parseFloat(String(value ?? ""));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function measureTop(element) {
    return toNumber(window.getComputedStyle(element).top, element.offsetTop || 0);
  }

  function measureHeight(element) {
    const computedHeight = toNumber(window.getComputedStyle(element).height, -1);
    if (computedHeight >= 0) {
      return computedHeight;
    }
    const rectHeight = toNumber(element.getBoundingClientRect().height, -1);
    if (rectHeight >= 0) {
      return rectHeight;
    }
    return element.offsetHeight || 0;
  }

  function captureLayoutMetric(element) {
    if (!element) {
      return;
    }
    // On mémorise la géométrie initiale une seule fois pour pouvoir rejouer
    // des recalculs idempotents après ouverture/fermeture d'un accordion.
    if (element.matches(SECTION_SELECTOR) || element.matches(LAYOUT_NODE_SELECTOR)) {
      if (!element.dataset.layoutOriginalTop) {
        element.dataset.layoutOriginalTop = String(measureTop(element));
      }
      if (!element.dataset.layoutCurrentTop) {
        element.dataset.layoutCurrentTop = element.dataset.layoutOriginalTop;
      }
    }
    if (!element.dataset.layoutOriginalHeight) {
      element.dataset.layoutOriginalHeight = String(measureHeight(element));
    }
    if (!element.dataset.layoutCurrentHeight) {
      element.dataset.layoutCurrentHeight = element.dataset.layoutOriginalHeight;
    }
  }

  function getOriginalTop(element) {
    captureLayoutMetric(element);
    return toNumber(element.dataset.layoutOriginalTop, 0);
  }

  function getOriginalHeight(element) {
    captureLayoutMetric(element);
    return toNumber(element.dataset.layoutOriginalHeight, 0);
  }

  function getCurrentHeight(element) {
    captureLayoutMetric(element);
    return toNumber(element.dataset.layoutCurrentHeight, getOriginalHeight(element));
  }

  function getCurrentTop(element) {
    captureLayoutMetric(element);
    return toNumber(element.dataset.layoutCurrentTop, getOriginalTop(element));
  }

  function setCurrentHeight(element, height, options) {
    const persistStyle = options && options.persistStyle === false ? false : true;
    const normalizedHeight = Math.max(height, 0);
    element.dataset.layoutCurrentHeight = String(normalizedHeight);
    if (persistStyle) {
      element.style.height = normalizedHeight + "px";
    } else {
      element.style.removeProperty("height");
    }
  }

  function setCurrentTop(element, top) {
    element.dataset.layoutCurrentTop = String(top);
    element.style.top = top + "px";
  }

  function compareByOriginalPosition(left, right) {
    const topDelta = getOriginalTop(left) - getOriginalTop(right);
    if (Math.abs(topDelta) > EPSILON) {
      return topDelta;
    }
    const position = left.compareDocumentPosition(right);
    if (position & Node.DOCUMENT_POSITION_PRECEDING) {
      return 1;
    }
    if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
      return -1;
    }
    return 0;
  }

  function containerDepth(element) {
    let depth = 0;
    let current = element.parentElement;
    while (current) {
      if (current.matches && current.matches(".content-node")) {
        depth += 1;
      }
      current = current.parentElement;
    }
    return depth;
  }

  function layoutChildren(parent) {
    return Array.from(parent.children).filter((child) => child.matches(LAYOUT_NODE_SELECTOR));
  }

  function pageSections(page) {
    return Array.from(page.querySelectorAll(SECTION_SELECTOR)).sort(compareByOriginalPosition);
  }

  function accordionItems(root) {
    return layoutChildren(root).filter((child) => child.dataset.accordionItem === "true");
  }

  function accordionTrigger(item) {
    return layoutChildren(item).find((child) => child.dataset.accordionTrigger === "true") || null;
  }

  function accordionPanel(item) {
    return layoutChildren(item).find((child) => child.dataset.accordionPanel === "true") || null;
  }

  function isLinkGridRow(element) {
    return Boolean(
      element &&
        element.matches &&
        element.matches(".content-node") &&
        element.parentElement &&
        element.parentElement.dataset.linkGrid === "true" &&
        element.dataset.linkCard !== "true",
    );
  }

  function isFlowLayoutContainer(element) {
    return Boolean(
      element &&
        element.matches &&
        (element.dataset.linkGrid === "true" || element.dataset.linkCard === "true" || isLinkGridRow(element)),
    );
  }

  function measureFlowHeight(element) {
    const rectHeight = toNumber(element.getBoundingClientRect().height, -1);
    if (rectHeight >= 0) {
      return rectHeight;
    }
    return Math.max(element.scrollHeight || 0, element.offsetHeight || 0, getOriginalHeight(element));
  }

  function isFlowAccordionItem(item) {
    return Boolean(item && item.dataset.accordionItem === "true" && item.dataset.layoutFlow === "true");
  }

  function isFlowAccordionRoot(root) {
    return Boolean(root && root.dataset.accordion === "true" && root.dataset.layoutFlow === "true");
  }

  function isPageFlowShell(page) {
    return Boolean(page && page.dataset.pageShell === "flow");
  }

  function isFlowSection(section) {
    return Boolean(
      section &&
        section.matches &&
        section.matches(SECTION_SELECTOR) &&
        (section.dataset.layoutShell === "flow" ||
          (section.dataset.layoutFlow === "true" && section.dataset.layoutStrategy === "flow")),
    );
  }

  function accordionHeaderHeight(item, trigger, panel) {
    const panelTop = panel ? getOriginalTop(panel) : 0;
    if (panelTop > EPSILON) {
      return panelTop;
    }
    if (trigger) {
      return getOriginalTop(trigger) + getOriginalHeight(trigger);
    }
    return getOriginalHeight(item);
  }

  function setAccordionItemState(item, open) {
    const trigger = accordionTrigger(item);
    const panel = accordionPanel(item);
    if (!trigger || !panel) {
      return;
    }

    item.dataset.accordionState = open ? "open" : "closed";
    item.dataset.accordionOpen = open ? "true" : "false";
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    panel.hidden = !open;
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    panel.style.visibility = open ? "visible" : "hidden";
    panel.style.pointerEvents = open ? "" : "none";
    panel.style.opacity = open ? "1" : "0";

    item.style.overflow = "hidden";
    if (isFlowAccordionItem(item)) {
      item.style.height = "";
      const nextHeight = measureFlowHeight(item);
      setCurrentHeight(item, nextHeight, { persistStyle: false });
      return;
    }

    const headerHeight = toNumber(item.dataset.accordionHeaderHeight, getOriginalHeight(item));
    const nextHeight = open ? getOriginalHeight(item) : headerHeight;
    setCurrentHeight(item, nextHeight);
  }

  function relayoutContainer(container) {
    if (isFlowAccordionRoot(container)) {
      const flowHeight = measureFlowHeight(container);
      setCurrentHeight(container, flowHeight, { persistStyle: false });
      return flowHeight;
    }

    if (isFlowAccordionItem(container)) {
      container.style.height = "";
      const flowHeight = measureFlowHeight(container);
      setCurrentHeight(container, flowHeight, { persistStyle: false });
      return flowHeight;
    }

    if (container.dataset.accordionItem === "true") {
      const explicitHeight = getCurrentHeight(container);
      container.style.height = explicitHeight + "px";
      return explicitHeight;
    }

    if (isFlowLayoutContainer(container)) {
      // Certains blocs, comme la matrice de cards, vivent mieux en flux CSS
      // qu'en repositionnement absolu enfant par enfant.
      container.style.left = "";
      container.style.top = "";
      container.style.height = "";
      const flowHeight = measureFlowHeight(container);
      setCurrentHeight(container, flowHeight, { persistStyle: false });
      return flowHeight;
    }

    const children = layoutChildren(container).sort(compareByOriginalPosition);
    if (!children.length) {
      const originalHeight = getOriginalHeight(container);
      setCurrentHeight(container, originalHeight);
      return originalHeight;
    }

    let currentHeight = 0;
    const previousChildren = [];

    for (const child of children) {
      const originalTop = getOriginalTop(child);
      let shift = 0;
      for (const previous of previousChildren) {
        if (originalTop + EPSILON >= previous.originalBottom) {
          shift += previous.delta;
        }
      }
      const nextTop = originalTop + shift;
      const childHeight = getCurrentHeight(child);

      setCurrentTop(child, nextTop);
      currentHeight = Math.max(currentHeight, nextTop + childHeight);
      previousChildren.push({
        originalBottom: getOriginalTop(child) + getOriginalHeight(child),
        delta: childHeight - getOriginalHeight(child),
      });
    }

    setCurrentHeight(container, currentHeight);
    return currentHeight;
  }

  function relayoutSections(page, startSection) {
    const sections = pageSections(page);
    if (!sections.length) {
      return;
    }
    const pageFlowShell = isPageFlowShell(page);

    const startIndex = startSection ? Math.max(sections.indexOf(startSection), 0) : 0;

    let pageHeight = 0;
    const previousSections = [];

    for (let index = 0; index < sections.length; index += 1) {
      const section = sections[index];
      const sectionInner = section.querySelector(":scope > .page-section__inner");
      const sectionHeight = sectionInner ? getCurrentHeight(sectionInner) : getOriginalHeight(section);
      if (index < startIndex) {
        pageHeight = Math.max(pageHeight, getCurrentTop(section) + sectionHeight);
        previousSections.push({
          originalBottom: getOriginalTop(section) + getOriginalHeight(section),
          delta: sectionHeight - getOriginalHeight(section),
        });
        continue;
      }

      const originalTop = getOriginalTop(section);
      let shift = 0;

      for (const previous of previousSections) {
        if (originalTop + EPSILON >= previous.originalBottom) {
          shift += previous.delta;
        }
      }

      const nextTop = originalTop + shift;
      if (pageFlowShell || isFlowSection(section)) {
        section.dataset.layoutCurrentTop = String(nextTop);
        section.style.removeProperty("top");
        setCurrentHeight(section, sectionHeight, { persistStyle: false });
        section.style.minHeight = sectionHeight + "px";
      } else {
        setCurrentTop(section, nextTop);
        setCurrentHeight(section, sectionHeight);
        section.style.minHeight = sectionHeight + "px";
      }

      pageHeight = Math.max(pageHeight, nextTop + sectionHeight);
      previousSections.push({
        originalBottom: getOriginalTop(section) + getOriginalHeight(section),
        delta: sectionHeight - getOriginalHeight(section),
      });
    }

    // Quand des blocs passent en flux (FAQ, matrice de cards...), le footer
    // peut remonter. On doit donc laisser la page se contracter, sinon on
    // conserve artificiellement la hauteur initiale de la maquette et un vide
    // blanc apparait sous le footer.
    if (pageFlowShell) {
      page.style.removeProperty("min-height");
      return;
    }
    page.style.minHeight = pageHeight + "px";
  }

  function relayoutPageFromSection(page, startSection) {
    if (!page) {
      return;
    }

    const sections = pageSections(page);
    const startIndex = startSection ? Math.max(sections.indexOf(startSection), 0) : 0;
    const scopedSections = sections.slice(startIndex);
    const containers = scopedSections.flatMap((section) => Array.from(section.querySelectorAll(".content-node"))).sort(
      (left, right) => containerDepth(right) - containerDepth(left),
    );
    for (const container of containers) {
      relayoutContainer(container);
    }

    const sectionInners = scopedSections
      .map((section) => section.querySelector(":scope > .page-section__inner"))
      .filter(Boolean);
    for (const sectionInner of sectionInners) {
      relayoutContainer(sectionInner);
    }

    relayoutSections(page, startSection);
  }

  function scheduleRelayoutPageFromSection(page, startSection) {
    if (!page) {
      return;
    }
    pendingRelayoutPage = page;
    if (startSection) {
      if (!pendingRelayoutSection) {
        pendingRelayoutSection = startSection;
      } else {
        pendingRelayoutSection =
          compareByOriginalPosition(startSection, pendingRelayoutSection) < 0 ? startSection : pendingRelayoutSection;
      }
    }
    if (relayoutFrame) {
      return;
    }
    relayoutFrame = window.requestAnimationFrame(() => {
      const nextPage = pendingRelayoutPage;
      const nextSection = pendingRelayoutSection;
      relayoutFrame = 0;
      pendingRelayoutPage = null;
      pendingRelayoutSection = null;
      relayoutPageFromSection(nextPage, nextSection);
    });
  }

  function bindResponsiveRelayout(page, startSection) {
    if (!page) {
      return;
    }
    const schedule = () => scheduleRelayoutPageFromSection(page, startSection);
    window.addEventListener("resize", schedule, { passive: true });
    window.addEventListener("load", schedule, { once: true });
    if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === "function") {
      document.fonts.ready.then(schedule).catch(() => {});
    }
    page.querySelectorAll("img").forEach((image) => {
      if (image.complete) {
        return;
      }
      image.addEventListener("load", schedule, { once: true });
    });
  }

  function initializeAccordionRoot(root) {
    const items = accordionItems(root).filter((item) => accordionTrigger(item) && accordionPanel(item));
    if (!items.length) {
      return false;
    }

    root.dataset.accordionReady = "true";
    for (const item of items) {
      const trigger = accordionTrigger(item);
      const panel = accordionPanel(item);
      captureLayoutMetric(item);
      captureLayoutMetric(trigger);
      captureLayoutMetric(panel);
      item.dataset.accordionHeaderHeight = String(accordionHeaderHeight(item, trigger, panel));
    }

    const singleMode = root.dataset.accordionMode === "single";
    if (singleMode) {
      const openItem = items.find((item) => item.dataset.accordionOpen !== "false") || items[0];
      for (const item of items) {
        setAccordionItemState(item, item === openItem);
      }
    } else {
      for (const item of items) {
        setAccordionItemState(item, item.dataset.accordionOpen !== "false");
      }
    }

    root.addEventListener("click", (event) => {
      const trigger = event.target.closest('[data-accordion-trigger="true"]');
      if (!trigger || !root.contains(trigger)) {
        return;
      }

      const item = trigger.closest('[data-accordion-item="true"]');
      if (!item) {
        return;
      }

      const shouldOpen = item.dataset.accordionState !== "open";
      if (singleMode && shouldOpen) {
        for (const otherItem of items) {
          if (otherItem !== item) {
            setAccordionItemState(otherItem, false);
          }
        }
      }

      setAccordionItemState(item, shouldOpen);
      scheduleRelayoutPageFromSection(root.ownerDocument.querySelector(PAGE_SELECTOR), root.closest(SECTION_SELECTOR));
    });

    return true;
  }

  function initializeAccordions() {
    const page = document.querySelector(PAGE_SELECTOR);
    if (!page) {
      return;
    }

    captureLayoutMetric(page);
    page.querySelectorAll(`${SECTION_SELECTOR}, .page-section__inner, .content-node, .content-text, .content-asset`).forEach(
      captureLayoutMetric,
    );

    const roots = Array.from(page.querySelectorAll('[data-accordion="true"]'));
    const hasInteractiveAccordion = roots.map(initializeAccordionRoot).some(Boolean);
    if (hasInteractiveAccordion) {
      const earliestAccordionSection = roots
        .map((root) => root.closest(SECTION_SELECTOR))
        .filter(Boolean)
        .sort(compareByOriginalPosition)[0];
      bindResponsiveRelayout(page, earliestAccordionSection || null);
      scheduleRelayoutPageFromSection(page, earliestAccordionSection || null);
    }
  }

  function setCarouselState(root, activeKey, slides, thumbs) {
    root.dataset.carouselActive = activeKey;
    for (const slide of slides) {
      const isActive = slide.dataset.carouselSlide === activeKey;
      slide.hidden = !isActive;
      slide.setAttribute("aria-hidden", isActive ? "false" : "true");
      slide.style.visibility = isActive ? "visible" : "hidden";
      slide.style.pointerEvents = isActive ? "" : "none";
      slide.style.opacity = isActive ? "1" : "0";
    }
    for (const thumb of thumbs) {
      const isActive = thumb.dataset.carouselThumb === activeKey;
      thumb.setAttribute("aria-pressed", isActive ? "true" : "false");
      thumb.dataset.carouselActive = isActive ? "true" : "false";
    }
  }

  function initializeCarouselRoot(root) {
    // Le carrousel ne recalcule pas le layout de la page : il ne fait que
    // permuter les slides visibles et mettre à jour l'état des miniatures.
    const slides = Array.from(root.querySelectorAll("[data-carousel-slide]"));
    const thumbs = Array.from(root.querySelectorAll("[data-carousel-thumb]"));
    if (!slides.length || !thumbs.length) {
      return false;
    }

    const slidesByKey = new Map();
    slides.forEach((slide, index) => {
      const key = slide.dataset.carouselSlide || slide.id || "slide-" + String(index + 1);
      slide.dataset.carouselSlide = key;
      slidesByKey.set(key, slide);
    });

    thumbs.forEach((thumb, index) => {
      const key = thumb.dataset.carouselThumb || slides[index]?.dataset.carouselSlide || thumb.id || "thumb-" + String(index + 1);
      thumb.dataset.carouselThumb = key;
      thumb.setAttribute("aria-pressed", "false");
      const matchingSlide = slidesByKey.get(key);
      if (matchingSlide && matchingSlide.id) {
        thumb.setAttribute("aria-controls", matchingSlide.id);
      }
    });

    const defaultSlide = slides.find((slide) => slide.dataset.carouselDefault === "true");
    const defaultThumb = thumbs.find((thumb) => thumb.dataset.carouselDefault === "true");
    const defaultMatchedThumb = thumbs.find((thumb) => slidesByKey.has(thumb.dataset.carouselThumb));
    const activeKey =
      defaultSlide?.dataset.carouselSlide ||
      defaultThumb?.dataset.carouselThumb ||
      defaultMatchedThumb?.dataset.carouselThumb ||
      slides[0].dataset.carouselSlide;

    setCarouselState(root, activeKey, slides, thumbs);
    root.dataset.carouselReady = "true";
    for (const thumb of thumbs) {
      thumb.addEventListener("click", (event) => {
        event.preventDefault();
        const nextKey = thumb.dataset.carouselThumb;
        if (!nextKey || !slidesByKey.has(nextKey)) {
          return;
        }
        setCarouselState(root, nextKey, slides, thumbs);
      });
    }
    return true;
  }

  function initializeCarousels() {
    const page = document.querySelector(PAGE_SELECTOR);
    if (!page) {
      return;
    }
    Array.from(page.querySelectorAll("[data-carousel='true']")).forEach(initializeCarouselRoot);
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        initializeAccordions();
        initializeCarousels();
      },
      { once: true },
    );
  } else {
    initializeAccordions();
    initializeCarousels();
  }
})();
