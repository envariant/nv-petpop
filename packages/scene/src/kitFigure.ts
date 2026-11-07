// A figure of part kits on screen (decision 136): every part's GLB, placed by the kit (kitPlan), each painted from its
// texture template's masks (paintTile) as the print is, stood on the floor. Geometry, masks and painted textures are
// cached, so changing a colour repaints and changing a shape re-places, without reloading.
import * as THREE from 'three';
import { loadGlb } from './glb';
import { kitPlan, maskLayers, paintTile, type Kit, type KitComposition, type KitManifest } from './kit';

const TILE = 256;

export class KitFigure {
  /** Hand to FigureStage.setObject; it stays at identity (the stage frames an object in its own frame), so the parts
   *  live in `inner`, which stands them on the floor. */
  readonly root = new THREE.Group();
  private readonly inner = new THREE.Group();
  private geometry = new Map<string, Promise<THREE.BufferGeometry | null>>();
  private masks = new Map<string, Promise<Uint8Array | null>>();
  private textures = new Map<string, THREE.Texture>();
  private lastPlan = '';

  constructor(private manifest: KitManifest, private kit: Kit, private url: (path: string) => string, private tile = TILE) {
    this.root.add(this.inner);
  }

  private geom(file: string): Promise<THREE.BufferGeometry | null> {
    if (!this.geometry.has(file)) {
      this.geometry.set(file, loadGlb(this.url(file)).then((obj) => {
        let g: THREE.BufferGeometry | null = null;
        obj.updateMatrixWorld(true);
        obj.traverse((o) => {
          const m = o as THREE.Mesh;
          if (!g && m.isMesh) g = (m.geometry as THREE.BufferGeometry).clone().applyMatrix4(m.matrixWorld);
        });
        if (g) (g as THREE.BufferGeometry).computeVertexNormals();
        return g;
      }).catch(() => null));
    }
    return this.geometry.get(file)!;
  }

  /** A mask resized to the tile, one byte per pixel (its red channel), or null when the template has none. */
  private mask(layout: string, name: string): Promise<Uint8Array | null> {
    const key = `${layout}/${name}`;
    if (!this.masks.has(key)) {
      const entry = this.manifest.masks?.find((x) => x.uv_layout === layout && x.name === name);
      this.masks.set(key, !entry ? Promise.resolve(null) : new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
          const c = document.createElement('canvas');
          c.width = c.height = this.tile;
          const ctx = c.getContext('2d', { willReadFrequently: true })!;
          ctx.imageSmoothingQuality = 'high';
          ctx.drawImage(img, 0, 0, this.tile, this.tile);
          const px = ctx.getImageData(0, 0, this.tile, this.tile).data;
          const out = new Uint8Array(this.tile * this.tile);
          for (let i = 0; i < out.length; i++) out[i] = px[i * 4];
          resolve(out);
        };
        img.onerror = () => resolve(null);
        img.src = this.url(entry.file);
      }));
    }
    return this.masks.get(key)!;
  }

  private async texture(layout: string | undefined, c: KitComposition): Promise<THREE.Texture> {
    const key = JSON.stringify([layout, c.texture, c.eye_colour, c.nose_colour]);
    const have = this.textures.get(key);
    if (have) return have;
    const masks = new Map<string, Uint8Array>();
    if (layout) {
      for (const [name] of maskLayers(c.texture, c.eye_colour, c.nose_colour)) {
        const m = await this.mask(layout, name);
        if (m) masks.set(name, m);
      }
    }
    const data = paintTile(this.tile, c.texture, masks, c.eye_colour, c.nose_colour);
    const tex = new THREE.DataTexture(data, this.tile, this.tile, THREE.RGBAFormat);
    tex.flipY = false; // glTF UVs: v = 0 is the image's top row, which is the data's first row
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.magFilter = THREE.LinearFilter;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.generateMipmaps = true;
    tex.needsUpdate = true;
    if (this.textures.size > 64) this.clearTextures();
    this.textures.set(key, tex);
    return tex;
  }

  private clearTextures() {
    this.textures.forEach((t) => t.dispose());
    this.textures.clear();
  }

  /** Build the figure for a composition. True when the parts moved (the caller may refit the camera). */
  async update(c: KitComposition): Promise<boolean> {
    const plan = kitPlan(this.kit, c);
    const shape = JSON.stringify(plan.map((p) => [p.part.mesh.file, p.matrix.elements]));
    const meshes = await Promise.all(plan.map(async (p) => {
      const g = await this.geom(p.part.mesh.file);
      if (!g) return null;
      const map = g.getAttribute('uv') ? await this.texture(p.part.uv_layout, c) : null;
      const mat = new THREE.MeshStandardMaterial({ map, color: map ? '#ffffff' : c.texture.base.hex, roughness: 0.75, metalness: 0 });
      const mesh = new THREE.Mesh(g, mat);
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(p.matrix);
      mesh.name = p.slot;
      return mesh;
    }));
    this.inner.children.forEach((o) => ((o as THREE.Mesh).material as THREE.Material)?.dispose?.());
    this.inner.clear();
    for (const m of meshes) if (m) this.inner.add(m);
    // stood on the floor, centred: measured in the parts' own frame (setFromObject would count the stage's offset)
    const box = new THREE.Box3();
    for (const m of meshes) {
      if (!m) continue;
      if (!m.geometry.boundingBox) m.geometry.computeBoundingBox();
      box.union(m.geometry.boundingBox!.clone().applyMatrix4(m.matrix));
    }
    if (!box.isEmpty()) this.inner.position.set(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
    const moved = shape !== this.lastPlan;
    this.lastPlan = shape;
    return moved;
  }

  dispose() {
    this.inner.children.forEach((o) => ((o as THREE.Mesh).material as THREE.Material)?.dispose?.());
    this.clearTextures();
    this.geometry.forEach((p) => void p.then((g) => g?.dispose()));
  }
}
