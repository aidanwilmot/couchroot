// Compile/run the actual bounded C simulation; render its real batches and GLSL.
const {chromium}=require('playwright');
const fs=require('node:fs'),{execFileSync}=require('node:child_process'),assert=require('node:assert/strict');
(async()=>{
  fs.mkdirSync(__dirname+'/bin',{recursive:true});
  execFileSync('cc',['-std=c99','-O2','-Wall','-Wextra','-Werror',__dirname+'/sample-animation.c','-lm','-o',__dirname+'/bin/sample-animation']);
  const simulation=JSON.parse(execFileSync(__dirname+'/bin/sample-animation',[__dirname+'/bin/frames.bin'],{encoding:'utf8'}));
  const source=fs.readFileSync(__dirname+'/renderer.c','utf8');
  const shader=name=>[...source.match(new RegExp(`static const char \\*${name} =([\\s\\S]*?);\\n`))[1].matchAll(/"(?:[^"\\]|\\.)*"/g)].map(m=>JSON.parse(m[0])).join('');
  const frames=fs.readFileSync(__dirname+'/bin/frames.bin');
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1280,height:720}});
    await page.setContent('<style>body{margin:0;background:black}canvas{width:1280px;height:720px}</style><canvas width="960" height="540"></canvas>');
    const result=await page.evaluate(({vs,fs,base64})=>{
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0)),dv=new DataView(bytes.buffer);
      const frames=[];let offset=0;
      while(offset<bytes.length){const time=dv.getUint32(offset,true),count=dv.getUint32(offset+4,true),gain=dv.getFloat32(offset+8,true);offset+=12;const vertices=new Float32Array(bytes.buffer.slice(offset,offset+count*24));offset+=count*24;frames.push({time,count,gain,vertices});}
      const gl=document.querySelector('canvas').getContext('webgl',{preserveDrawingBuffer:true,alpha:true,antialias:false});
      if(!gl)throw Error('WebGL unavailable');
      const compile=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
      const p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,vs));gl.attachShader(p,compile(gl.FRAGMENT_SHADER,fs));['position','color','edge'].forEach((n,i)=>gl.bindAttribLocation(p,i,n));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));gl.useProgram(p);
      const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      [2,3,1].forEach((n,i)=>{gl.enableVertexAttribArray(i);gl.vertexAttribPointer(i,n,gl.FLOAT,false,24,[0,8,20][i]);});
      gl.uniform1f(gl.getUniformLocation(p,'aspect'),16/9);const gain=gl.getUniformLocation(p,'gain');
      gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
      const pixels=new Uint8Array(960*540*4),dwell=new Uint16Array(960*540);
      function draw(frame){gl.clearColor(0,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);gl.uniform1f(gain,frame.gain);gl.bufferData(gl.ARRAY_BUFFER,frame.vertices,gl.STREAM_DRAW);gl.drawArrays(gl.TRIANGLES,0,frame.count);gl.readPixels(0,0,960,540,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}
      let max=0,litFraction=0,blackFailures=0,paletteFailures=0,alphaFailures=0,maxSampleDwell=0,preview=null,previewScore=0;
      for(const frame of frames){if(frame.time===0)dwell.fill(0);draw(frame);let lit=0;
        for(let i=0,j=0;i<pixels.length;i+=4,j++){
          const r=pixels[i],g=pixels[i+1],b=pixels[i+2];max=Math.max(max,r,g,b);
          if(r+g+b>0){lit++;dwell[j]+=10;maxSampleDwell=Math.max(maxSampleDwell,dwell[j]);}else dwell[j]=0;
          if(frame.time>=600&&r+g+b>0)blackFailures++;
          if(r<g||g<b)paletteFailures++;
          if(pixels[i+3]!==255)alphaFailures++;
        }
        litFraction=Math.max(litFraction,lit/(960*540));
        if(frame.time>10&&frame.time<120&&frame.count>previewScore){preview=frame;previewScore=frame.count;}
      }
      // Repeated overlap must stay within the digital ink cap, with opaque black underneath.
      draw(preview);for(let k=0;k<30;k++)gl.drawArrays(gl.TRIANGLES,0,preview.count);
      gl.readPixels(0,0,960,540,gl.RGBA,gl.UNSIGNED_BYTE,pixels);let overlapMax=0;for(let i=0;i<pixels.length;i+=4)overlapMax=Math.max(overlapMax,pixels[i],pixels[i+1],pixels[i+2]);
      draw(preview);
      return{max,overlapMax,litFraction,maxSampleDwell,blackFailures,paletteFailures,alphaFailures,previewTime:preview.time,frames:frames.length,error:gl.getError()};
    },{vs:shader('vertex_shader'),fs:shader('fragment_shader'),base64:frames.toString('base64')});
    console.log(JSON.stringify({simulation,render:result}));
    assert.equal(result.error,0);assert.ok(result.max>25&&result.max<=46);assert.ok(result.overlapMax<=46);
    assert.ok(result.litFraction<0.025);assert.ok(result.maxSampleDwell<60);
    assert.equal(result.blackFailures,0);assert.equal(result.paletteFailures,0);assert.equal(result.alphaFailures,0);
    await page.screenshot({path:__dirname+'/bin/preview.png'});
    fs.writeFileSync(__dirname+'/bin/verification.json',JSON.stringify({simulation,render:result},null,2)+'\n');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
