const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const path=require('node:path');
const url='file://'+path.resolve(__dirname,'../../qn90a-screensaver/web/index.html');
test('QN90A Asteroids: offline rendering, bounded C ticks, native exit and preserved black deadline',async()=>{
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage(), errors=[], remote=[];
    page.on('pageerror',e=>errors.push(String(e)));
    page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url());});
    await page.addInitScript(()=>{
      window.exitCount=0; window.tizen={application:{getCurrentApplication:()=>({exit:()=>exitCount++})}};
      window.timeOffset=0; const now=performance.now.bind(performance);
      performance.now=()=>now()+window.timeOffset;
      // Read actual framebuffer output in the draw callback, before discard.
      const draw=WebGLRenderingContext.prototype.drawArrays;
      WebGLRenderingContext.prototype.drawArrays=function(...args){
        draw.apply(this,args);
        if (!window.pixelEvidence && window.timeOffset===10000 && window.saverState && saverState.frames>5) {
          const pixels=new Uint8Array(1920*1080*4);
          this.readPixels(0,0,1920,1080,this.RGBA,this.UNSIGNED_BYTE,pixels);
          let peak=0,visible=0,opaque=true,warm=true;
          for(let i=0;i<pixels.length;i+=4){
            peak=Math.max(peak,pixels[i]);
            if(pixels[i]>80)visible++;
            opaque=opaque&&pixels[i+3]===255;
            warm=warm&&pixels[i]>=pixels[i+1]&&pixels[i+1]>=pixels[i+2];
          }
          window.pixelEvidence={peak,visible,opaque,warm};
        }
      };
    });
    await page.goto(url); await page.waitForFunction(()=>saverState.frames>5);
    await page.evaluate(()=>{window.timeOffset=10000;});
    await page.waitForFunction(()=>window.pixelEvidence);
    const pixels=await page.evaluate(()=>pixelEvidence);
    assert.ok(pixels.peak>100&&pixels.peak<=166,JSON.stringify(pixels));
    assert.ok(pixels.visible>100&&pixels.visible<1920*1080*.10,JSON.stringify(pixels));
    assert.ok(pixels.opaque&&pixels.warm);
    const result=await page.evaluate(async()=>{
      const m=await AsteroidsCore(); m._saver_init(123,100);
      const initial=m._saver_frame(100,1920,1080);
      const cached=m._saver_frame(100,1920,1080);
      m._saver_frame(500,1920,1080); const bounded=m._saver_steps();
      const black=m._saver_frame(700,1920,1080);
      const light=m._saver_light(700);
      return {initial,cached,bounded,black,light};
    });
    assert.ok(result.initial>0&&result.initial<=16384);
    assert.equal(result.cached,-1); assert.ok(result.bounded<=6);
    assert.equal(result.black,-2); assert.equal(result.light,0);
    // A restored GL context must not create a fresh ten-minute bright period.
    await page.evaluate(()=>{window.timeOffset=599000;window.loss=document.querySelector('canvas').getContext('webgl').getExtension('WEBGL_lose_context');loss.loseContext();});
    await page.waitForFunction(()=>!saverState.ready);
    await page.evaluate(()=>{window.timeOffset=601000;loss.restoreContext();});
    await page.waitForFunction(()=>saverState.black);
    const frames=await page.evaluate(()=>saverState.frames);
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(()=>saverState.frames),frames);
    await page.keyboard.press('ArrowRight');assert.equal(await page.evaluate(()=>exitCount),1);
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    // A hidden saver stops and exits through the normal app API.
    await page.goto(url);await page.waitForFunction(()=>saverState.frames>2);
    await page.evaluate(()=>{Object.defineProperty(document,'hidden',{value:true});document.dispatchEvent(new Event('visibilitychange'));});
    assert.equal(await page.evaluate(()=>exitCount),1);
    // A synchronous WASM/bootstrap failure must exit, not leave a blank app.
    await page.route('**/core.js',route=>route.fulfill({contentType:'text/javascript',body:'window.AsteroidsCore=function(){throw new Error("compile denied")};'}));
    await page.goto(url);await page.waitForFunction(()=>saverState.error);
    assert.match(await page.evaluate(()=>saverState.error),/compile denied/);
    assert.equal(await page.evaluate(()=>exitCount),1);
    await page.route('**/core.js',route=>route.fulfill({contentType:'text/javascript',body:'window.AsteroidsCore=function(){return Promise.reject(new Error("async compile denied"))};'}));
    await page.goto(url);await page.waitForFunction(()=>saverState.error);
    assert.match(await page.evaluate(()=>saverState.error),/async compile denied/);
    assert.equal(await page.evaluate(()=>exitCount),1);
  }finally{await browser.close();}
});
