'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium,webkit}=require('playwright');
const {localServer,usable}=require('./mobile-smoke.cjs');
const artifactDir=process.env.GENESIS_SCREENSHOTS;
const position=page=>page.evaluate(()=>GENESIS_WORLD_RUNTIME_V5.getCanonicalState().player_position);
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
async function play(page,base,label){
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 // Keep this gameplay gate deterministic: external assets are optional; the
 // actual procedural scene, command bridge and persistence run unmodified.
 const origin=new URL(base).origin;
 await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 await page.goto(base);
 await page.locator('#genesis-birth-intent').fill('построй старый каменный маяк');
 await Promise.all([page.waitForNavigation(),page.locator('#genesis-birth-submit').click()]);
 await page.waitForFunction(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions().length>0);
 await page.waitForFunction(()=>!document.querySelector('#action-submit').disabled);
 assert.match(await page.locator('#action-result').innerText(),/Постройка создана/);
 assert.equal(await page.locator('.command-technical-report').getAttribute('open'),null);
 assert(await page.locator('#world-status-panel').isHidden(),'diagnostics hidden in normal play');
 await usable(page,'#world-interact',44);
 if(label.endsWith('desktop')){
  await page.locator('#action-input').fill('подойди к маяку');
  await page.locator('#action-submit').click();
 }else await page.locator('#world-interact').click();
 try{await page.waitForFunction(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0]?.distance<=1.1);}
 catch(error){console.error('APPROACH_STATE',label,await page.evaluate(()=>({active:document.activeElement?.id,position:GENESIS_WORLD_RUNTIME_V5.getCanonicalState().player_position,nearby:GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions(),result:document.querySelector('#action-result').innerText,drawer:document.body.dataset.genesisDrawerOpen})));throw error;}
 await page.waitForFunction(()=>document.querySelector('#world-interact').textContent.includes('Открыть'));
 const approached=await position(page);
 await page.locator('#world-interact').click();
 await page.waitForFunction(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0]?.door_open);
 await page.locator('#world-interact').click();
 await page.waitForFunction(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0]?.beacon_lit);
 assert.match(await page.locator('#action-result').innerText(),/Маяк зажжён/);
 assert.match(await page.locator('#objective-title').innerText(),/горит/);
 await page.locator('[data-player-command="осмотри место"]').click();
 await page.waitForFunction(()=>document.querySelector('#action-result').textContent.includes('Ты осмотрел место'));
 assert.match(await page.locator('#action-result').innerText(),/дверь открыта.*огонь горит/);
 // History and settings are ordinary accessible dialogs and stop game input.
 await page.locator('#chronicle-toggle').click();
 assert.match(await page.locator('#chronicle-list').innerText(),/Зажжён огонь маяка/);
 await page.locator('[data-close="chronicle-panel"]').click();
 await page.locator('#settings-toggle').focus();await page.keyboard.press('Enter');
 await page.locator('#settings-panel').waitFor({state:'visible'});
 const beforeDialog=await position(page);
 await page.keyboard.down('w');await page.waitForTimeout(150);await page.keyboard.up('w');
 assert(distance(beforeDialog,await position(page))<.001,'dialog prevents background movement');
 await page.locator('#save-export').scrollIntoViewIfNeeded();
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#save-export').click()]);
 const file=await download.path();assert(file,'export download created');
 const exported=JSON.parse(fs.readFileSync(file,'utf8'));
 assert.equal(exported.schema,'janus.genesis.browser_export.v1');
 await page.locator('[data-close="settings-panel"]').focus();await page.keyboard.press('Enter');
 await page.locator('#settings-panel').waitFor({state:'hidden'});
 // Change the world, then verify preview/cancel does not silently restore it.
 await page.locator('#action-input').fill('погаси маяк');await page.locator('#action-submit').click();
 await page.waitForFunction(()=>!GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0]?.beacon_lit);
 await page.locator('#settings-toggle').click();
 await page.locator('#save-import').setInputFiles(file);
 await page.locator('#save-import-confirm').waitFor({state:'visible'});
 assert.equal(await page.evaluate(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0].beacon_lit),false,'preview leaves current world alone');
 await page.locator('#save-import-cancel').click();
 assert.equal(await page.evaluate(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0].beacon_lit),false,'cancel leaves current world alone');
 // Invalid files must preserve the world and offer no replacement action.
 await page.locator('#save-import').setInputFiles({name:'broken.json',mimeType:'application/json',buffer:Buffer.from('{"schema":"bad"}')});
 await page.waitForFunction(()=>document.querySelector('#save-import-status').textContent.length>0);
 assert(await page.locator('#save-import-confirm').isHidden(),'invalid import cannot be confirmed');
 await page.locator('#save-import').setInputFiles(file);
 await page.locator('#save-import-confirm').waitFor({state:'visible'});
 await Promise.all([page.waitForNavigation(),page.locator('#save-import-confirm').click()]);
 await page.locator('#enter-world').click();
 assert.equal(await page.evaluate(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0].beacon_lit),true,'import restores lit state');
 assert.equal(await page.evaluate(()=>GENESIS_WORLD_RUNTIME_V5.getNearbyInteractions()[0].door_open),true);
 assert(distance(exported.save.player_position,await position(page))<.001,'import restores saved position');
 await page.locator('#action-input').fill('невыполнимая абракадабра');await page.locator('#action-submit').click();
 await page.waitForFunction(()=>document.querySelector('#action-result').textContent.includes('Не удалось понять команду'));
 assert(await page.locator('.command-suggestion').count()>0,'failure offers a next action');
 if(artifactDir){fs.mkdirSync(artifactDir,{recursive:true});await page.locator('[data-player-command="осмотри место"]').click();await page.waitForFunction(()=>!document.querySelector('#action-submit').disabled);await page.screenshot({path:path.join(artifactDir,`${label}-playable.png`)});}
 assert.deepEqual(errors,[],'runtime errors');
 console.log(`PASS ${label}: birth→build→approach→door→beacon→inspect→history→export→cancel→import`);
}
(async()=>{
 const server=localServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=process.env.GENESIS_BASE_URL||`http://127.0.0.1:${server.address().port}/`;
 try{
  for(const [name,type]of Object.entries({chromium,webkit})){
   const browser=await type.launch({headless:true});
   try{
    for(const [device,width,height,touch]of [['portrait',390,844,true],['small',320,568,true],['desktop',1280,800,false]].filter(([device])=>!process.env.GENESIS_DEVICE||device===process.env.GENESIS_DEVICE)){
     const context=await browser.newContext({viewport:{width,height},isMobile:touch,hasTouch:touch,deviceScaleFactor:1,acceptDownloads:true});
     try{await play(await context.newPage(),base,`${name}-${device}`);}finally{await context.close();}
    }
   }finally{await browser.close();}
  }
 }finally{server.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
