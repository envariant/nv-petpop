"""base.bin + mesh.json: the base mesh as the kiosk's viewer consumes it (packages/viewer/src/library.ts).

The preview is built from the same vertex order the deltas are keyed on (the GLB splits vertices at UV seams, so
it cannot be used for deltas). Layout of base.bin, little endian:

    magic  "PPB1"
    u32    n (vertices), u32 t (triangles)
    f32    co[n * 3]          base positions, mm, Z up, front -Y
    u32    tri[t * 3]         vertex indices
    f32    uv[t * 6]          corner UVs (u, v per corner)
    u8     shell[n]           0 body, 1 ear_L, 2 ear_R, 3 tail, 4 eye_L, 5 eye_R, 6 nose
"""
from __future__ import annotations

import json
import struct

import numpy as np

from .meshkit import BaseMesh

MAGIC = b"PPB1"


def base_bin(base: BaseMesh) -> bytes:
    n, t = len(base.co), len(base.tri_verts)
    uv = base.uv[base.tri_loops].astype("<f4").reshape(t, 6)
    return b"".join([
        MAGIC, struct.pack("<II", n, t),
        base.co.astype("<f4").tobytes(), base.tri_verts.astype("<u4").tobytes(), uv.tobytes(),
        base.shell.astype(np.uint8).tobytes(),
    ])


def read_base_bin(data: bytes) -> dict[str, np.ndarray]:
    if data[:4] != MAGIC:
        raise ValueError("not a base.bin")
    n, t = struct.unpack_from("<II", data, 4)
    off = 12
    co = np.frombuffer(data, "<f4", n * 3, off).reshape(n, 3)
    off += n * 12
    tri = np.frombuffer(data, "<u4", t * 3, off).reshape(t, 3)
    off += t * 12
    uv = np.frombuffer(data, "<f4", t * 6, off).reshape(t, 3, 2)
    off += t * 24
    shell = np.frombuffer(data, np.uint8, n, off)
    return {"co": co, "tri": tri, "uv": uv, "shell": shell}


def mesh_json(base: BaseMesh, version: str) -> bytes:
    doc = {"base_mesh_version": version, "topology": base.topology_hash(), "vertices": int(len(base.co)),
           "triangles": int(len(base.tri_verts)), "bin": "base.bin",
           "landmarks": {k: int(v) for k, v in sorted(base.landmarks.items())}}
    return (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode()
