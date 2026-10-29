// Pattern layers in the shader (BRIEF Section 16): each layer's signed-distance mask is thresholded at its coverage
// on the GPU, so markings grow and shrink smoothly as a slider moves, with up to 10 layers at no extra CPU cost.
// The compositing maths is petpop_library/paint.py's composite(), in the same order and units (0..255): base
// colour, layers (mask < coverage * 250, 2-step soft edge), the 8-bit stamp layer "over", then nose and eye.
// bakeAtlas() renders that function unlit into an RGBA8 target, texel for texel, which is how gate 7 checks the
// screen against the export's albedo.
import * as THREE from 'three';

export const MAX_LAYERS = 10;
const MASK_TEXTURES = 3; // 12 channels: 10 patterns + eye + nose

export const COMPOSITE_GLSL = /* glsl */ `
uniform sampler2D uMask0;
uniform sampler2D uMask1;
uniform sampler2D uMask2;
uniform sampler2D uStamps;
uniform vec3 uBase;
uniform int uLayerCount;
uniform int uLayerChannel[${MAX_LAYERS}];
uniform float uLayerCoverage[${MAX_LAYERS}];
uniform vec3 uLayerColour[${MAX_LAYERS}];
uniform int uEyeChannel;
uniform int uNoseChannel;
uniform vec3 uEye;
uniform vec3 uNose;

// Atlas textures are uploaded with row 0 = image top; v = 1 is the top, so sample at (u, 1 - v).
vec3 ppComposite(vec2 uv) {
  vec2 st = vec2(uv.x, 1.0 - uv.y);
  vec4 m0 = texture2D(uMask0, st);
  vec4 m1 = texture2D(uMask1, st);
  vec4 m2 = texture2D(uMask2, st);
  float mv[12];
  mv[0] = m0.r; mv[1] = m0.g; mv[2] = m0.b; mv[3] = m0.a;
  mv[4] = m1.r; mv[5] = m1.g; mv[6] = m1.b; mv[7] = m1.a;
  mv[8] = m2.r; mv[9] = m2.g; mv[10] = m2.b; mv[11] = m2.a;
  vec3 c = uBase;
  for (int i = 0; i < ${MAX_LAYERS}; i++) {
    if (i >= uLayerCount) break;
    float m = 0.0;
    for (int k = 0; k < 12; k++) if (k == uLayerChannel[i]) m = mv[k];
    float a = clamp((uLayerCoverage[i] * 250.0 - m * 255.0) / 2.0 + 0.5, 0.0, 1.0);
    c += (uLayerColour[i] - c) * a;
  }
  vec4 s = texture2D(uStamps, st);
  c = c * (1.0 - s.a) + s.rgb * 255.0 * s.a;
  float nose = 0.0;
  float eye = 0.0;
  for (int k = 0; k < 12; k++) {
    if (k == uNoseChannel) nose = mv[k];
    if (k == uEyeChannel) eye = mv[k];
  }
  if (nose * 255.0 >= 127.5) c = uNose;
  if (eye * 255.0 >= 127.5) c = uEye;
  return c;
}
`;

export interface PatternState {
  base: string;
  layers: { channel: number; coverage: number; colour: string }[];
  eye: string;
  nose: string;
}

function rgb255(hex: string): THREE.Vector3 {
  const s = hex.replace('#', '');
  return new THREE.Vector3(parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16));
}

export interface AtlasTextures {
  masks: THREE.Texture[];
  stamps: THREE.DataTexture;
}

/** Atlas data textures: linear filtering, no mipmaps, no colour conversion (they are data, not colours). */
export function atlasTexture(t: THREE.Texture): THREE.Texture {
  t.flipY = false;
  t.colorSpace = THREE.NoColorSpace;
  t.magFilter = THREE.LinearFilter;
  t.minFilter = THREE.LinearFilter;
  t.generateMipmaps = false;
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  t.needsUpdate = true;
  return t;
}

export function stampTexture(size: number, data?: Uint8Array): THREE.DataTexture {
  const bytes = (data ?? new Uint8Array(size * size * 4)) as Uint8Array<ArrayBuffer>;
  const tex = new THREE.DataTexture(bytes, size, size, THREE.RGBAFormat, THREE.UnsignedByteType);
  atlasTexture(tex);
  return tex;
}

export function makeUniforms(tex: AtlasTextures, channels: Record<string, number>): Record<string, THREE.IUniform> {
  if (tex.masks.length < MASK_TEXTURES) throw new Error('a release needs three mask textures');
  return {
    uMask0: { value: tex.masks[0] },
    uMask1: { value: tex.masks[1] },
    uMask2: { value: tex.masks[2] },
    uStamps: { value: tex.stamps },
    uBase: { value: new THREE.Vector3(200, 160, 120) },
    uLayerCount: { value: 0 },
    uLayerChannel: { value: new Array(MAX_LAYERS).fill(0) },
    uLayerCoverage: { value: new Array(MAX_LAYERS).fill(0) },
    uLayerColour: { value: Array.from({ length: MAX_LAYERS }, () => new THREE.Vector3()) },
    uEyeChannel: { value: channels.eye },
    uNoseChannel: { value: channels.nose },
    uEye: { value: new THREE.Vector3() },
    uNose: { value: new THREE.Vector3() },
  };
}

/** Push the composition's colours and layers into the uniforms (no recompile, no texture work). */
export function setPattern(u: Record<string, THREE.IUniform>, p: PatternState): void {
  (u.uBase.value as THREE.Vector3).copy(rgb255(p.base));
  const n = Math.min(p.layers.length, MAX_LAYERS);
  u.uLayerCount.value = n;
  for (let i = 0; i < MAX_LAYERS; i++) {
    const l = p.layers[i];
    (u.uLayerChannel.value as number[])[i] = l ? l.channel : 0;
    (u.uLayerCoverage.value as number[])[i] = l ? l.coverage : 0;
    (u.uLayerColour.value as THREE.Vector3[])[i].copy(l ? rgb255(l.colour) : new THREE.Vector3());
  }
  (u.uEye.value as THREE.Vector3).copy(rgb255(p.eye));
  (u.uNose.value as THREE.Vector3).copy(rgb255(p.nose));
}

/** The lit preview: MeshStandardMaterial whose diffuse colour is the composited atlas (sRGB -> linear). */
export function patternMaterial(uniforms: Record<string, THREE.IUniform>): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0 });
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec2 vPpUv;')
      .replace('#include <uv_vertex>', '#include <uv_vertex>\nvPpUv = uv;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying vec2 vPpUv;\n${COMPOSITE_GLSL}`)
      .replace(
        '#include <map_fragment>',
        `vec3 ppC = ppComposite(vPpUv) / 255.0;
         diffuseColor.rgb = mix(pow((ppC + 0.055) / 1.055, vec3(2.4)), ppC / 12.92, vec3(lessThanEqual(ppC, vec3(0.04045))));`,
      );
  };
  mat.customProgramCacheKey = () => 'petpop-pattern-v1';
  return mat;
}

/** Render the composited atlas unlit into an RGBA8 target and read it back (row 0 = image top). */
export function bakeAtlas(renderer: THREE.WebGLRenderer, uniforms: Record<string, THREE.IUniform>, size: number): Uint8Array {
  const target = new THREE.WebGLRenderTarget(size, size, { type: THREE.UnsignedByteType, format: THREE.RGBAFormat, depthBuffer: false });
  target.texture.colorSpace = THREE.NoColorSpace;
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: 'void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }',
    fragmentShader: `uniform float uSize;\n${COMPOSITE_GLSL}\nvoid main() { vec2 uv = gl_FragCoord.xy / uSize; gl_FragColor = vec4(ppComposite(uv) / 255.0, 1.0); }`,
  });
  material.uniforms.uSize = { value: size };
  const scene = new THREE.Scene();
  scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material));
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const prevTarget = renderer.getRenderTarget();
  const prevColourSpace = renderer.outputColorSpace;
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.setRenderTarget(target);
  renderer.render(scene, camera);
  const raw = new Uint8Array(size * size * 4);
  renderer.readRenderTargetPixels(target, 0, 0, size, size, raw);
  renderer.setRenderTarget(prevTarget);
  renderer.outputColorSpace = prevColourSpace;
  target.dispose();
  material.dispose();
  // readPixels rows run bottom-up (row 0 = v near 0); flip to image order (row 0 = top).
  const out = new Uint8Array(raw.length);
  const row = size * 4;
  for (let y = 0; y < size; y++) out.set(raw.subarray((size - 1 - y) * row, (size - y) * row), y * row);
  return out;
}
