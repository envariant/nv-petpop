// A library composition as a three.js object (BRIEF Section 16, decision 118), the same maths as the export: the
// mesh with its family delta and part variants, shells on their sockets, pattern layers in the shader and stamps in
// an atlas texture. Framework-free: the Vue Design screen drives it, the React viewer did the same in components.
import * as THREE from 'three';
import { hitToBase, buildGeometry, composeCoords, socketFrames, updateGeometry, type Composition, type SplitGeometry } from './library';
import type { LoadedLibrary } from './load';
import { bakeAtlas, makeUniforms, patternMaterial, setPattern } from './PatternMaterial';

export class ComposedFigure {
  /** Y-up root to hand to FigureStage.setObject (the release meshes are Z-up). */
  readonly root = new THREE.Group();
  readonly body: THREE.Mesh;
  readonly uniforms: Record<string, THREE.IUniform>;
  co: Float64Array | null = null;
  private readonly zUp = new THREE.Group();
  private readonly split: SplitGeometry;
  private shells: THREE.Mesh[] = [];
  private geometryKey = '';
  private shellKey = '';

  constructor(readonly lib: LoadedLibrary) {
    this.split = buildGeometry(lib.base);
    this.uniforms = makeUniforms(lib.textures, lib.meshEntry.atlas.channels);
    this.body = new THREE.Mesh(this.split.geometry, patternMaterial(this.uniforms));
    this.zUp.rotation.x = -Math.PI / 2;
    this.zUp.add(this.body);
    this.root.add(this.zUp);
  }

  /** Apply a composition: geometry and shells when they changed, colours and layers always (uniforms only).
   *  Resolves once the geometry is ready; returns whether the geometry changed (the stage should re-fit). */
  async update(c: Composition): Promise<boolean> {
    this.colours(c);
    let changed = false;
    const gKey = JSON.stringify([c.family_id, c.parts]);
    if (gKey !== this.geometryKey) {
      this.geometryKey = gKey;
      const m = this.lib.manifest;
      const fam = m.families.find((f) => f.id === c.family_id && f.mesh_id === this.lib.meshEntry.id);
      const parts = Object.values(c.parts)
        .map((id) => m.region_deltas.find((d) => d.id === id && d.mesh_id === this.lib.meshEntry.id))
        .filter((d): d is NonNullable<typeof d> => !!d);
      const ds = await Promise.all([fam?.delta ? this.lib.delta(fam.delta) : Promise.resolve(null), ...parts.map((p) => this.lib.delta(p.delta))]);
      if (gKey !== this.geometryKey) return false; // a newer update won
      this.co = composeCoords(this.lib.base, ds);
      updateGeometry(this.lib.base, this.split, this.co);
      this.shellKey = ''; // sockets move with the geometry
      changed = true;
    }
    const sKey = JSON.stringify(c.shells);
    if (this.co && sKey !== this.shellKey) {
      this.shellKey = sKey;
      const frames = socketFrames(this.co, this.lib.mesh.landmarks, this.lib.base.shell);
      const meshes = await Promise.all(
        c.shells.map(async (s) => {
          const item = this.lib.manifest.shell_parts.find((p) => p.id === s.part_id);
          if (!item) return null;
          const mesh = new THREE.Mesh(await this.lib.shell(item.mesh), new THREE.MeshStandardMaterial({ color: s.colour, roughness: 0.5, metalness: 0 }));
          const f = frames[item.kind];
          if (f) {
            mesh.position.set(...f.loc);
            mesh.scale.setScalar(f.scale);
          }
          return mesh;
        }),
      );
      if (sKey !== this.shellKey) return changed;
      this.shells.forEach((s) => this.zUp.remove(s));
      this.shells = meshes.filter(Boolean) as THREE.Mesh[];
      this.shells.forEach((s) => this.zUp.add(s));
    }
    return changed;
  }

  colours(c: Composition): void {
    const pl = this.lib.manifest.pattern_layers;
    setPattern(this.uniforms, {
      base: c.base_colour, eye: c.eye_colour, nose: c.nose_colour,
      layers: c.layers.map((l) => ({ channel: pl.find((p) => p.id === l.pattern_id)?.channel ?? 0, coverage: l.coverage, colour: l.colour })),
    });
  }

  /** Where a ray meets the body, as a position on the undeformed mesh (where stamps live), or null. */
  pick(ray: THREE.Raycaster): [number, number, number] | null {
    if (!this.co) return null;
    const hit = ray.intersectObject(this.body, false)[0];
    if (!hit || hit.faceIndex == null) return null;
    return hitToBase(this.lib.base, this.co, hit.faceIndex, this.body.worldToLocal(hit.point.clone()));
  }

  /** The composited atlas, unlit, texel for texel (gate 7: the print matches the screen). */
  bake(renderer: THREE.WebGLRenderer): Uint8Array {
    return bakeAtlas(renderer, this.uniforms, this.lib.meshEntry.atlas.size);
  }
}
