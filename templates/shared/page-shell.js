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
    page.querySelectorAll('[data-page-shell-normalized-text="true"]').forEach(function (text) {
      text.removeAttribute("data-page-shell-normalized-text");
      text.style.removeProperty("font-size");
      text.style.removeProperty("line-height");
      text.style.removeProperty("left");
      text.style.removeProperty("width");
      text.style.removeProperty("height");
      text.style.removeProperty("overflow");
    });
    page.querySelectorAll('[data-page-shell-stretched-band="true"]').forEach(function (item) {
      item.removeAttribute("data-page-shell-stretched-band");
      item.style.removeProperty("height");
      item.style.removeProperty("min-height");
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
      form.removeAttribute("data-page-shell-readable-form");
      form.style.removeProperty("transform");
      form.style.removeProperty("transform-origin");
      form.style.removeProperty("left");
      form.querySelectorAll(".content-form-control, [data-form-submit]").forEach(function (control) {
        if (control.dataset.pageShellInitiallyDisabled !== "true") {
          control.disabled = false;
        }
        delete control.dataset.pageShellInitiallyDisabled;
        delete control.dataset.pageShellDisabled;
        control.removeAttribute("aria-hidden");
        control.style.removeProperty("pointer-events");
        control.style.removeProperty("visibility");
        control.style.removeProperty("font-size");
        control.style.removeProperty("line-height");
        control.style.removeProperty("padding");
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
    repairResponsiveTextSizeConsistency(page, scale);
    repairTextCollisions(page, scale);
    repairAnchoredRescuedTexts(page, scale);
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
      if (repairReadableTinyForm(form, scale, width)) {
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

  function repairReadableTinyForm(form, scale, width) {
    var section = form.closest(".page-section");
    if (!(section instanceof HTMLElement)) {
      return false;
    }
    var sectionRect = section.getBoundingClientRect();
    var sectionWidth = sectionRect.width / scale;
    if (sectionWidth > 480 || width <= 0) {
      return false;
    }
    var targetWidth = Math.min(176, Math.max(156, sectionWidth * 0.42));
    if (targetWidth <= width * 1.2) {
      return false;
    }
    var formRect = form.getBoundingClientRect();
    var formLeft = (formRect.left - sectionRect.left) / scale;
    var formTop = (formRect.top - sectionRect.top) / scale;
    var formScale = targetWidth / width;
    var sectionPadding = 10;
    var nextLeft = Math.min(formLeft, sectionWidth - targetWidth - sectionPadding);
    nextLeft = Math.max(sectionPadding, nextLeft);
    form.setAttribute("data-page-shell-tiny-form", "true");
    form.setAttribute("data-page-shell-readable-form", "true");
    form.style.setProperty("left", roundPx(nextLeft) + "px", "important");
    form.style.setProperty("transform-origin", "top left");
    form.style.setProperty(
      "transform",
      "translateY(var(--content-node-stack-shift, 0px)) scale(" + roundPx(formScale) + ")",
    );
    repairReadableFormControlText(form, scale);
    stretchFormVisualBand(form, section, formTop + formRect.height / scale * formScale + sectionPadding);
    return true;
  }

  function repairReadableFormControlText(form, scale) {
    form.querySelectorAll(".content-form-control").forEach(function (control) {
      if (!(control instanceof HTMLElement) || !isVisible(control)) {
        return;
      }
      var rect = control.getBoundingClientRect();
      var height = rect.height / scale;
      if (height <= 0) {
        return;
      }
      var fontSize = Math.min(7, Math.max(5.2, height * 0.58));
      var lineHeight = control.tagName.toUpperCase() === "TEXTAREA" ? fontSize * 1.25 : height;
      var padding = Math.max(2, Math.min(4, height * 0.3));
      control.style.setProperty("font-size", roundPx(fontSize) + "px", "important");
      control.style.setProperty("line-height", roundPx(lineHeight) + "px", "important");
      control.style.setProperty("padding", "0 " + roundPx(padding) + "px", "important");
    });
  }

  function stretchFormVisualBand(form, section, minHeight) {
    var sectionRect = section.getBoundingClientRect();
    var formAncestor = form.parentElement;
    while (formAncestor && formAncestor !== section) {
      if (/\b(bandeau|banner|footer|contact)\b/i.test(String(formAncestor.className || ""))) {
        break;
      }
      formAncestor = formAncestor.parentElement;
    }
    var target = formAncestor instanceof HTMLElement && formAncestor !== section ? formAncestor : section;
    var targetRect = target.getBoundingClientRect();
    var targetTop = target === section ? 0 : (targetRect.top - sectionRect.top) / scaleFromRects(sectionRect, section);
    var currentHeight = targetRect.height / scaleFromRects(sectionRect, section);
    var nextHeight = Math.ceil(minHeight - targetTop);
    if (nextHeight <= currentHeight) {
      return;
    }
    var delta = nextHeight - currentHeight;
    var shiftedBottom = targetTop + nextHeight;
    var parent = target.parentElement;
    target.style.setProperty("height", roundPx(nextHeight) + "px", "important");
    target.style.setProperty("min-height", roundPx(nextHeight) + "px", "important");
    target.setAttribute("data-page-shell-stretched-band", "true");
    target.querySelectorAll(".content-asset.bg, .content-asset[data-purpose='background']").forEach(function (asset) {
      if (!(asset instanceof HTMLElement)) {
        return;
      }
      asset.style.setProperty("height", "100%", "important");
      asset.setAttribute("data-page-shell-stretched-band", "true");
    });
    if (parent instanceof HTMLElement) {
      Array.from(parent.children).forEach(function (sibling) {
        if (!(sibling instanceof HTMLElement) || sibling === target || !isVisible(sibling)) {
          return;
        }
        var siblingRect = sibling.getBoundingClientRect();
        var siblingTop = (siblingRect.top - sectionRect.top) / scaleFromRects(sectionRect, section);
        if (siblingTop < targetTop + currentHeight - 2) {
          return;
        }
        setStackShift(sibling, delta);
        shiftedBottom = Math.max(shiftedBottom, siblingTop + siblingRect.height / scaleFromRects(sectionRect, section) + delta);
      });
    }
    stretchSectionForBand(section, shiftedBottom + 2);
  }

  function scaleFromRects(sectionRect, section) {
    var sectionWidth = parsePx(window.getComputedStyle(section).width) || section.offsetWidth || sectionRect.width;
    return sectionWidth > 0 ? sectionRect.width / sectionWidth : 1;
  }

  function stretchSectionForBand(section, minHeight) {
    var inner = section.querySelector(":scope > .page-section__inner");
    var sectionHeight = parsePx(window.getComputedStyle(section).height) || section.offsetHeight || 0;
    if (minHeight <= sectionHeight) {
      return;
    }
    [section, inner].forEach(function (item) {
      if (!(item instanceof HTMLElement)) {
        return;
      }
      item.style.setProperty("height", roundPx(minHeight) + "px", "important");
      item.style.setProperty("min-height", roundPx(minHeight) + "px", "important");
      item.setAttribute("data-page-shell-stretched-band", "true");
    });
  }

  function repairResponsiveTextSizeConsistency(page, scale) {
    var pageRect = page.getBoundingClientRect();
    var pageWidth = pageRect.width / scale;
    if (pageWidth <= 0 || pageWidth > 1024) {
      return;
    }
    var items = Array.from(page.querySelectorAll("p.content-text"))
      .filter(isResponsiveBodyTextCandidate)
      .map(function (text) {
        var style = window.getComputedStyle(text);
        var rect = visualElementRect(text, scale);
        var section = text.closest(".page-section") || page;
        var sectionRect = section.getBoundingClientRect();
        return {
          element: text,
          section: section,
          sectionRect: sectionRect,
          fontSize: parsePx(style.fontSize),
          lineHeight: parsePx(style.lineHeight),
          left: (rect.left - sectionRect.left) / scale,
          width: rect.width / scale,
          height: rect.height / scale,
        };
      })
      .filter(function (item) {
        return item.fontSize > 0 && item.width > 0;
      });

    if (items.length < 3) {
      return;
    }

    var fontSizes = items.map(function (item) {
      return item.fontSize;
    });
    var lineRatios = items
      .map(function (item) {
        return item.lineHeight > 0 ? item.lineHeight / item.fontSize : 0;
      })
      .filter(function (ratio) {
        return ratio >= 1 && ratio <= 2;
      });
    var widths = items.map(function (item) {
      return item.width;
    });
    var targetFontSize = median(fontSizes);
    if (pageWidth <= 480) {
      targetFontSize = Math.max(targetFontSize, 8.5);
    }
    targetFontSize = Math.min(targetFontSize, pageWidth <= 480 ? 10 : 14);
    var lineRatio = Math.min(1.5, Math.max(1.2, median(lineRatios) || 1.25));
    var targetLineHeight = targetFontSize * lineRatio;
    var targetWidth = Math.min(median(widths), pageWidth - 32);
    if (pageWidth <= 480) {
      targetWidth = Math.max(targetWidth, Math.min(pageWidth - 32, pageWidth * 0.68));
    }

    items.forEach(function (item) {
      if (item.fontSize >= targetFontSize * 0.86) {
        return;
      }
      var sectionWidth = item.sectionRect.width / scale;
      var nextWidth = Math.min(Math.max(item.width, targetWidth), Math.max(1, sectionWidth - 24));
      var nextFontSize = targetFontSize;
      var nextLineHeight = targetLineHeight;
      var nextLeft = item.left + item.width / 2 - nextWidth / 2;
      nextLeft = Math.min(Math.max(12, nextLeft), Math.max(12, sectionWidth - nextWidth - 12));
      var maxHeight = pageWidth <= 480 ? Math.max(120, Math.min(160, item.height * 2.25)) : Infinity;
      if (Number.isFinite(maxHeight)) {
        var estimatedHeight = estimateNormalizedTextHeight(item, nextWidth, nextFontSize, nextLineHeight, scale);
        if (estimatedHeight > maxHeight) {
          var shrink = Math.sqrt(maxHeight / estimatedHeight);
          nextFontSize = Math.max(item.fontSize * 1.15, nextFontSize * shrink);
          nextLineHeight = nextFontSize * lineRatio;
        }
      }
      item.element.setAttribute("data-page-shell-normalized-text", "true");
      item.element.style.setProperty("font-size", roundPx(nextFontSize) + "px", "important");
      item.element.style.setProperty("line-height", roundPx(nextLineHeight) + "px", "important");
      item.element.style.setProperty("left", roundPx(nextLeft) + "px", "important");
      item.element.style.setProperty("width", roundPx(nextWidth) + "px", "important");
      item.element.style.setProperty("height", "auto", "important");
      item.element.style.setProperty("overflow", "visible", "important");
    });
  }

  function estimateNormalizedTextHeight(item, width, fontSize, lineHeight, scale) {
    item.element.style.setProperty("font-size", roundPx(fontSize) + "px", "important");
    item.element.style.setProperty("line-height", roundPx(lineHeight) + "px", "important");
    item.element.style.setProperty("width", roundPx(width) + "px", "important");
    item.element.style.setProperty("height", "auto", "important");
    item.element.style.setProperty("overflow", "visible", "important");
    var rect = visualElementRect(item.element, scale);
    item.element.style.removeProperty("font-size");
    item.element.style.removeProperty("line-height");
    item.element.style.removeProperty("width");
    item.element.style.removeProperty("height");
    item.element.style.removeProperty("overflow");
    return rect.height / scale;
  }

  function isResponsiveBodyTextCandidate(text) {
    if (!isVisible(text) || isHeadingText(text)) {
      return false;
    }
    var content = normalizeTextContent(text.textContent);
    if (content.length < 80) {
      return false;
    }
    var className = String(text.className || "");
    if (/\b(button|footer|label|coord|legal|copyright)\b/i.test(className)) {
      return false;
    }
    if (text.closest("button, form, [data-form='true'], [data-form-submit]")) {
      return false;
    }
    var framed = text.closest(".content-node, .page-section");
    while (framed instanceof HTMLElement) {
      if (/\b(bandeau|banner|hero|nav|menu)\b/i.test(String(framed.className || ""))) {
        return false;
      }
      if (framed.classList.contains("page-section")) {
        break;
      }
      framed = framed.parentElement;
    }
    return true;
  }

  function median(values) {
    if (!values || values.length === 0) {
      return 0;
    }
    var sorted = values
      .slice()
      .filter(function (value) {
        return Number.isFinite(value);
      })
      .sort(function (a, b) {
        return a - b;
      });
    if (sorted.length === 0) {
      return 0;
    }
    var middle = Math.floor(sorted.length / 2);
    if (sorted.length % 2) {
      return sorted[middle];
    }
    return (sorted[middle - 1] + sorted[middle]) / 2;
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
            top: (rect.top - sectionRect.top) / scale,
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
            var existingShift = parsePx(item.element.style.getPropertyValue("--content-text-stack-shift"));
            item.element.style.setProperty("--content-text-stack-shift", roundPx(Math.max(existingShift, shift)) + "px");
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
    clone.setAttribute("data-page-shell-rescue-heading-text", normalizeTextContent(heading.textContent));
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

  function repairAnchoredRescuedTexts(page, scale) {
    page.querySelectorAll('[data-page-shell-rescued-text="true"]').forEach(function (text) {
      if (!(text instanceof HTMLElement) || !isVisible(text)) {
        return;
      }
      var section = text.closest(".page-section");
      if (!(section instanceof HTMLElement)) {
        return;
      }
      var headingText = text.getAttribute("data-page-shell-rescue-heading-text");
      if (!headingText) {
        return;
      }
      var heading = findVisibleHeadingByText(
        Array.from(section.querySelectorAll(".content-text")).filter(function (candidate) {
          return candidate !== text && isVisible(candidate) && isHeadingText(candidate);
        }),
        headingText,
      );
      if (!(heading instanceof HTMLElement)) {
        return;
      }
      ensureRescuedHeadingClearance(section, heading, text, scale);
      var sectionRect = section.getBoundingClientRect();
      var headingRect = visualElementRect(heading, scale);
      var headingStyle = window.getComputedStyle(heading);
      var gap = Math.max(8, parsePx(headingStyle.lineHeight) / Math.max(scale, 1) * 0.45);
      text.style.removeProperty("--content-text-stack-shift");
      text.style.setProperty("top", roundPx((headingRect.bottom - sectionRect.top) / scale + gap) + "px", "important");
    });
  }

  function ensureRescuedHeadingClearance(section, heading, rescuedText, scale) {
    var minGap = 12;
    var sectionRect = section.getBoundingClientRect();
    var headingRect = visualElementRect(heading, scale);
    var headingTop = (headingRect.top - sectionRect.top) / scale;
    var headingLeft = (headingRect.left - sectionRect.left) / scale;
    var headingRight = (headingRect.right - sectionRect.left) / scale;
    var headingWidth = headingRect.width / scale;
    var previousBottom = -Infinity;
    Array.from(section.querySelectorAll("p.content-text"))
      .filter(isVisible)
      .forEach(function (paragraph) {
        if (paragraph === rescuedText) {
          return;
        }
        var rect = visualElementRect(paragraph, scale);
        var top = (rect.top - sectionRect.top) / scale;
        if (top > headingTop) {
          return;
        }
        var left = (rect.left - sectionRect.left) / scale;
        var right = (rect.right - sectionRect.left) / scale;
        var width = rect.width / scale;
        var overlap = Math.min(headingRight, right) - Math.max(headingLeft, left);
        if (overlap < Math.min(headingWidth, width) * 0.16) {
          return;
        }
        previousBottom = Math.max(previousBottom, (rect.bottom - sectionRect.top) / scale);
      });
    if (previousBottom > -Infinity && headingTop - previousBottom < minGap) {
      addTextShift(heading, minGap - (headingTop - previousBottom));
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
