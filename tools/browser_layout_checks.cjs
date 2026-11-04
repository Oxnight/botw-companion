const assert = require('node:assert/strict');

async function assertLocalizedLayout(page) {
  const viewport = page.viewportSize();
  const routeBody = page.locator('#routeBody');
  const routeHidden = await routeBody.evaluate(element => element.hidden);
  const saved = await page.evaluateHandle(() => {
    const changed = [];
    for (const element of document.querySelectorAll(
      'main > header h1, #saveInfo, .appActionButtons button, .routeSessions > label, .routeSessions > button')) {
      for (const node of element.childNodes) {
        if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) continue;
        changed.push({node, text: node.textContent});
        node.textContent = Array(3).fill(node.textContent.trim()).join(' — ');
      }
    }
    return changed;
  });
  try {
    await routeBody.evaluate(element => {element.hidden = false;});
    for (const width of [320, 390, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({width, height: viewport.height});
      const result = await page.evaluate(async () => {
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const overflow = [...document.querySelectorAll(
          'main > header, #saveInfo, .dsuControl, .appActionButtons, .appActionButtons button, .routeSessions, .routeSessions > *')]
          .filter(element => element.clientWidth && element.scrollWidth > element.clientWidth + 2)
          .map(element => element.id || element.className || element.tagName);
        const overlaps = [];
        for (const selector of ['main > header', '.appActionButtons', '.routeSessions']) {
          const boxes = [...document.querySelector(selector).children]
            .map(element => element.getBoundingClientRect()).filter(box => box.width && box.height);
          for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i], b = boxes[j];
            if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
                Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) overlaps.push(selector);
          }
        }
        return {overflow, overlaps, buttonHeights: [...document.querySelectorAll('.appActionButtons button')]
          .map(element => element.getBoundingClientRect().height)};
      });
      const language = await page.locator('html').getAttribute('lang');
      assert.deepEqual(result.overflow, [], `${language}/${width}: long text overflows ${result.overflow}`);
      assert.deepEqual(result.overlaps, [], `${language}/${width}: controls overlap ${result.overlaps}`);
      assert(result.buttonHeights.every(height => height >= 44), `${language}/${width}: action target too short`);
    }
  } finally {
    await saved.evaluate(changed => changed.forEach(({node, text}) => {node.textContent = text;}));
    await saved.dispose();
    await routeBody.evaluate((element, hidden) => {element.hidden = hidden;}, routeHidden);
    await page.setViewportSize(viewport);
  }
}

module.exports = {assertLocalizedLayout};
