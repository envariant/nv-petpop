// Part kits (decision 127), the TypeScript twin of packages/library/python/petpop_library/parts.py (golden-tested
// against it): joint frames, a part's placement on its torso slot, the leg twists and head angles of a pose, and the
// right legs as mirror images of the left. Frame: glTF, mm, +Y up, +Z the pet's front, +X the pet's own left.
import * as THREE from 'three';

export type Kind = 'head' | 'torso' | 'front_leg' | 'hind_leg' | 'tail';
export type Slot = 'head' | 'front_left' | 'front_right' | 'hind_left' | 'hind_right' | 'tail';
export type Vec3 = [number, number, number] | number[];
export interface JointData { pivot: Vec3; axis: Vec3; twist?: number }
export interface AttachmentData { position: Vec3; axis: Vec3; twist?: number }
export interface PoseData { legs?: Partial<Record<'front_left' | 'front_right' | 'hind_left' | 'hind_right', number>>; head?: { yaw?: number; pitch?: number; roll?: number } }

export const KINDS: Kind[] = ['head', 'torso', 'front_leg', 'hind_leg', 'tail'];
export const SLOTS: Slot[] = ['head', 'front_left', 'front_right', 'hind_left', 'hind_right', 'tail'];
export const SLOT_KIND: Record<Slot, Kind> = { head: 'head', front_left: 'front_leg', front_right: 'front_leg', hind_left: 'hind_leg', hind_right: 'hind_leg', tail: 'tail' };
export const MIRRORED = new Set<Slot>(['front_right', 'hind_right']);
export const LEG_SLOTS = ['front_left', 'front_right', 'hind_left', 'hind_right'] as const;
export const PAIRS: Partial<Record<Slot, Slot>> = { front_left: 'front_right', front_right: 'front_left', hind_left: 'hind_right', hind_right: 'hind_left' };
export const LEG_STEP_DEG = 120;
const FRONT = new THREE.Vector3(0, 0, 1);
const UP = new THREE.Vector3(0, 1, 0);
const DEG = Math.PI / 180;

const v3 = (a: Vec3) => new THREE.Vector3(a[0], a[1], a[2]);
const unit = (a: Vec3 | THREE.Vector3) => (a instanceof THREE.Vector3 ? a.clone() : v3(a)).normalize();

/** A joint's frame: columns (axis, ref, axis x ref), ref being the world front projected off the axis (world up when
 *  the axis is nearly front or back), turned by the twist about the axis. */
export function frame(axis: Vec3, twist = 0): THREE.Matrix4 {
  const a = unit(axis);
  const base = Math.abs(a.dot(FRONT)) < 0.95 ? FRONT : UP;
  const r = base.clone().addScaledVector(a, -base.dot(a)).normalize().applyAxisAngle(a, twist * DEG);
  const c = new THREE.Vector3().crossVectors(a, r);
  return new THREE.Matrix4().makeBasis(a, r, c);
}

export function mirrorJoint(j: JointData): JointData {
  return { pivot: [-j.pivot[0], j.pivot[1], j.pivot[2]], axis: [-j.axis[0], j.axis[1], j.axis[2]], twist: -(j.twist ?? 0) };
}

/** The pose's extra rotation at a slot, about the attachment's frame. */
export function poseRotation(slot: Slot, attach: AttachmentData, pose?: PoseData | null): THREE.Matrix4 {
  if ((LEG_SLOTS as readonly string[]).includes(slot)) {
    const k = (((pose?.legs?.[slot as (typeof LEG_SLOTS)[number]] ?? 0) % 3) + 3) % 3;
    const deg = LEG_STEP_DEG * k * (MIRRORED.has(slot) ? -1 : 1);
    return new THREE.Matrix4().makeRotationAxis(unit(attach.axis), deg * DEG);
  }
  if (slot === 'head') {
    const f = frame(attach.axis, attach.twist ?? 0);
    const a = new THREE.Vector3(), r = new THREE.Vector3(), c = new THREE.Vector3();
    f.extractBasis(a, r, c);
    const h = pose?.head ?? {};
    return new THREE.Matrix4().makeRotationAxis(r, (h.yaw ?? 0) * DEG)
      .multiply(new THREE.Matrix4().makeRotationAxis(c, (h.pitch ?? 0) * DEG))
      .multiply(new THREE.Matrix4().makeRotationAxis(a, (h.roll ?? 0) * DEG));
  }
  return new THREE.Matrix4();
}

/** The matrix taking a part's own (authored, left-leg) coordinates to the figure: mirrored for the right legs, its
 *  pivot onto the slot's attachment, its frame onto the attachment's, then the pose's turn. */
export function placement(part: JointData, attach: AttachmentData, slot: Slot, pose?: PoseData | null): THREE.Matrix4 {
  const mirrored = MIRRORED.has(slot);
  const j = mirrored ? mirrorJoint(part) : part;
  const R = poseRotation(slot, attach, pose)
    .multiply(frame(attach.axis, attach.twist ?? 0))
    .multiply(frame(j.axis, j.twist ?? 0).transpose());
  const t = v3(attach.position).sub(v3(j.pivot).applyMatrix4(R));
  const M = R.clone().setPosition(t);
  return mirrored ? M.multiply(new THREE.Matrix4().makeScale(-1, 1, 1)) : M;
}

/** The mirror of a slot's attachment (symmetry in the workbench: a left slot's edit copied to the right). */
export function mirrorAttachment(a: AttachmentData): AttachmentData {
  return { position: [-a.position[0], a.position[1], a.position[2]], axis: [-a.axis[0], a.axis[1], a.axis[2]], twist: -(a.twist ?? 0) };
}

/** Head angles outside the head's limits (empty when the pose fits). */
export function headProblems(pose: PoseData, limits: Record<'yaw' | 'pitch' | 'roll', number[]>): string[] {
  return (['yaw', 'pitch', 'roll'] as const).flatMap((k) => {
    const v = pose.head?.[k] ?? 0;
    const [lo, hi] = limits[k];
    return v < lo - 1e-6 || v > hi + 1e-6 ? [`head ${k} ${v} is outside ${lo}..${hi}`] : [];
  });
}
