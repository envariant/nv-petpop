// react-three-fiber views: the live Build preview (base mesh + morph weights + painted albedo) and the
// result viewer (GLB with Draco, turntable, pinch zoom, textured/clay toggle). No network beyond our origin:
// Draco decoders are served from /draco/ and the lighting is analytic (no HDR download).
import { OrbitControls, useGLTF } from '@react-three/drei';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Component, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import * as THREE from 'three';
import type { PetSpec } from '../api/types';
import { loadMasks, paintAlbedo, type Masks } from '../lib/albedo';
import { morphWeights } from '../lib/morph';

const DRACO = '/draco/';

class GlBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

/** Centre the model on the origin, base on the floor line, and move the camera so it fills the view. */
function Fit({ object, margin = 1.12 }: { object: THREE.Object3D; margin?: number }) {
  const { camera, size, controls } = useThree();
  const [offset, setOffset] = useState<[number, number, number]>([0, 0, 0]);
  useEffect(() => {
    // Bounds in the object's own frame (ignores the spinning parent).
    object.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(object.matrixWorld).invert();
    const box = new THREE.Box3();
    object.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const g = mesh.geometry;
      const pos = g.getAttribute('position');
      const rel = new THREE.Matrix4().multiplyMatrices(inv, mesh.matrixWorld);
      const v = new THREE.Vector3();
      for (let i = 0; i < pos.count; i += 3) box.expandByPoint(v.fromBufferAttribute(pos, i).applyMatrix4(rel));
    });
    if (box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3());
    const dim = box.getSize(new THREE.Vector3());
    setOffset([-c.x, -c.y, -c.z]);
    const cam = camera as THREE.PerspectiveCamera;
    const vfov = (cam.fov * Math.PI) / 180;
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * (size.width / size.height));
    const radiusXZ = Math.max(dim.x, dim.z) / 2;
    const dist = Math.max(dim.y / 2 / Math.tan(vfov / 2), radiusXZ / Math.tan(hfov / 2)) * margin + Math.max(dim.x, dim.z) / 2;
    cam.position.set(0, dim.y * 0.08, dist);
    cam.near = dist / 50;
    cam.far = dist * 10;
    cam.lookAt(0, 0, 0);
    cam.updateProjectionMatrix();
    const orbit = controls as unknown as { target?: THREE.Vector3; update?: () => void } | null;
    if (orbit?.target) {
      orbit.target.set(0, 0, 0);
      orbit.update?.();
    }
  }, [object, camera, controls, size.width, size.height]);
  return (
    <group position={offset}>
      <primitive object={object} />
    </group>
  );
}

function Spin({ children, speed = 0.35, enabled = true }: { children: ReactNode; speed?: number; enabled?: boolean }) {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    if (enabled && ref.current) ref.current.rotation.y += dt * speed;
  });
  return <group ref={ref}>{children}</group>;
}

export function Stage({ children, fallback, interactive = false, testId, className }: { children: ReactNode; fallback?: ReactNode; interactive?: boolean; testId?: string; className?: string }) {
  const [gl] = useState(webglAvailable);
  const fb = fallback ?? <div className="flex h-full items-center justify-center text-2xl text-muted">3D preview unavailable</div>;
  return (
    <div className={className ?? 'h-full w-full'} data-testid={testId} style={{ touchAction: interactive ? 'none' : 'auto' }}>
      {gl ? (
        <GlBoundary fallback={fb}>
          <Canvas resize={{ offsetSize: true }} camera={{ position: [0, 20, 220], fov: 30, near: 1, far: 5000 }} dpr={[1, 1.5]} gl={{ preserveDrawingBuffer: true, antialias: true }}>
            <hemisphereLight args={['#ffffff', '#b9a99a', 1.6]} />
            <directionalLight position={[80, 160, 120]} intensity={1.8} />
            <directionalLight position={[-120, 60, -80]} intensity={0.6} />
            <Suspense fallback={null}>
              {children}
            </Suspense>
            {interactive && <OrbitControls makeDefault enablePan={false} minDistance={40} maxDistance={800} />}
          </Canvas>
        </GlBoundary>
      ) : (
        fb
      )}
    </div>
  );
}

function PreviewMesh({ spec }: { spec: PetSpec }) {
  const { scene } = useGLTF(`/assets/base/${spec.species}/base.glb`, DRACO);
  const model = useMemo(() => scene.clone(true), [scene]);
  const [masks, setMasks] = useState<Masks | null>(null);
  const texture = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const t = new THREE.CanvasTexture(c);
    t.flipY = false;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);
  const material = useMemo(() => new THREE.MeshStandardMaterial({ map: texture, roughness: 0.55, metalness: 0 }), [texture]);

  useEffect(() => {
    let live = true;
    loadMasks(spec.species).then((m) => live && setMasks(m)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [spec.species]);

  useEffect(() => {
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) mesh.material = material;
    });
  }, [model, material]);

  useEffect(() => {
    const w = morphWeights(spec);
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh || !mesh.morphTargetDictionary || !mesh.morphTargetInfluences) return;
      for (const [name, idx] of Object.entries(mesh.morphTargetDictionary)) mesh.morphTargetInfluences[idx] = w[name] ?? 0;
    });
    if (masks) {
      const canvas = texture.image as HTMLCanvasElement;
      const g = canvas.getContext('2d')!;
      const img = g.createImageData(masks.size, masks.size);
      paintAlbedo(spec, masks, img);
      g.putImageData(img, 0, 0);
      texture.needsUpdate = true;
    }
  }, [spec, model, masks, texture]);

  return <Fit object={model} />;
}

export function PreviewFigure({ spec, spin = true }: { spec: PetSpec; spin?: boolean }) {
  return (
    <Stage testId="live-preview">
      <Spin enabled={spin} speed={0.25}>
        <PreviewMesh spec={spec} />
      </Spin>
    </Stage>
  );
}

const CLAY = new THREE.MeshStandardMaterial({ color: '#cfc6bb', roughness: 0.8, metalness: 0 });

function GlbMesh({ url, clay }: { url: string; clay: boolean }) {
  const { scene } = useGLTF(url, DRACO);
  const model = useMemo(() => scene.clone(true), [scene]);
  const originals = useMemo(() => {
    const m = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) m.set(mesh, mesh.material);
    });
    return m;
  }, [model]);
  useEffect(() => {
    originals.forEach((mat, mesh) => {
      mesh.material = clay ? CLAY : mat;
    });
  }, [clay, originals]);
  return <Fit object={model} />;
}

export function GlbFigure({ url, clay = false, spin = true, interactive = false, fallbackImage, testId }: { url: string; clay?: boolean; spin?: boolean; interactive?: boolean; fallbackImage?: string; testId?: string }) {
  const fallback = fallbackImage ? <img src={fallbackImage} alt="figurine" className="h-full w-full object-contain" /> : undefined;
  return (
    <Stage interactive={interactive} fallback={fallback} testId={testId}>
      <Spin enabled={spin}>
        <GlbMesh url={url} clay={clay} />
      </Spin>
    </Stage>
  );
}
