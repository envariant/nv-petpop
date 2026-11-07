// A figure of part kits on screen (decisions 136, 139): every part's GLB, placed by the kit (kitPlan), painted as the
// print is (kitPaint.ts: its texture template's masks, then its slot's stamps), extras on the figure's sockets, stood
// on the floor. Geometry, masks and painted tiles are cached, so a colour or a spot repaints one tile and a shape
// change re-places, without reloading. A slot shares its part's tile unless it has stamps of its own.
import * as THREE from 'three';
import type { BaseData } from './atlas';
import { loadGlb } from './glb';
import { kitPlan, maskLayers, type Kit, type KitComposition, type KitManifest, type PlacedPart } from './kit';
import { LANDMARK_SLOTS, kitLandmarks, paintKitTile, partBase, type KitSlot, type MaskImage } from './kitPaint';
import { socketFrames } from './library';

const TILE = 256;

interface PartGeometry { geometry: THREE.BufferGeometry; base: BaseData }
export interface KitHit { slot: KitSlot; p: [number, number, number] }

const round3 = (x: number) => Math.round(x * 1000) / 1000;

export class KitFigure {
  /** Hand to FigureStage.setObject; it stays at identity (the stage frames an object in its own frame), so the parts
   *  live in `inner`, which stands them on the floor. */
  readonly root = new THREE.Group();
  private readonly inner = new THREE.Group();
  private readonly extras = new THREE.Group(); // Z-up, as the extras' sockets are
  private geometry = new Map<string, Promise<PartGeometry | null>>();
  private masks = new Map<string, Promise<MaskImage | null>>();
  private textures = new Map<string, THREE.Texture>();
  private shellGeometry = new Map<string, Promise<THREE.BufferGeometry | null>>();
  private parts: THREE.Mesh[] = [];
  private lastPlan = '';
  private shellKey = '';
  private seq = 0;

  constructor(private manifest: KitManifest, private kit: Kit, private url: (path: string) => string, private tile = TILE) {
    this.extras.rotation.x = -Math.PI / 2;
    this.inner.add(this.extras);
    this.root.add(this.inner);
  }

  /** Every mesh of a part's GLB, joined, in its own frame (kit_figure.read_part), with what the stamp rasteriser reads. */
  private geom(file: string): Promise<PartGeometry | null> {
    if (!this.geometry.has(file)) {
      this.geometry.set(file, loadGlb(this.url(file)).then((obj) => {
        const gs: THREE.BufferGeometry[] = [];
        obj.updateMatrixWorld(true);
        obj.traverse((o) => {
          const m = o as THREE.Mesh;
          if (m.isMesh) gs.push((m.geometry as THREE.BufferGeometry).clone().applyMatrix4(m.matrixWorld));
        });
        if (!gs.length) return null;
        const base = partBase(gs);
        const g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.BufferAttribute(base.co, 3));
        const uv = new Float32Array(base.n * 2).fill(0.5);
        let off = 0;
        for (const x of gs) {
          const t = x.getAttribute('uv');
          if (t) for (let i = 0; i < t.count; i++) uv.set([t.getX(i), t.getY(i)], (off + i) * 2);
          off += x.getAttribute('position').count;
        }
        g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
        g.setIndex(new THREE.BufferAttribute(base.tri, 1));
        g.computeVertexNormals();
        g.computeBoundingBox();
        return { geometry: g, base };
      }).catch(() => null));
    }
    return this.geometry.get(file)!;
  }

  /** A mask at its own size, one byte per pixel (its red channel), or null when the template has none. */
  private mask(layout: string, name: string): Promise<MaskImage | null> {
    const key = `${layout}/${name}`;
    if (!this.masks.has(key)) {
      const entry = this.manifest.masks?.find((x) => x.uv_layout === layout && x.name === name);
      this.masks.set(key, !entry ? Promise.resolve(null) : new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
          const w = img.naturalWidth, h = img.naturalHeight;
          const c = document.createElement('canvas');
          c.width = w;
          c.height = h;
          const ctx = c.getContext('2d', { willReadFrequently: true })!;
          ctx.drawImage(img, 0, 0);
          const px = ctx.getImageData(0, 0, w, h).data;
          const data = new Uint8Array(w * h);
          for (let i = 0; i < data.length; i++) data[i] = px[i * 4];
          resolve({ data, w, h });
        };
        img.onerror = () => resolve(null);
        img.src = this.url(entry.file);
      }));
    }
    return this.masks.get(key)!;
  }

  private stampsOf(c: KitComposition, slot: string) {
    return (c.stamps ?? []).filter((s) => s.slot === slot).map(({ p, r, colour }) => ({ p, r, colour }));
  }

  /** A slot's tile, size x size RGBA, and its key: the part's file, or file#slot when the slot has stamps of its own. */
  async tileFor(p: PlacedPart, c: KitComposition, size = this.tile): Promise<{ key: string; rgba: Uint8Array<ArrayBuffer> }> {
    const stamps = this.stampsOf(c, p.slot);
    const key = stamps.length ? `${p.part.mesh.file}#${p.slot}` : p.part.mesh.file;
    const masks = new Map<string, MaskImage>();
    if (p.part.uv_layout) {
      for (const [name] of maskLayers(c.texture, c.eye_colour, c.nose_colour)) {
        const m = await this.mask(p.part.uv_layout, name);
        if (m) masks.set(name, m);
      }
    }
    const part = stamps.length ? (await this.geom(p.part.mesh.file))?.base : null;
    return { key, rgba: paintKitTile(size, c.texture, masks, c.eye_colour, c.nose_colour, part, stamps) };
  }

  private async texture(p: PlacedPart, c: KitComposition): Promise<THREE.Texture> {
    const stamps = this.stampsOf(c, p.slot);
    const key = JSON.stringify([p.part.uv_layout, c.texture, c.eye_colour, c.nose_colour, stamps.length ? [p.part.mesh.file, stamps] : null]);
    const have = this.textures.get(key);
    if (have) return have;
    const { rgba } = await this.tileFor(p, c);
    const tex = new THREE.DataTexture(rgba, this.tile, this.tile, THREE.RGBAFormat);
    tex.flipY = false; // glTF UVs: v = 0 is the image's top row, which is the data's first row
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.magFilter = THREE.LinearFilter;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.generateMipmaps = true;
    tex.needsUpdate = true;
    if (this.textures.size > 96) this.clearTextures();
    this.textures.set(key, tex);
    return tex;
  }

  private clearTextures() {
    this.textures.forEach((t) => t.dispose());
    this.textures.clear();
  }

  private shell(path: string): Promise<THREE.BufferGeometry | null> {
    if (!this.shellGeometry.has(path)) {
      this.shellGeometry.set(path, loadGlb(this.url(path)).then((obj) => {
        let g: THREE.BufferGeometry | null = null;
        obj.traverse((o) => {
          const m = o as THREE.Mesh;
          if (m.isMesh && !g) g = m.geometry as THREE.BufferGeometry;
        });
        const geom = g as THREE.BufferGeometry | null;
        if (geom && !geom.getAttribute('normal')) geom.computeVertexNormals(); // the extras' GLBs carry none: lit black otherwise
        return geom;
      }).catch(() => null));
    }
    return this.shellGeometry.get(path)!;
  }

  /** Build the figure for a composition. True when the parts moved (the caller may refit the camera). */
  async update(c: KitComposition): Promise<boolean> {
    const seq = ++this.seq;
    const plan = kitPlan(this.kit, c);
    const shape = JSON.stringify(plan.map((p) => [p.part.mesh.file, p.matrix.elements]));
    const built = await Promise.all(plan.map(async (p) => {
      const g = await this.geom(p.part.mesh.file);
      if (!g) return null;
      const map = await this.texture(p, c);
      return { p, g, map };
    }));
    const shells = c.shells ?? [];
    const shellGeoms = await Promise.all(shells.map(async (s) => {
      const item = this.manifest.shell_parts?.find((x) => x.id === s.part_id);
      return item ? { s, item, g: await this.shell(item.mesh) } : null;
    }));
    if (seq !== this.seq) return false; // a newer update won
    this.parts.forEach((m) => {
      (m.material as THREE.Material).dispose();
      this.inner.remove(m);
    });
    this.parts = [];
    for (const b of built) {
      if (!b) continue;
      const mat = new THREE.MeshStandardMaterial({ map: b.map, color: '#ffffff', roughness: 0.75, metalness: 0 });
      const mesh = new THREE.Mesh(b.g.geometry, mat);
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(b.p.matrix);
      mesh.name = b.p.slot;
      this.inner.add(mesh);
      this.parts.push(mesh);
    }
    // stood on the floor, centred: measured in the parts' own frame (setFromObject would count the stage's offset)
    const box = new THREE.Box3();
    for (const m of this.parts) box.union(m.geometry.boundingBox!.clone().applyMatrix4(m.matrix));
    if (!box.isEmpty()) this.inner.position.set(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
    const sKey = JSON.stringify([shape, shells]);
    if (sKey !== this.shellKey) {
      this.shellKey = sKey;
      this.placeExtras(built.filter((b): b is NonNullable<typeof b> => !!b).map((b) => ({ p: b.p, base: b.g.base })),
        shellGeoms.filter((x): x is NonNullable<typeof x> => !!x));
    }
    const moved = shape !== this.lastPlan;
    this.lastPlan = shape;
    return moved;
  }

  /** Extras on the sockets of the placed figure (accessories.accessory_anchors on kit_figure's landmarks). */
  private placeExtras(parts: { p: PlacedPart; base: BaseData }[],
    shells: { s: { part_id: string; colour: string }; item: { kind: string }; g: THREE.BufferGeometry | null }[]) {
    this.extras.children.forEach((o) => ((o as THREE.Mesh).material as THREE.Material)?.dispose?.());
    this.extras.clear();
    if (!shells.length || !parts.length) return;
    const n = parts.reduce((s, x) => s + x.base.n, 0);
    const co = new Float64Array(n * 3);
    const slotOf = new Uint8Array(n);
    let o = 0;
    const v = new THREE.Vector3();
    for (const { p, base } of parts) {
      for (let i = 0; i < base.n; i++) {
        v.set(base.co[i * 3], base.co[i * 3 + 1], base.co[i * 3 + 2]).applyMatrix4(p.matrix);
        co.set([v.x, v.y, v.z], (o + i) * 3);
        slotOf[o + i] = LANDMARK_SLOTS.indexOf(p.slot as KitSlot);
      }
      o += base.n;
    }
    const lm = kitLandmarks(co, slotOf);
    const zUp = new Float64Array(n * 3);
    const shellOf = new Uint8Array(n); // the figure's one surface (shell 0), the tail its own (as the schema has it)
    for (let i = 0; i < n; i++) {
      zUp.set([co[i * 3], -co[i * 3 + 2], co[i * 3 + 1]], i * 3);
      if (LANDMARK_SLOTS[slotOf[i]] === 'tail') shellOf[i] = 3;
    }
    const frames = socketFrames(zUp, lm, shellOf);
    for (const { s, item, g } of shells) {
      const f = frames[item.kind as keyof typeof frames];
      if (!g || !f) continue;
      const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: s.colour, roughness: 0.5, metalness: 0 }));
      mesh.position.set(...f.loc);
      mesh.scale.setScalar(f.scale);
      mesh.name = `extra:${s.part_id}`;
      this.extras.add(mesh);
    }
  }

  /** Where a ray meets a part: its slot and the point in that part's own frame (where its stamps live), or null. */
  pick(ray: THREE.Raycaster): KitHit | null {
    const hit = ray.intersectObjects(this.parts, false)[0];
    if (!hit) return null;
    const local = (hit.object as THREE.Mesh).worldToLocal(hit.point.clone());
    return { slot: hit.object.name as KitSlot, p: [round3(local.x), round3(local.y), round3(local.z)] };
  }

  /** Gate 7 (print = screen): every slot's tile at `size`, as the export paints it (kit_figure.slot_tiles). */
  async bakeTiles(c: KitComposition, size: number): Promise<Record<string, { key: string; rgba: Uint8Array }>> {
    const out: Record<string, { key: string; rgba: Uint8Array }> = {};
    for (const p of kitPlan(this.kit, c)) out[p.slot] = await this.tileFor(p, c, size);
    return out;
  }

  /** The extras on the figure (tests): part ids. */
  extraIds(): string[] {
    return this.extras.children.map((o) => o.name.replace(/^extra:/, ''));
  }

  dispose() {
    this.parts.forEach((m) => (m.material as THREE.Material).dispose());
    this.extras.children.forEach((o) => ((o as THREE.Mesh).material as THREE.Material)?.dispose?.());
    this.clearTextures();
    this.geometry.forEach((p) => void p.then((g) => g?.geometry.dispose()));
  }
}
