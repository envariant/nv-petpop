// Loading one release mesh for library mode (BRIEF Section 16, decision 118): its binary, info, pattern masks, own
// texture and texel map, with deltas and shell parts fetched on demand and cached.
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { buildTexelMap, parseBaseBin, type BaseData, type TexelMap } from './atlas';
import { decodeF16, type Composition, type MeshEntry, type MeshInfo, type ReleaseManifest } from './library';
import { atlasTexture, stampTexture, type AtlasTextures } from './PatternMaterial';
import { StampLayer, triangleSpheres } from './stamps';

export interface LoadedLibrary {
  manifest: ReleaseManifest;
  meshEntry: MeshEntry;
  mesh: MeshInfo;
  base: BaseData;
  tm: TexelMap;
  stamps: StampLayer;
  textures: AtlasTextures;
  url: (path: string) => string;
  delta: (path: string) => Promise<Float32Array>;
  shell: (path: string) => Promise<THREE.BufferGeometry>;
}

/** Load one release mesh (the first family's when none is named), its masks and texel map; deltas and shells
 *  load on demand and are cached. */
export async function loadLibrary(manifest: ReleaseManifest, url: (path: string) => string, meshId?: string): Promise<LoadedLibrary> {
  const id = meshId ?? manifest.families[0]?.mesh_id ?? manifest.meshes[0].id;
  const meshEntry = manifest.meshes.find((m) => m.id === id);
  if (!meshEntry) throw new Error(`the release has no mesh ${id}`);
  const [mesh, bin] = await Promise.all([
    fetch(url(meshEntry.info)).then((r) => r.json() as Promise<MeshInfo>),
    fetch(url(meshEntry.bin)).then((r) => r.arrayBuffer()),
  ]);
  const base = parseBaseBin(bin);
  const size = meshEntry.atlas.size;
  const loader = new THREE.TextureLoader();
  const masks = await Promise.all(meshEntry.atlas.mask_files.map((f) => loader.loadAsync(url(f)).then(atlasTexture)));
  const texture = meshEntry.texture ? await loader.loadAsync(url(meshEntry.texture)).then(atlasTexture) : null;
  const tm = buildTexelMap(base, size);
  const stamps = new StampLayer(base, tm, triangleSpheres(base));
  const deltaCache = new Map<string, Promise<Float32Array>>();
  const shellCache = new Map<string, Promise<THREE.BufferGeometry>>();
  const gltf = new GLTFLoader();
  return {
    manifest, meshEntry, mesh, base, tm, stamps, url,
    textures: { masks, stamps: stampTexture(size), texture, coat: meshEntry.coat_hex ?? null },
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
          const out = (geom ?? new THREE.BufferGeometry()) as THREE.BufferGeometry;
          if (out.getAttribute('position') && !out.getAttribute('normal')) out.computeVertexNormals(); // lit black without them
          return out;
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
