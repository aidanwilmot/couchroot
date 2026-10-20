/* Layout review only: SVG scene output uses mock text metrics, not firmware Evas. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const out=path.join(root,'test-results/native-scenes');
 fs.mkdirSync(out,{recursive:true});
 execFileSync('sh',['native-hub/test.sh',out],{cwd:root,stdio:'inherit'});
 const browser=await chromium.launch();
 try {
  for(const width of [1920,960]) {
   const page=await browser.newPage({viewport:{width,height:width*9/16}});
   for(const file of fs.readdirSync(out).filter(f=>f.endsWith('.svg'))) {
    await page.setContent('<style>html,body{margin:0}svg{width:100vw;height:100vh}</style>'+fs.readFileSync(path.join(out,file),'utf8'));
    await page.screenshot({path:path.join(out,file.replace('.svg',`-${width}.png`))});
   }
   await page.close();
  }
 } finally {await browser.close();}
 console.log('Native layout review images: '+out);
})().catch(error=>{console.error(error);process.exitCode=1;});
