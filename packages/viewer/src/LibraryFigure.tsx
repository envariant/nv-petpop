// The kiosk's Design preview (BRIEF Section 16): one release mesh with its family delta and part variants applied
// as vertex offsets, shell parts on their sockets, pattern layers in the shader and stamps in an atlas texture.
// It is the final asset, not a proxy: the export composes the same deltas and paints the same atlas.
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ThreeEvent } from '@react-three/fiber';
import { useThree } from '@react-three/fiber';
import * as THREE from 'three';
import {
  bakeAtlas, buildGeometry, composeCoords, hitToBase, makeUniforms, patternMaterial, setPattern, socketFrames, updateGeometry,
  type Composition, type LoadedLibrary, type PaintHit, type SplitGeometry,
} from '@petpop/scene';
import { Fit, Spin, Stage } from './Figure3D';


function Composed({ lib, composition, onPaint, onBake }: { lib: LoadedLibrary; composition: Composition; onPaint?: (h: PaintHit) => void; onBake?: (bake: () => Uint8Array) => void }) {
  const gl = useThree((s) => s.gl);
  const split = useMemo<SplitGeometry>(() => buildGeometry(lib.base), [lib]);
  const uniforms = useMemo(() => makeUniforms(lib.textures, lib.meshEntry.atlas.channels), [lib]);
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

  // Geometry: family delta + part variants of this mesh (loaded on demand), recomposed on every part swap.
  const deltaKey = JSON.stringify([composition.family_id, composition.parts]);
  useEffect(() => {
    let live = true;
    const m = lib.manifest;
    const fam = m.families.find((f) => f.id === composition.family_id && f.mesh_id === lib.meshEntry.id);
    const parts = Object.values(composition.parts)
      .map((id) => m.region_deltas.find((d) => d.id === id && d.mesh_id === lib.meshEntry.id))
      .filter((d): d is NonNullable<typeof d> => !!d);
    Promise.all([fam?.delta ? lib.delta(fam.delta) : Promise.resolve(null), ...parts.map((p) => lib.delta(p.delta))]).then((ds) => {
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
    onBake?.(() => bakeAtlas(gl, uniforms, lib.meshEntry.atlas.size));
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
