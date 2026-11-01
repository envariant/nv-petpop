// A three.js stage in plain TypeScript (decision 122): renderer, camera, lights, optional orbit controls, an optional
// turntable spin, and "fit" (centre a model and frame it). The Vue components wrap it; nothing here knows a framework.
// Lighting is analytic (no HDR download); the canvas measures its CSS box, so a CSS-scaled kiosk frame keeps a sharp
// drawing buffer.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

export interface StageOptions {
  interactive?: boolean; // orbit and pinch-zoom with the pointer
  spin?: boolean;
  spinSpeed?: number; // radians per second
  maxPixelRatio?: number;
}

export class FigureStage {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(30, 1, 1, 5000);
  readonly spinner = new THREE.Group(); // rotates when spinning
  readonly offset = new THREE.Group(); // centres the current object
  controls: OrbitControls | null = null;
  spin: boolean;
  spinSpeed: number;
  private object: THREE.Object3D | null = null;
  private frame = 0;
  private last = performance.now();
  private resize: ResizeObserver;

  constructor(readonly container: HTMLElement, opts: StageOptions = {}) {
    this.spin = opts.spin ?? false;
    this.spinSpeed = opts.spinSpeed ?? 0.35;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, opts.maxPixelRatio ?? 1.5));
    this.renderer.domElement.style.display = 'block';
    this.renderer.domElement.style.width = '100%';
    this.renderer.domElement.style.height = '100%';
    container.appendChild(this.renderer.domElement);
    this.camera.position.set(0, 20, 220);
    this.scene.add(new THREE.HemisphereLight('#ffffff', '#b9a99a', 1.6));
    const key = new THREE.DirectionalLight('#ffffff', 1.8);
    key.position.set(80, 160, 120);
    const fill = new THREE.DirectionalLight('#ffffff', 0.6);
    fill.position.set(-120, 60, -80);
    this.scene.add(key, fill, this.spinner);
    this.spinner.add(this.offset);
    this.setInteractive(opts.interactive ?? false);
    this.resize = new ResizeObserver(() => this.onResize());
    this.resize.observe(container);
    this.onResize();
    const tick = (now: number) => {
      const dt = Math.min((now - this.last) / 1000, 0.1);
      this.last = now;
      if (this.spin) this.spinner.rotation.y += dt * this.spinSpeed;
      this.controls?.update();
      this.renderer.render(this.scene, this.camera);
      this.frame = requestAnimationFrame(tick);
    };
    this.frame = requestAnimationFrame(tick);
  }

  setInteractive(on: boolean): void {
    if (on && !this.controls) {
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enablePan = false;
      this.controls.minDistance = 40;
      this.controls.maxDistance = 800;
      this.renderer.domElement.style.touchAction = 'none';
    } else if (!on && this.controls) {
      this.controls.dispose();
      this.controls = null;
      this.renderer.domElement.style.touchAction = 'auto';
    }
  }

  /** Show `object`, centred on the origin and framed to fill the view. */
  setObject(object: THREE.Object3D | null, margin = 1.12): void {
    if (this.object) this.offset.remove(this.object);
    this.object = object;
    if (!object) return;
    this.offset.add(object);
    this.fit(margin);
  }

  fit(margin = 1.12): void {
    const object = this.object;
    if (!object) return;
    object.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(object.matrixWorld).invert();
    const box = new THREE.Box3();
    const v = new THREE.Vector3();
    object.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const pos = mesh.geometry.getAttribute('position');
      const rel = new THREE.Matrix4().multiplyMatrices(inv, mesh.matrixWorld);
      for (let i = 0; i < pos.count; i += 3) box.expandByPoint(v.fromBufferAttribute(pos, i).applyMatrix4(rel));
    });
    if (box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3());
    const dim = box.getSize(new THREE.Vector3());
    this.offset.position.set(-c.x, -c.y, -c.z);
    const { width, height } = this.size();
    const vfov = (this.camera.fov * Math.PI) / 180;
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * (width / height));
    const radiusXZ = Math.max(dim.x, dim.z) / 2;
    const dist = Math.max(dim.y / 2 / Math.tan(vfov / 2), radiusXZ / Math.tan(hfov / 2)) * margin + Math.max(dim.x, dim.z) / 2;
    this.camera.position.set(0, dim.y * 0.08, dist);
    this.camera.near = dist / 50;
    this.camera.far = dist * 10;
    this.camera.lookAt(0, 0, 0);
    this.camera.updateProjectionMatrix();
    if (this.controls) {
      this.controls.target.set(0, 0, 0);
      this.controls.update();
    }
  }

  /** A ray from the camera through a pointer event's position on the canvas. */
  rayFrom(e: { clientX: number; clientY: number }): THREE.Raycaster {
    const r = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    return ray;
  }

  private size(): { width: number; height: number } {
    return { width: Math.max(this.container.clientWidth, 1), height: Math.max(this.container.clientHeight, 1) };
  }

  private onResize(): void {
    const { width, height } = this.size();
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.fit();
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls?.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
