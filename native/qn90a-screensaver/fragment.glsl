precision mediump float;
varying vec3 ink;
varying float across;
uniform float gain;
void main() {
    float coverage = 1.0 - smoothstep(0.50, 1.0, abs(across));
    // Device-specific visibility adjustment; never changes the shared OLED shader.
    gl_FragColor = vec4(min(ink * 4.0, vec3(0.65)) * gain, coverage);
}
