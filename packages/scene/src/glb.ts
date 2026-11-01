// GLB figures (the result viewer, the attract loop): Draco from our own origin, a textured/clay toggle.
import * as THREE from 'three';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { assetUrl } from '@petpop/core';

let loader: GLTFLoader | null = null;

function gltf(): GLTFLoader {
  if (!loader) {
    const draco = new DRACOLoader();
    draco.setDecoderPath(assetUrl('draco/'));
    loader = new GLTFLoader();
    loader.setDRACOLoader(draco);
  }
  return loader;
}

export async function loadGlb(url: string): Promise<THREE.Object3D> {
  return (await gltf().loadAsync(url)).scene;
}

const CLAY = new THREE.MeshStandardMaterial({ color: '#cfc6bb', roughness: 0.8, metalness: 0 });
const ORIGINAL = new WeakMap<THREE.Mesh, THREE.Material | THREE.Material[]>();

/** Swap every mesh to a neutral clay material, or back to its own. */
export function setClay(object: THREE.Object3D, clay: boolean): void {
  object.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    if (!ORIGINAL.has(mesh)) ORIGINAL.set(mesh, mesh.material);
    mesh.material = clay ? CLAY : ORIGINAL.get(mesh)!;
  });
}
