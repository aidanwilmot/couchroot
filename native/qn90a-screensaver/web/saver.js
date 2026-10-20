/* Samsung owns system idle and wake; this app only renders the shared scene. */
(function () {
  'use strict';
  var canvas = document.getElementById('scene'), gl, core, program, buffer, gain;
  var frameId = 0, started = performance.now() / 1000, stopped = false, count = 0, uploadView;
  window.saverState = {ready:false, black:false, frames:0, error:null};
  function exit() {
    stopped = true; cancelAnimationFrame(frameId);
    try { if (window.tizen) { tizen.application.getCurrentApplication().exit(); } } catch (_) { /* Native wake also terminates the screensaver. */ }
  }
  document.addEventListener('keydown', function () { exit(); }, true);
  document.addEventListener('tizenhwkey', function () { exit(); }, true);
  document.addEventListener('visibilitychange', function () { if (document.hidden) { exit(); } });
  canvas.addEventListener('webglcontextlost', function (event) {
    event.preventDefault(); cancelAnimationFrame(frameId); window.saverState.ready = false;
  });
  canvas.addEventListener('webglcontextrestored', function () {
    if (!stopped) { try { setup(); frameId = requestAnimationFrame(frame); } catch (e) { fail(e); } }
  });
  function fail(error) { window.saverState.error = String(error); exit(); }
  function compile(type, source) {
    var shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) { throw new Error(gl.getShaderInfoLog(shader)); }
    return shader;
  }
  function setup() {
    gl = canvas.getContext('webgl', {alpha:false, antialias:false, depth:false, stencil:false, preserveDrawingBuffer:false});
    if (!gl) { throw new Error('WebGL unavailable'); }
    canvas.width = 1920; canvas.height = 1080; gl.viewport(0, 0, canvas.width, canvas.height);
    var vertex = compile(gl.VERTEX_SHADER, SaverShaders.vertex), fragment = compile(gl.FRAGMENT_SHADER, SaverShaders.fragment);
    program = gl.createProgram(); gl.attachShader(program, vertex); gl.attachShader(program, fragment);
    ['position', 'color', 'edge'].forEach(function (name, i) { gl.bindAttribLocation(program, i, name); });
    gl.linkProgram(program); gl.deleteShader(vertex); gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { throw new Error(gl.getProgramInfoLog(program)); }
    gl.useProgram(program); gl.uniform1f(gl.getUniformLocation(program, 'aspect'), 16 / 9); gain = gl.getUniformLocation(program, 'gain');
    buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, 16384 * 24, gl.DYNAMIC_DRAW);
    [2, 3, 1].forEach(function (size, i) { gl.enableVertexAttribArray(i); gl.vertexAttribPointer(i, size, gl.FLOAT, false, 24, [0, 8, 20][i]); });
    gl.enable(gl.BLEND); gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    // Restore the current batch after context loss without restarting the deadline.
    if (count) { gl.bufferSubData(gl.ARRAY_BUFFER, 0, uploadView); }
    window.saverState.ready = true;
  }
  function frame() {
    if (stopped) { return; }
    var now = performance.now() / 1000, result = core._saver_frame(now, canvas.width, canvas.height);
    if (result === -2) {
      gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT); window.saverState.black = true; return;
    }
    if (result >= 0) {
      if (count !== result || !uploadView) { count = result; uploadView = new Float32Array(core.HEAPF32.buffer, core._saver_vertices(), count * 6); }
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, uploadView);
      gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(gain, core._saver_light(now)); gl.drawArrays(gl.TRIANGLES, 0, count); window.saverState.frames++;
    }
    frameId = requestAnimationFrame(frame);
  }
  Promise.resolve().then(function () { return AsteroidsCore(); }).then(function (module) {
    if (stopped) { return; }
    core = module; core._saver_init((Date.now() >>> 0) || 1, started);
    setup(); frameId = requestAnimationFrame(frame);
  }).catch(fail);
}());
