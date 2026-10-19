'use strict';

// npm ci --prefix tests/browser
// npx --prefix tests/browser playwright install chromium webkit
// npm test --prefix tests/browser
// GENESIS_BASE_URL can target the published Pages build in an isolated browser context.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium, webkit} = require('playwright');
const root = path.resolve(__dirname, '../..');
const artifactDir = process.env.GENESIS_SCREENSHOTS;
if (artifactDir) fs.mkdirSync(artifactDir, {recursive: true});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function localServer() {
  const types = {'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json'};
  return http.createServer((req,res) => {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const file = path.resolve(root, '.' + pathname + (pathname.endsWith('/') ? 'index.html' : ''));
    if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    fs.readFile(file, (error,data) => {
      if (error) { res.writeHead(404).end(); return; }
      res.writeHead(200, {'Content-Type':types[path.extname(file)] || 'application/octet-stream'}).end(data);
    });
  });
}

async function usable(page, selector, minimum = 0) {
  const item = page.locator(selector);
  assert(await item.isVisible(), `${selector} must be visible`);
  const box = await item.boundingBox();
  const viewport = page.viewportSize();
  assert(box.x >= -1 && box.y >= -1 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1,
    `${selector} outside ${JSON.stringify(viewport)}: ${JSON.stringify(box)}`);
  assert(box.width >= minimum && box.height >= minimum, `${selector} touch target too small: ${JSON.stringify(box)}`);
  assert(await item.evaluate(el => {
    const b = el.getBoundingClientRect();
    const hit = document.elementFromPoint(b.x + b.width/2, b.y + b.height/2);
    return el === hit || el.contains(hit);
  }), `${selector} is covered by another element`);
  return box;
}

const position = page => page.evaluate(() => GENESIS_WORLD_RUNTIME_V5.getCanonicalState().player_position);
const distance = (a,b) => Math.hypot(a.x-b.x,a.y-b.y);

async function check(page, base, entry, width, height, touch, label) {
  await page.setViewportSize({width,height});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(new URL(entry, base).href);
  await page.locator('#genesis-birth-intent').waitFor();
  if (touch) assert.notEqual(await page.evaluate(() => document.activeElement.id), 'genesis-birth-intent', 'touch boot must not open keyboard');
  await usable(page, '#genesis-birth-submit', touch ? 44 : 0);
  if (artifactDir && width === 390) await page.screenshot({path:path.join(artifactDir, `${label}-birth.png`)});
  await page.locator('#genesis-birth-intent').fill('вперед');
  await Promise.all([page.waitForNavigation(), page.locator('#genesis-birth-submit').click()]);
  await page.waitForFunction(() => GENESIS_WORLD_RUNTIME_V5.getCanonicalState().player_position.y > 1);
  await page.waitForFunction(() => !document.querySelector('#action-submit').disabled);
  assert(await page.locator('#welcome').isHidden(), 'first cause should enter world');
  if (touch) assert.notEqual(await page.evaluate(() => document.activeElement.id), 'action-input', 'submitted touch command must dismiss keyboard');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'horizontal overflow');
  await usable(page, '#action-input', touch ? 44 : 0);
  await usable(page, '#action-submit', touch ? 44 : 0);
  await usable(page, '#chronicle-toggle', touch ? 44 : 0);
  if (touch) {
    for (const selector of ['up','left','down','right']) await usable(page, `[data-move="${selector}"]`, 44);
    await usable(page, '[data-action="jump"]', 44);
    const start = await position(page);
    await page.locator('[data-move="up"]').tap();
    await sleep(120);
    assert(distance(start, await position(page)) > .01, 'a touch tap must take a step');
    const up = await usable(page, '[data-move="up"]', 44);
    const before = await position(page);
    await page.mouse.move(up.x + up.width/2, up.y + up.height/2);
    await page.mouse.down();
    await sleep(240);
    await page.mouse.move(width/2, height/2);
    await page.mouse.up();
    assert(distance(before, await position(page)) > .1, 'holding control must walk');
    await sleep(80);
    const released = await position(page);
    await sleep(160);
    assert(distance(released, await position(page)) < .001, 'release outside control must stop walking');
    await page.locator('[data-action="jump"]').tap();
    await page.waitForFunction(() => !GENESIS_WORLD_RUNTIME_V5.getPresentationState().grounded);
    await page.waitForFunction(() => GENESIS_WORLD_RUNTIME_V5.getPresentationState().grounded);
    // Cancellation/blur must also clear a held direction.
    await page.locator('[data-move="left"]').dispatchEvent('pointerdown', {pointerId:31,pointerType:'touch',isPrimary:true,button:0});
    await sleep(100);
    await page.locator('[data-move="left"]').dispatchEvent('pointercancel', {pointerId:31,pointerType:'touch'});
    const cancelled = await position(page);
    await sleep(120);
    assert(distance(cancelled, await position(page)) < .001, 'cancel must stop walking');
    await page.locator('[data-move="right"]').dispatchEvent('pointerdown', {pointerId:32,pointerType:'touch',isPrimary:true,button:0});
    await sleep(100);
    await page.evaluate(() => dispatchEvent(new Event('blur')));
    const blurred = await position(page);
    await sleep(120);
    assert(distance(blurred, await position(page)) < .001, 'blur must stop walking');
  } else {
    await page.locator('#genesis-world').focus();
    const before = await position(page);
    await page.keyboard.down('w'); await sleep(200); await page.keyboard.up('w');
    assert(distance(before, await position(page)) > .1, 'keyboard movement regression');
  }
  const beforeCommand = await position(page);
  await page.locator('#action-input').fill('вперед');
  await page.locator('#action-submit').click();
  await page.waitForFunction(before => {
    const p = GENESIS_WORLD_RUNTIME_V5.getCanonicalState().player_position;
    return Math.hypot(p.x-before.x,p.y-before.y) > .9;
  }, beforeCommand);
  await page.waitForFunction(() => !document.querySelector('#action-submit').disabled);
  if (!touch) await page.locator('#action-input').blur();
  if (touch && width === 390) {
    // Resize the same running world, rather than opening a new landscape save.
    await page.setViewportSize({width:844,height:390});
    await usable(page, '[data-move="up"]', 44);
    await usable(page, '#action-submit', 44);
    await page.setViewportSize({width,height});
    // Model the visual viewport shrink separately from the layout viewport.
    // This checks our Safari inset math; physical iOS keyboard QA remains separate.
    await page.locator('#action-input').focus();
    await page.evaluate(() => {
      Object.defineProperties(visualViewport, {
        height:{configurable:true,value:320}, offsetTop:{configurable:true,value:0}
      });
      visualViewport.dispatchEvent(new Event('resize'));
    });
    const submit = await usable(page, '#action-submit', 44);
    assert(submit.y + submit.height <= 320, 'composer must stay above modeled keyboard');
    assert(await page.locator('.mobile-pad').isHidden(), 'pad should yield to keyboard');
    await page.evaluate(() => {
      delete visualViewport.height; delete visualViewport.offsetTop;
      visualViewport.dispatchEvent(new Event('resize'));
    });
    await page.locator('#action-input').blur();
    await usable(page, '[data-move="up"]', 44);
  }
  await page.locator('#chronicle-toggle').click();
  await usable(page, '[data-close="chronicle-panel"]', touch ? 44 : 0);
  await page.locator('[data-close="chronicle-panel"]').click();
  const saved = await position(page);
  if (artifactDir) await page.screenshot({path:path.join(artifactDir, `${label}.png`)});
  await page.reload();
  await page.locator('#enter-world').waitFor();
  await usable(page, '#enter-world', touch ? 44 : 0);
  await page.locator('#enter-world').click();
  assert(distance(saved, await position(page)) < .001, 'reload must preserve player position');
  assert.deepEqual(errors, [], 'browser runtime errors');
  console.log(`PASS ${label}: birth, command, ${touch?'touch controls, release/cancel/blur, jump':'keyboard'}, chronicle, save/reload`);
}

(async () => {
  const server = localServer();
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const base = process.env.GENESIS_BASE_URL || `http://127.0.0.1:${server.address().port}/`;
  const cases = [
    ['small-phone',320,568,true], ['iphone-se',375,667,true], ['iphone-portrait',390,844,true],
    ['iphone-large',430,932,true], ['phone-landscape',844,390,true], ['tablet',820,1180,true],
    ['desktop',1280,800,false],
  ];
  try {
    for (const [name,type] of Object.entries({chromium,webkit})) {
      const browser = await type.launch({headless:true});
      try {
        for (const [device,width,height,touch] of cases) {
          const context = await browser.newContext({viewport:{width,height},hasTouch:touch,isMobile:touch,deviceScaleFactor:1});
          try { await check(await context.newPage(),base,'',width,height,touch,`${name}-${device}`); }
          finally { await context.close(); }
        }
        // The secondary entrypoint must keep the same live controls/dependencies.
        const context = await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
        try { await check(await context.newPage(),base,'site/',390,844,true,`${name}-site-portrait`); }
        finally { await context.close(); }
      } finally { await browser.close(); }
    }
  } finally { server.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
