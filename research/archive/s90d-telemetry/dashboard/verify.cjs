// Live dashboard smoke check; mocked responses exercise outage display only.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1200}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 const url=process.env.DASHBOARD_URL||'http://192.0.2.20:20491/';
 await page.goto(url);await page.waitForFunction(()=>document.querySelector('#connection').textContent==='Receiving telemetry');
 assert.equal(await page.locator('.chart').count(),6);
 assert.equal(await page.locator('#device option').count(),2);
 assert.equal(await page.locator('#overview article').count(),2);
 const switchResponse=page.waitForResponse(r=>r.url().includes('device=qn90a'));await page.locator('#device').selectOption('qn90a');assert.equal((await switchResponse).status(),200);
 await page.waitForFunction(()=>document.querySelector('#device-name').textContent.endsWith('QN90A') && document.querySelector('#cpu-value').textContent!=='—');
 assert.equal(await page.locator('#connection').textContent(),'Receiving telemetry');
 await page.screenshot({path:path.join(process.env.HOME,'.local/share/samsung-tv-research/telemetry/dashboard/qn90a.png'),fullPage:true});
 const backResponse=page.waitForResponse(r=>r.url().includes('device=s90d'));await page.locator('#device').selectOption('s90d');await backResponse;
 await page.waitForFunction(()=>document.querySelector('#device-name').textContent.endsWith('S90D'));
 assert.ok(await page.locator('.chart svg .line').count()>=6);
 assert.notEqual(await page.locator('#cpu-value').textContent(),'—');
 assert.notEqual(await page.locator('#memory-value').textContent(),'—');
 const screenshot=path.join(process.env.HOME,'.local/share/samsung-tv-research/telemetry/dashboard/desktop.png');
 await page.screenshot({path:screenshot,fullPage:true});
 await page.locator('#pause').click();assert.equal(await page.locator('#connection').textContent(),'View paused');
 for(const range of ['3600','21600','86400','900']){
  const response=page.waitForResponse(r=>r.url().includes('/api/snapshot?range='+range));await page.locator('[data-range="'+range+'"]').click();assert.equal((await response).status(),200);
  assert.equal(await page.locator('[data-range="'+range+'"]').getAttribute('aria-pressed'),'true');
 }
 await page.locator('#chart-cpu svg').focus();await page.keyboard.press('ArrowLeft');assert.match(await page.locator('#chart-cpu .chart-tip').textContent(),/Active:/);
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:path.join(process.env.HOME,'.local/share/samsung-tv-research/telemetry/dashboard/mobile.png'),fullPage:true});
 const snapshot=await(await page.request.get(url+'api/snapshot?range=900')).json();
 snapshot.latest.received_at=snapshot.server_time-120;
 await page.route('**/api/snapshot*',route=>route.fulfill({json:snapshot}));
 await page.locator('[data-range="900"]').click();await page.waitForFunction(()=>document.querySelector('#connection').textContent==='No recent telemetry');
 assert.equal(await page.locator('#cpu-value').textContent(),'—');assert.ok(await page.locator('.chart svg .line').count()>0);
 await page.unroute('**/api/snapshot*');
 await page.route('**/api/snapshot*',route=>route.fulfill({status:503,body:'Unavailable'}));
 await page.locator('[data-range="900"]').click();await page.waitForFunction(()=>document.querySelector('#connection').textContent==='Dashboard disconnected');
 assert.equal(await page.locator('#cpu-value').textContent(),'—');
 assert.equal(await page.locator('#notice').isVisible(),true);
 // A simulated 503 deliberately produces a browser network diagnostic.
 assert.deepEqual(errors.filter(e=>!e.includes('503')),[]);
 assert.equal((await page.request.get(url+'api/snapshot?range=999')).status(),400);
 assert.equal((await page.request.get(url+'api/snapshot?range=900&device=../receiver')).status(),400);
 assert.equal((await page.request.get(url+'api/snapshot?range=900&device=unknown')).status(),400);
 assert.equal((await page.request.get(url+'server.py')).status(),404);
 assert.equal((await page.request.get(url+'receiver.json')).status(),404);
 console.log('PASS: live metrics, six charts, four ranges, pause/resume, keyboard chart inspection, mobile width, stale/disconnected states, API range/file restrictions.');
 console.log(screenshot);
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
