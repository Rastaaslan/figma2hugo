(function () {
  function parsePx(value) {
    var parsed = Number.parseFloat(String(value || "").replace("px", "").trim());
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function roundPx(value) {
    return Math.round(value * 100) / 100;
  }

  function isVisible(element) {
    if (!(element instanceof HTMLElement)) {
      return false;
    }
    var style = window.getComputedStyle(element);
    var rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 1 && rect.height > 1;
  }

  function clipsOverflow(value) {
    return value === "hidden" || value === "clip";
  }

  function visualElementRect(element, scale) {
    var rect = element.getBoundingClientRect();
    if (!(element instanceof HTMLElement) || !element.classList.contains("content-text")) {
      return rect;
    }
    var safeScale = scale > 0 ? scale : 1;
    var style = window.getComputedStyle(element);
    var width = rect.width;
    var height = rect.height;
    if (!clipsOverflow(style.overflowX || style.overflow)) {
      width = Math.max(width, (element.scrollWidth || 0) * safeScale);
    }
    if (!clipsOverflow(style.overflowY || style.overflow)) {
      height = Math.max(height, (element.scrollHeight || 0) * safeScale);
    }
    return {
      left: rect.left,
      top: rect.top,
      right: rect.left + width,
      bottom: rect.top + height,
      width: width,
      height: height,
    };
  }

  function currentShellScale(shell, fallbackScale) {
    var current = Number.parseFloat(shell.style.getPropertyValue("--page-shell-scale"));
    if (Number.isFinite(current) && current > 0) {
      return current;
    }
    return fallbackScale > 0 ? fallbackScale : 1;
  }

  function measureVisibleSectionBounds(page, fallbackWidth, fallbackHeight, scale) {
    var maxRight = fallbackWidth;
    var maxBottom = fallbackHeight;
    var pageRect = page.getBoundingClientRect();
    var sections = page.querySelectorAll(".page-section");
    sections.forEach(function (section) {
      if (!isVisible(section)) {
        return;
      }
      var rect = section.getBoundingClientRect();
      maxBottom = Math.max(maxBottom, (rect.bottom - pageRect.top) / scale);
    });
    page.querySelectorAll(".content-asset:not(.is-decorative):not(.bg)").forEach(function (item) {
      if (!isVisible(item)) {
        return;
      }
      var rect = visualElementRect(item, scale);
      maxRight = Math.max(maxRight, (rect.right - pageRect.left) / scale);
      maxBottom = Math.max(maxBottom, (rect.bottom - pageRect.top) / scale);
    });
    page.querySelectorAll(".content-text").forEach(function (item) {
      if (!isVisible(item)) {
        return;
      }
      var rect = visualElementRect(item, scale);
      if (item.scrollWidth > item.clientWidth + 1) {
        maxRight = Math.max(maxRight, (rect.right - pageRect.left) / scale);
      }
      maxBottom = Math.max(maxBottom, (rect.bottom - pageRect.top) / scale);
    });
    return { width: maxRight, height: maxBottom };
  }

  function clearLayoutRepairs(page) {
    page.querySelectorAll('[data-page-shell-rescued-text="true"]').forEach(function (text) {
      text.remove();
    });
    page.querySelectorAll(".content-node").forEach(function (node) {
      node.style.removeProperty("--content-node-stack-shift");
    });
    page.querySelectorAll(".content-asset").forEach(function (asset) {
      asset.style.removeProperty("--content-asset-stack-shift");
    });
    page.querySelectorAll(".content-text").forEach(function (text) {
      text.style.removeProperty("--content-text-stack-shift");
    });
    page.querySelectorAll(".page-section").forEach(function (section) {
      section.style.removeProperty("--page-section-stack-shift");
      section.style.removeProperty("--page-section-compact-height");
      section.removeAttribute("data-page-shell-compact-height");
    });
    page.querySelectorAll('[data-page-shell-hidden-breakpoint-bg="true"]').forEach(function (asset) {
      asset.removeAttribute("data-page-shell-hidden-breakpoint-bg");
      asset.style.removeProperty("display");
    });
    page.querySelectorAll('[data-page-shell-tiny-form="true"]').forEach(function (form) {
      form.removeAttribute("data-page-shell-tiny-form");
      form.querySelectorAll(".content-form-control, [data-form-submit]").forEach(function (control) {
        if (control.dataset.pageShellInitiallyDisabled !== "true") {
          control.disabled = false;
        }
        delete control.dataset.pageShellInitiallyDisabled;
        delete control.dataset.pageShellDisabled;
        control.removeAttribute("aria-hidden");
        control.style.removeProperty("pointer-events");
        control.style.removeProperty("visibility");
      });
    });
  }

  function shouldRepairResponsiveLayout(shell, pageWidth) {
    return shell.dataset.pageShell === "fixed" && pageWidth > 0 && pageWidth <= 1024;
  }

  function repairResponsiveLayout(page, scale) {
    repairBreakpointBackgroundLayers(page);
    repairTinyResponsiveForms(page, scale);
    repairRescuedTrailingTexts(page, scale);
    repairTextCollisions(page, scale);
    repairScopedContentCollisions(page, scale);
    repairPostTextControlSpacing(page, scale);
    repairButtonBandSpacing(page, scale);
    repairBandTextContainment(page, scale);
    repairIconLabelCards(page, scale);
    repairSparseSectionHeights(page, scale);
    repairSectionStack(page, scale);
  }

  function repairTinyResponsiveForms(page, scale) {
    page.querySelectorAll('form.content-node[data-form="true"]').forEach(function (form) {
      if (!isVisible(form)) {
        return;
      }
      var rect = form.getBoundingClientRect();
      var width = rect.width / scale;
      if (width >= 180) {
        return;
      }
      form.setAttribute("data-page-shell-tiny-form", "true");
      form.querySelectorAll(".content-form-control, [data-form-submit]").forEach(function (control) {
        control.dataset.pageShellInitiallyDisabled = control.disabled ? "true" : "false";
        control.dataset.pageShellDisabled = "true";
        control.disabled = true;
        control.setAttribute("aria-hidden", "true");
        control.style.setProperty("pointer-events", "none");
        if (control.classList.contains("content-form-control")) {
          control.style.setProperty("visibility", "hidden");
        }
      });
    });
  }

  function repairPostTextControlSpacing(page, scale) {
    var minGap = 18;
    page.querySelectorAll(".page-section").forEach(function (section) {
      if (!isVisible(section)) {
        return;
      }
      var sectionRect = section.getBoundingClientRect();
      var texts = Array.from(section.querySelectorAll(".content-text"))
        .filter(isVisible)
        .map(function (text) {
          var rect = visualElementRect(text, scale);
          return {
            left: (rect.left - sectionRect.left) / scale,
            right: (rect.right - sectionRect.left) / scale,
            bottom: (rect.bottom - sectionRect.top) / scale,
            width: rect.width / scale,
          };
        });
      var controls = Array.from(
        section.querySelectorAll("button.content-node:not([data-form-submit]), .content-asset:not(.is-decorative):not(.bg)"),
      )
        .filter(isVisible)
        .filter(function (control) {
          if (control.closest('[data-page-shell-tiny-form="true"]')) {
            return false;
          }
          var rect = control.getBoundingClientRect();
          return rect.width / scale <= 180 && rect.height / scale <= 120;
        });

      controls.forEach(function (control) {
        var rect = visualElementRect(control, scale);
        var top = (rect.top - sectionRect.top) / scale;
        var left = (rect.left - sectionRect.left) / scale;
        var right = (rect.right - sectionRect.left) / scale;
        var width = rect.width / scale;
        var nearestBottom = -Infinity;
        texts.forEach(function (text) {
          if (text.bottom > top) {
            return;
          }
          var overlap = Math.min(right, text.right) - Math.max(left, text.left);
          if (overlap < Math.min(width, text.width) * 0.2) {
            return;
          }
          nearestBottom = Math.max(nearestBottom, text.bottom);
        });
        if (nearestBottom > -Infinity && top - nearestBottom < minGap) {
          setStackShift(control, minGap - (top - nearestBottom));
        }
      });
    });
  }

  function repairBreakpointBackgroundLayers(page) {
    page.querySelectorAll(".page-section, .page-section__inner, .content-node").forEach(function (parent) {
      var groups = new Map();
      Array.from(parent.children).forEach(function (child, order) {
        if (
          !(child instanceof HTMLElement) ||
          !child.classList.contains("content-asset") ||
          !child.classList.contains("bg") ||
          !child.classList.contains("is-decorative") ||
          !isVisible(child)
        ) {
          return;
        }
        var key = breakpointBackgroundKey(child);
        if (!key) {
          return;
        }
        if (!groups.has(key)) {
          groups.set(key, []);
        }
        groups.get(key).push({
          element: child,
          order: order,
          variantScore: breakpointBackgroundVariantScore(child),
        });
      });

      groups.forEach(function (items) {
        var variants = items.filter(function (item) {
          return item.variantScore > 0;
        });
        if (variants.length === 0) {
          return;
        }
        var keep = variants[0];
        variants.forEach(function (item) {
          if (item.variantScore > keep.variantScore || (item.variantScore === keep.variantScore && item.order > keep.order)) {
            keep = item;
          }
        });
        items.forEach(function (item) {
          if (item.element === keep.element) {
            return;
          }
          item.element.setAttribute("data-page-shell-hidden-breakpoint-bg", "true");
          item.element.style.setProperty("display", "none", "important");
        });
      });
    });
  }

  function breakpointBackgroundKey(element) {
    var token = breakpointBackgroundClass(element);
    return token ? token.replace(/(?:-w\d+)+$/i, "") : "";
  }

  function breakpointBackgroundVariantScore(element) {
    var token = breakpointBackgroundClass(element);
    var matches = token ? token.match(/-w\d+/gi) : null;
    return matches ? matches.length : 0;
  }

  function breakpointBackgroundClass(element) {
    var tokens = Array.from(element.classList).filter(function (className) {
      return /^asset-/.test(className);
    });
    return (
      tokens.find(function (className) {
        return /(?:-w\d+)+$/i.test(className);
      }) ||
      tokens[0] ||
      ""
    );
  }

  function repairButtonBandSpacing(page, scale) {
    var minGap = 22;
    page.querySelectorAll(".page-section").forEach(function (section) {
      if (!isVisible(section)) {
        return;
      }
      var sectionRect = section.getBoundingClientRect();
      var buttons = Array.from(section.querySelectorAll("button.content-node:not([data-form-submit])")).filter(isVisible);
      var bands = Array.from(section.querySelectorAll(".content-node, .content-asset"))
        .filter(isVisible)
        .filter(function (item) {
          return /\b(bandeau|banner)\b/i.test(item.className);
        });
      buttons.forEach(function (button) {
        var buttonRect = visualElementRect(button, scale);
        var buttonBottom = (buttonRect.bottom - sectionRect.top) / scale;
        var buttonLeft = (buttonRect.left - sectionRect.left) / scale;
        var buttonRight = (buttonRect.right - sectionRect.left) / scale;
        var nearestBand = null;
        var nearestTop = Infinity;
        bands.forEach(function (band) {
          if (band === button || button.contains(band) || band.contains(button)) {
            return;
          }
          var bandRect = visualElementRect(band, scale);
          var bandTop = (bandRect.top - sectionRect.top) / scale;
          if (bandTop <= buttonBottom) {
            return;
          }
          var bandLeft = (bandRect.left - sectionRect.left) / scale;
          var bandRight = (bandRect.right - sectionRect.left) / scale;
          var overlap = Math.min(buttonRight, bandRight) - Math.max(buttonLeft, bandLeft);
          if (overlap < Math.min(buttonRect.width / scale, bandRect.width / scale) * 0.2) {
            return;
          }
          if (bandTop < nearestTop) {
            nearestTop = bandTop;
            nearestBand = band;
          }
        });
        if (nearestBand && nearestTop - buttonBottom < minGap) {
          setStackShift(nearestBand, minGap - (nearestTop - buttonBottom));
        }
      });
    });
  }

  function repairBandTextContainment(page, scale) {
    var minTopGap = 4;
    var minBottomGap = 20;
    var bands = Array.from(page.querySelectorAll(".content-node, .content-asset"))
      .filter(isVisible)
      .filter(function (item) {
        return /\b(bandeau|banner)\b/i.test(item.className);
      })
      .filter(function (item) {
        return !isCardLikeBandItem(item);
      });
    bands.forEach(function (band) {
      var bandRect = visualElementRect(band, scale);
      band.querySelectorAll(".content-text").forEach(function (text) {
        if (!isVisible(text)) {
          return;
        }
        var rect = visualElementRect(text, scale);
        var topGap = (rect.top - bandRect.top) / scale;
        var bottomGap = (bandRect.bottom - rect.bottom) / scale;
        if (bottomGap >= minBottomGap) {
          return;
        }
        var shift = -(minBottomGap - bottomGap);
        if (topGap + shift < minTopGap) {
          shift = minTopGap - topGap;
        }
        var existingShift = parsePx(text.style.getPropertyValue("--content-text-stack-shift"));
        text.style.setProperty("--content-text-stack-shift", roundPx(existingShift + shift) + "px");
      });
    });
  }

  function isCardLikeBandItem(element) {
    if (element.dataset.card === "true") {
      return true;
    }
    return /\b(card|item)\b/i.test(String(element.className || ""));
  }

  function repairIconLabelCards(page, scale) {
    var minGap = 7;
    var cards = Array.from(page.querySelectorAll(".content-node"))
      .filter(isVisible)
      .filter(function (card) {
        var section = card.closest(".page-section");
        return (
          isCardLikeBandItem(card) &&
          /\b(bandeau|banner)\b/i.test(String(card.className || "") + " " + String(section ? section.className : ""))
        );
      });
    cards.forEach(function (card) {
      var cardRect = card.getBoundingClientRect();
      var assets = Array.from(card.querySelectorAll(".content-asset:not(.bg):not(.is-decorative)")).filter(isVisible);
      var texts = Array.from(card.querySelectorAll(".content-text")).filter(isVisible);
      if (assets.length === 0 || texts.length === 0) {
        return;
      }
      var assetBottom = Math.max.apply(
        null,
        assets.map(function (asset) {
          return (asset.getBoundingClientRect().bottom - cardRect.top) / scale;
        }),
      );
      texts.forEach(function (text) {
        var textRect = visualElementRect(text, scale);
        var textTop = (textRect.top - cardRect.top) / scale;
        if (textTop - assetBottom < minGap) {
          addTextShift(text, minGap - (textTop - assetBottom));
        }
      });
    });
  }

  function addTextShift(text, delta) {
    var existingShift = parsePx(text.style.getPropertyValue("--content-text-stack-shift"));
    text.style.setProperty("--content-text-stack-shift", roundPx(existingShift + delta) + "px");
  }

  function repairTextCollisions(page, scale) {
    var groups = new Map();
    page.querySelectorAll(".content-text").forEach(function (text) {
      if (!isVisible(text)) {
        return;
      }
      var parent = text.offsetParent;
      if (!(parent instanceof HTMLElement) || parent === page) {
        parent = text.closest(".content-node, .page-section") || page;
      }
      if (!groups.has(parent)) {
        groups.set(parent, []);
      }
      var parentRect = parent.getBoundingClientRect();
      var rect = visualElementRect(text, scale);
      groups.get(parent).push({
        element: text,
        top: (rect.top - parentRect.top) / scale,
        left: (rect.left - parentRect.left) / scale,
        width: rect.width / scale,
        height: rect.height / scale,
      });
    });

    groups.forEach(function (items) {
      var placed = [];
      items
        .sort(function (a, b) {
          return a.top - b.top || a.left - b.left;
        })
        .forEach(function (item) {
          var shift = 0;
          var right = item.left + item.width;
          placed.forEach(function (previous) {
            var horizontalOverlap = Math.max(
              0,
              Math.min(right, previous.right) - Math.max(item.left, previous.left),
            );
            var meaningfulOverlap =
              horizontalOverlap >= 12 ||
              horizontalOverlap >= Math.min(item.width, previous.width) * 0.16;
            if (!meaningfulOverlap) {
              return;
            }
            var shiftedTop = item.top + shift;
            if (shiftedTop < previous.bottom + 4) {
              shift = Math.max(shift, previous.bottom + 4 - item.top);
            }
          });
          if (shift > 0) {
            item.element.style.setProperty("--content-text-stack-shift", roundPx(shift) + "px");
          }
          placed.push({
            left: item.left,
            right: right,
            width: item.width,
            bottom: item.top + shift + item.height,
          });
        });
    });
  }

  function repairScopedContentCollisions(page, scale) {
    var groups = new Map();
    page.querySelectorAll(".content-text").forEach(function (text) {
      if (!isVisible(text)) {
        return;
      }
      var scope = text.closest(".page-section") || page;
      var target = contentCollisionTarget(text);
      if (!groups.has(scope)) {
        groups.set(scope, new Map());
      }
      if (!groups.get(scope).has(target)) {
        groups.get(scope).set(target, {
          element: target,
          textRects: [],
        });
      }
      groups.get(scope).get(target).textRects.push(visualElementRect(text, scale));
    });

    groups.forEach(function (targets, scope) {
      var scopeRect = scope.getBoundingClientRect();
      var items = Array.from(targets.values())
        .map(function (item) {
          var targetRect = item.element.getBoundingClientRect();
          var union = unionRects([targetRect].concat(item.textRects));
          return {
            element: item.element,
            top: (union.top - scopeRect.top) / scale,
            left: (union.left - scopeRect.left) / scale,
            width: union.width / scale,
            height: union.height / scale,
          };
        })
        .sort(function (a, b) {
          return a.top - b.top || a.left - b.left;
        });
      placeStackedItems(items, 6);
    });
  }

  function contentCollisionTarget(text) {
    var panel = text.closest("[data-accordion-panel]");
    if (panel instanceof HTMLElement) {
      return panel;
    }
    var button = text.closest("button.content-node");
    if (button instanceof HTMLElement) {
      return button;
    }
    return text;
  }

  function unionRects(rects) {
    var first = rects[0];
    var left = first.left;
    var top = first.top;
    var right = first.right;
    var bottom = first.bottom;
    rects.slice(1).forEach(function (rect) {
      left = Math.min(left, rect.left);
      top = Math.min(top, rect.top);
      right = Math.max(right, rect.right);
      bottom = Math.max(bottom, rect.bottom);
    });
    return { left: left, top: top, right: right, bottom: bottom, width: right - left, height: bottom - top };
  }

  function placeStackedItems(items, gap) {
    var placed = [];
    items.forEach(function (item) {
      var shift = 0;
      var right = item.left + item.width;
      placed.forEach(function (previous) {
        var horizontalOverlap = Math.max(
          0,
          Math.min(right, previous.right) - Math.max(item.left, previous.left),
        );
        var meaningfulOverlap =
          horizontalOverlap >= 12 ||
          horizontalOverlap >= Math.min(item.width, previous.width) * 0.16;
        if (!meaningfulOverlap) {
          return;
        }
        var shiftedTop = item.top + shift;
        if (shiftedTop < previous.bottom + gap) {
          shift = Math.max(shift, previous.bottom + gap - item.top);
        }
      });
      setStackShift(item.element, shift);
      placed.push({
        left: item.left,
        right: right,
        width: item.width,
        bottom: item.top + shift + item.height,
      });
    });
  }

  function setStackShift(element, shift) {
    var property = "--content-text-stack-shift";
    if (element.classList.contains("content-node")) {
      property = "--content-node-stack-shift";
    } else if (element.classList.contains("content-asset")) {
      property = "--content-asset-stack-shift";
    }
    var existingShift = parsePx(element.style.getPropertyValue(property));
    var nextShift = Math.max(existingShift, shift);
    if (nextShift > 0) {
      element.style.setProperty(property, roundPx(nextShift) + "px");
    } else {
      element.style.removeProperty(property);
    }
  }

  function repairSectionStack(page, scale) {
    var pageRect = page.getBoundingClientRect();
    var sections = Array.from(
      page.querySelectorAll(":scope > .page-section, .page-main > .page-section"),
    ).filter(isVisible);
    var cursorBottom = 0;
    var compactionShift = 0;
    sections
      .sort(function (a, b) {
        return a.offsetTop - b.offsetTop || a.offsetLeft - b.offsetLeft;
      })
      .forEach(function (section) {
        var sectionRect = section.getBoundingClientRect();
        var top = (sectionRect.top - pageRect.top) / scale;
        var existingShift = parsePx(section.style.getPropertyValue("--page-section-stack-shift"));
        var baseTop = top - existingShift;
        var desiredShift = cursorBottom - baseTop;
        var shift = Math.max(existingShift, desiredShift, 0);
        if (compactionShift > 0) {
          shift = Math.max(-compactionShift, desiredShift);
        }
        if (Math.abs(shift - existingShift) > 0.01) {
          section.style.setProperty("--page-section-stack-shift", roundPx(shift) + "px");
          sectionRect = section.getBoundingClientRect();
          top = (sectionRect.top - pageRect.top) / scale;
        }
        var contentBottom = measureSectionContentBottom(section, sectionRect, scale);
        cursorBottom = Math.max(cursorBottom, top + contentBottom);
        if (section.getAttribute("data-page-shell-compact-height") === "true") {
          var compactHeight = parsePx(section.style.getPropertyValue("--page-section-compact-height"));
          compactionShift += Math.max(0, sectionRect.height / scale - compactHeight);
        }
      });
  }

  function repairRescuedTrailingTexts(page, scale) {
    page.querySelectorAll(".page-section").forEach(function (section) {
      if (!isVisible(section)) {
        return;
      }
      var visibleTexts = Array.from(section.querySelectorAll(".content-text")).filter(isVisible);
      var visibleHeadings = visibleTexts.filter(isHeadingText);
      if (visibleHeadings.length === 0) {
        return;
      }
      section.querySelectorAll("p.content-text").forEach(function (text) {
        if (isVisible(text) || !hasHiddenAncestor(text, section) || !text.textContent.trim()) {
          return;
        }
        var previousText = previousTextSibling(text);
        if (!previousText || !isHeadingText(previousText)) {
          return;
        }
        var heading = findVisibleHeadingByText(visibleHeadings, previousText.textContent);
        if (!heading) {
          return;
        }
        if (hasVisibleParagraphAfter(visibleTexts, heading, scale)) {
          return;
        }
        var referenceText = nearestVisibleTextBefore(visibleTexts, heading, scale) || heading;
        rescueTrailingText(section, text, heading, referenceText, scale);
      });
    });
  }

  function hasHiddenAncestor(element, boundary) {
    var current = element.parentElement;
    while (current && current !== boundary) {
      if (current instanceof HTMLElement && !isVisible(current)) {
        return true;
      }
      current = current.parentElement;
    }
    return false;
  }

  function previousTextSibling(element) {
    var current = element.previousElementSibling;
    while (current) {
      if (current instanceof HTMLElement && current.classList.contains("content-text")) {
        return current;
      }
      current = current.previousElementSibling;
    }
    return null;
  }

  function isHeadingText(element) {
    if (!(element instanceof HTMLElement) || !element.classList.contains("content-text")) {
      return false;
    }
    var level = element.getAttribute("data-heading-level");
    if (level) {
      return true;
    }
    return /^H[1-6]$/i.test(element.tagName);
  }

  function findVisibleHeadingByText(headings, text) {
    var normalized = normalizeTextContent(text);
    if (!normalized) {
      return null;
    }
    return (
      headings.find(function (heading) {
        return normalizeTextContent(heading.textContent) === normalized;
      }) || null
    );
  }

  function normalizeTextContent(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function nearestVisibleTextBefore(texts, target, scale) {
    var targetRect = target.getBoundingClientRect();
    var best = null;
    var bestDistance = Infinity;
    texts.forEach(function (text) {
      if (text === target || isHeadingText(text)) {
        return;
      }
      var rect = visualElementRect(text, scale);
      if (rect.bottom > targetRect.top) {
        return;
      }
      var distance = targetRect.top - rect.bottom;
      if (distance < bestDistance) {
        best = text;
        bestDistance = distance;
      }
    });
    return best;
  }

  function hasVisibleParagraphAfter(texts, target, scale) {
    var targetRect = target.getBoundingClientRect();
    return texts.some(function (text) {
      if (text === target || isHeadingText(text) || text.tagName.toUpperCase() !== "P") {
        return false;
      }
      var rect = visualElementRect(text, scale);
      return rect.top >= targetRect.bottom - 1;
    });
  }

  function rescueTrailingText(section, text, heading, referenceText, scale) {
    var sectionRect = section.getBoundingClientRect();
    var headingRect = visualElementRect(heading, scale);
    var referenceRect = visualElementRect(referenceText, scale);
    var clone = text.cloneNode(true);
    var referenceStyle = window.getComputedStyle(referenceText);
    var headingStyle = window.getComputedStyle(heading);
    var gap = Math.max(10, parsePx(headingStyle.lineHeight) / Math.max(scale, 1) * 0.35);
    clone.removeAttribute("id");
    clone.setAttribute("data-page-shell-rescued-text", "true");
    clone.setAttribute("aria-hidden", "false");
    clone.style.setProperty("display", "block", "important");
    clone.style.setProperty("left", roundPx((referenceRect.left - sectionRect.left) / scale) + "px", "important");
    clone.style.setProperty("top", roundPx((headingRect.bottom - sectionRect.top) / scale + gap) + "px", "important");
    clone.style.setProperty("width", roundPx(referenceRect.width / scale) + "px", "important");
    clone.style.setProperty("height", "auto", "important");
    clone.style.setProperty("overflow", "visible", "important");
    clone.style.setProperty("white-space", "normal", "important");
    clone.style.setProperty("font-family", referenceStyle.fontFamily, "important");
    clone.style.setProperty("font-size", referenceStyle.fontSize, "important");
    clone.style.setProperty("font-weight", referenceStyle.fontWeight, "important");
    clone.style.setProperty("font-style", referenceStyle.fontStyle, "important");
    clone.style.setProperty("line-height", referenceStyle.lineHeight, "important");
    clone.style.setProperty("letter-spacing", referenceStyle.letterSpacing, "important");
    clone.style.setProperty("text-align", referenceStyle.textAlign, "important");
    clone.style.setProperty("color", referenceStyle.color, "important");
    var target = section.querySelector(".page-section__inner, .content-node");
    if (target instanceof HTMLElement) {
      target.appendChild(clone);
    }
  }

  function repairSparseSectionHeights(page, scale) {
    var bottomGap = 28;
    page.querySelectorAll(".page-section").forEach(function (section) {
      if (!isVisible(section)) {
        return;
      }
      var sectionRect = section.getBoundingClientRect();
      var sectionHeight = sectionRect.height / scale;
      if (sectionHeight < 220 || hasCoveringSectionBackground(section, sectionRect, scale)) {
        return;
      }
      var visibleBottom = measureSectionContentBottom(section, sectionRect, scale, {
        includeSectionHeight: false,
        visualOnly: true,
      });
      if (visibleBottom <= 0) {
        return;
      }
      var compactHeight = Math.ceil(visibleBottom + bottomGap);
      var blankSpace = sectionHeight - compactHeight;
      if (blankSpace < Math.max(32, sectionHeight * 0.05)) {
        return;
      }
      section.setAttribute("data-page-shell-compact-height", "true");
      section.style.setProperty("--page-section-compact-height", roundPx(compactHeight) + "px");
    });
  }

  function hasCoveringSectionBackground(section, sectionRect, scale) {
    var sectionWidth = sectionRect.width / scale;
    var sectionHeight = sectionRect.height / scale;
    return Array.from(section.querySelectorAll(".content-asset.bg, .content-asset[data-purpose='background']")).some(function (
      asset,
    ) {
      if (!isVisible(asset)) {
        return false;
      }
      var rect = asset.getBoundingClientRect();
      var left = (rect.left - sectionRect.left) / scale;
      var top = (rect.top - sectionRect.top) / scale;
      var right = (rect.right - sectionRect.left) / scale;
      var bottom = (rect.bottom - sectionRect.top) / scale;
      var coversWidth =
        rect.width / scale >= sectionWidth * 0.85 && left <= sectionWidth * 0.12 && right >= sectionWidth * 0.88;
      var coversHeight =
        rect.height / scale >= sectionHeight * 0.72 &&
        top <= sectionHeight * 0.14 &&
        bottom >= sectionHeight * 0.86;
      return coversWidth && coversHeight;
    });
  }

  function measureSectionContentBottom(section, sectionRect, scale, options) {
    var includeSectionHeight = !(options && options.includeSectionHeight === false);
    var visualOnly = Boolean(options && options.visualOnly);
    var compactHeight = parsePx(section.style.getPropertyValue("--page-section-compact-height"));
    var sectionHeight = compactHeight > 0 ? compactHeight : sectionRect.height / scale;
    var bottom = includeSectionHeight ? sectionHeight : 0;
    var selector = visualOnly
      ? ".content-text, .content-asset:not(.is-decorative):not(.bg), button.content-node, form.content-node, " +
        "[data-card='true'], [data-form='true'], .content-node"
      : ".content-node, .content-text, .content-asset:not(.is-decorative):not(.bg)";
    section.querySelectorAll(selector).forEach(function (item) {
      if (!isVisible(item) || (visualOnly && !isSectionVisualMeasurementItem(item))) {
        return;
      }
      var rect = visualElementRect(item, scale);
      bottom = Math.max(bottom, (rect.bottom - sectionRect.top) / scale);
    });
    return bottom;
  }

  function isSectionVisualMeasurementItem(item) {
    if (item.classList.contains("content-text")) {
      return true;
    }
    if (item.classList.contains("content-asset")) {
      return !item.classList.contains("is-decorative") && !item.classList.contains("bg");
    }
    if (
      item.matches("button.content-node, form.content-node") ||
      item.dataset.form === "true" ||
      item.dataset.card === "true"
    ) {
      return true;
    }
    if (/\b(bandeau|banner)\b/i.test(item.className)) {
      return true;
    }
    return Array.from(item.children).some(function (child) {
      return (
        child instanceof HTMLElement &&
        child.classList.contains("content-asset") &&
        child.classList.contains("bg") &&
        isVisible(child)
      );
    });
  }

  function updatePageShell(shell) {
    if (!(shell instanceof HTMLElement)) {
      return;
    }

    var page = shell.querySelector(".page");
    var viewport = shell.querySelector(".page-shell__viewport");
    if (!(page instanceof HTMLElement) || !(viewport instanceof HTMLElement)) {
      return;
    }

    if (shell.dataset.pageShell !== "fixed") {
      shell.style.removeProperty("--page-shell-scale");
      shell.style.removeProperty("--page-shell-width");
      shell.style.removeProperty("--page-shell-height");
      return;
    }

    var pageStyle = window.getComputedStyle(page);
    var fallbackWidth = Math.max(parsePx(pageStyle.getPropertyValue("--page-max-width")), page.offsetWidth || 0);
    var fallbackHeight = Math.max(parsePx(pageStyle.minHeight), page.offsetHeight || 0);
    var pageWidth = fallbackWidth;
    var availableWidth = Math.max(0, shell.clientWidth || shell.getBoundingClientRect().width || 0);

    if (pageWidth <= 0 || availableWidth <= 0) {
      return;
    }

    var isResponsiveFixedLayout = shouldRepairResponsiveLayout(shell, pageWidth);
    var rawScale = availableWidth / pageWidth;
    var scale = isResponsiveFixedLayout ? rawScale : Math.min(1, rawScale);
    clearLayoutRepairs(page);
    var measurementScale = currentShellScale(shell, scale);
    if (isResponsiveFixedLayout) {
      repairResponsiveLayout(page, measurementScale);
    }
    var visibleBounds = measureVisibleSectionBounds(
      page,
      fallbackWidth,
      isResponsiveFixedLayout ? 0 : fallbackHeight,
      measurementScale,
    );
    var effectiveWidth = Math.max(pageWidth, visibleBounds.width);
    if (effectiveWidth > pageWidth) {
      scale = isResponsiveFixedLayout
        ? availableWidth / effectiveWidth
        : Math.min(1, availableWidth / effectiveWidth);
    }
    var pageHeight = isResponsiveFixedLayout
      ? visibleBounds.height
      : Math.max(fallbackHeight, visibleBounds.height);
    shell.style.setProperty("--page-shell-scale", String(scale));
    shell.style.setProperty("--page-shell-width", roundPx(effectiveWidth * scale) + "px");
    shell.style.setProperty("--page-shell-height", roundPx(pageHeight * scale) + "px");
  }

  function updateAllPageShells() {
    var shells = document.querySelectorAll(".page-shell[data-page-shell]");
    shells.forEach(updatePageShell);
  }

  var scheduledFrame = 0;
  function scheduleUpdate() {
    if (scheduledFrame) {
      window.cancelAnimationFrame(scheduledFrame);
    }
    scheduledFrame = window.requestAnimationFrame(function () {
      scheduledFrame = 0;
      updateAllPageShells();
    });
  }

  window.addEventListener("resize", scheduleUpdate, { passive: true });
  window.addEventListener("load", scheduleUpdate, { passive: true });
  document.addEventListener("DOMContentLoaded", scheduleUpdate);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(scheduleUpdate).catch(function () {});
  }
})();
