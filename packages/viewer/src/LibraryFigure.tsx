// The kiosk's Design preview (BRIEF Section 16): the release's base mesh with the family and region deltas applied
// as vertex offsets, shell parts on their sockets, pattern layers in the shader and stamps in an atlas texture.
// It is the final asset, not a proxy: the export composes the same deltas and paints the same atlas.
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ThreeEvent } from '@react-three/fiber';
import { useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { buildTexelMap, parseBaseBin, type BaseData, type TexelMap } from './atlas';
import { Fit, Spin, Stage } from './Figure3D';
import {
  buildGeometry, composeCoords, decodeF16, hitToBase, socketFrames, updateGeometry, type Composition, type MeshInfo, type ReleaseManifest,
  type SplitGeometry,
} from './library';
import { atlasTexture, bakeAtlas, makeUniforms, patternMaterial, setPattern, stampTexture, type AtlasTextures } from './PatternMaterial';
import { StampLayer, triangleSpheres } from './stamps';

export interface LoadedLibrary {
  manifest: ReleaseManifest;
  mesh: MeshInfo;
  base: BaseData;
  tm: TexelMap;
  stamps: StampLayer;
  textures: AtlasTextures;
  url: (path: string) => string;
  delta: (path: string) => Promise<Float32Array>;
  shell: (path: string) => Promise<THREE.BufferGeometry>;
}

/** Load a release's base mesh, masks and texel map; deltas and shells load on demand and are cached. */
export async function loadLibrary(manifest: ReleaseManifest, url: (path: string) => string): Promise<LoadedLibrary> {
  const [mesh, bin] = await Promise.all([
    fetch(url(manifest.mesh)).then((r) => r.json() as Promise<MeshInfo>),
    fetch(url('base.bin')).then((r) => r.arrayBuffer()),
  ]);
  const base = parseBaseBin(bin);
  const size = manifest.atlas.size;
  const loader = new THREE.TextureLoader();
  const masks = await Promise.all(manifest.atlas.mask_files.map((f) => loader.loadAsync(url(f)).then(atlasTexture)));
  const tm = buildTexelMap(base, size);
  const stamps = new StampLayer(base, tm, triangleSpheres(base));
  const deltaCache = new Map<string, Promise<Float32Array>>();
  const shellCache = new Map<string, Promise<THREE.BufferGeometry>>();
  const gltf = new GLTFLoader();
  return {
    manifest, mesh, base, tm, stamps, url,
    textures: { masks, stamps: stampTexture(size) },
    delta: (path) => {
      if (!deltaCache.has(path)) deltaCache.set(path, fetch(url(path)).then((r) => r.arrayBuffer()).then(decodeF16));
      return deltaCache.get(path)!;
    },
    shell: (path) => {
      if (!shellCache.has(path)) {
        shellCache.set(path, gltf.loadAsync(url(path)).then((g) => {
          let geom: THREE.BufferGeometry | null = null;
          g.scene.traverse((o) => {
            const m = o as THREE.Mesh;
            if (m.isMesh && !geom) geom = m.geometry;
          });
          return geom ?? new THREE.BufferGeometry();
        }));
      }
      return shellCache.get(path)!;
    },
  };
}

/** Re-rasterise every stamp (after undo or a reset) and upload the stamp texture. */
export function syncStamps(lib: LoadedLibrary, stamps: Composition['stamps']): void {
  lib.stamps.clear();
  for (const s of stamps) lib.stamps.add(s);
  uploadStamps(lib);
}

export function uploadStamps(lib: LoadedLibrary): void {
  const tex = lib.textures.stamps;
  lib.stamps.toRGBA(tex.image.data as Uint8Array, true);
  tex.needsUpdate = true;
}

export interface PaintHit {
  p: [number, number, number];
  dragging: boolean;
}

function Composed({ lib, composition, onPaint, onBake }: { lib: LoadedLibrary; composition: Composition; onPaint?: (h: PaintHit) => void; onBake?: (bake: () => Uint8Array) => void }) {
  const gl = useThree((s) => s.gl);
  const split = useMemo<SplitGeometry>(() => buildGeometry(lib.base), [lib]);
  const uniforms = useMemo(() => makeUniforms(lib.textures, lib.manifest.atlas.channels), [lib]);
  const material = useMemo(() => patternMaterial(uniforms), [uniforms]);
  const group = useMemo(() => new THREE.Group(), []); // fitted by <Fit> in its own (Y up) frame
  const zUp = useMemo(() => {
    const g = new THREE.Group();
    g.rotation.x = -Math.PI / 2; // base mesh is Z up, three.js is Y up
    return g;
  }, []);
  const body = useMemo(() => new THREE.Mesh(split.geometry, material), [split, material]);
  const [co, setCo] = useState<Float64Array | null>(null);
  const [shells, setShells] = useState<THREE.Mesh[]>([]);
  const painting = useRef(false);

  useEffect(() => {
    group.add(zUp);
    zUp.add(body);
    return () => {
      zUp.remove(body);
      group.remove(zUp);
    };
  }, [group, zUp, body]);

  // Geometry: family + region deltas (loaded on demand), recomposed on every part swap.
  const deltaKey = JSON.stringify([composition.family_id, composition.parts]);
  useEffect(() => {
    let live = true;
    const m = lib.manifest;
    const fam = m.families.find((f) => f.id === composition.family_id);
    const parts = Object.values(composition.parts)
      .map((id) => m.region_deltas.find((d) => d.id === id))
      .filter((d): d is NonNullable<typeof d> => !!d);
    Promise.all([fam ? lib.delta(fam.delta) : Promise.resolve(null), ...parts.map((p) => lib.delta(p.delta))]).then((ds) => {
      if (!live) return;
      const c = composeCoords(lib.base, ds);
      updateGeometry(lib.base, split, c);
      setCo(c);
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lib, split, deltaKey]);

  // Shells on their sockets.
  const shellKey = JSON.stringify(composition.shells);
  useEffect(() => {
    if (!co) return;
    let live = true;
    const frames = socketFrames(co, lib.mesh.landmarks, lib.base.shell);
    Promise.all(
      composition.shells.map(async (s) => {
        const item = lib.manifest.shell_parts.find((p) => p.id === s.part_id);
        if (!item) return null;
        const geom = await lib.shell(item.mesh);
        const mesh = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ color: s.colour, roughness: 0.5, metalness: 0 }));
        const f = frames[item.kind];
        if (f) {
          mesh.position.set(...f.loc);
          mesh.scale.setScalar(f.scale);
        }
        return mesh;
      }),
    ).then((ms) => {
      if (live) setShells(ms.filter(Boolean) as THREE.Mesh[]);
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lib, co, shellKey]);
  useEffect(() => {
    shells.forEach((s) => zUp.add(s));
    return () => shells.forEach((s) => zUp.remove(s));
  }, [zUp, shells]);

  // Colours and layers: uniforms only, so a coverage slider costs nothing but a redraw.
  const channels = lib.manifest.pattern_layers;
  useEffect(() => {
    setPattern(uniforms, {
      base: composition.base_colour,
      eye: composition.eye_colour,
      nose: composition.nose_colour,
      layers: composition.layers.map((l) => ({ channel: channels.find((p) => p.id === l.pattern_id)?.channel ?? 0, coverage: l.coverage, colour: l.colour })),
    });
  }, [uniforms, composition.base_colour, composition.eye_colour, composition.nose_colour, composition.layers, channels]);

  useEffect(() => {
    onBake?.(() => bakeAtlas(gl, uniforms, lib.manifest.atlas.size));
  }, [gl, uniforms, lib, onBake]);

  const hit = (e: ThreeEvent<PointerEvent>, dragging: boolean) => {
    if (!onPaint || !co || e.faceIndex == null) return;
    e.stopPropagation();
    const local = body.worldToLocal(e.point.clone());
    onPaint({ p: hitToBase(lib.base, co, e.faceIndex, local), dragging });
  };
  return (
    <group
      onPointerDown={(e) => {
        painting.current = true;
        hit(e, false);
      }}
      onPointerMove={(e) => painting.current && hit(e, true)}
      onPointerUp={() => (painting.current = false)}
      onPointerLeave={() => (painting.current = false)}
    >
      {co && <Fit object={group} />}
    </group>
  );
}

export function LibraryFigure({ lib, composition, onPaint, spin = false, interactive = true, onBake, testId = 'design-preview' }: {
  lib: LoadedLibrary;
  composition: Composition;
  onPaint?: (h: PaintHit) => void;
  spin?: boolean;
  interactive?: boolean;
  onBake?: (bake: () => Uint8Array) => void;
  testId?: string;
}) {
  return (
    <Stage interactive={interactive && !onPaint} testId={testId}>
      <Spin enabled={spin} speed={0.25}>
        <Composed lib={lib} composition={composition} onPaint={onPaint} onBake={onBake} />
      </Spin>
    </Stage>
  );
}
