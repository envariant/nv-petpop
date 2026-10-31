"""Gate 8: "a release bundle loads on a clean kiosk" (BRIEF Section 16).

Studio side (one temporary install): a batch of real pipeline runs on the active GenAI profile (the mock profile's
stand-ins in CI), curated into library meshes (one per figurine, with its family; decision 119), the passing ones accepted and
published, and a release packed. Kiosk side (a second, clean install: no proxy library, its own database and
store): the bundle dropped in its inbox loads, becomes active, and a composition on a new figurine's own mesh
exports to a print bundle.

    python scripts/gate8_clean_kiosk.py
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PETPOP_QUALITY", "test")


def fresh(var: Path, **env: str) -> None:
    os.environ.update(PETPOP_VAR=str(var), PETPOP_RELEASE_INBOX=str(var / "inbox"), **env)
    from backend.api import db

    db._engines.clear()


def main() -> int:
    from backend.api import models as m
    from petpop_library import release

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from gate8_lib import accept_and_publish, run_batch

    studio_var, kiosk_var = Path(tempfile.mkdtemp(prefix="pp-g8-studio-")), Path(tempfile.mkdtemp(prefix="pp-g8-kiosk-"))
    # ---------------------------------------------------------------- Studio
    fresh(studio_var, PETPOP_SEED_PROXY_LIBRARY="1")
    from backend.api.service import BackendApi
    from backend.core.config import settings
    from backend.worker.service import Worker

    s = settings()
    api, worker = BackendApi(s), Worker(s, queue="studio")
    batch = run_batch(api, worker, "dog", ["beagle", "border_collie"])
    batch = accept_and_publish(api, batch)
    summ = batch.summary
    print(f"studio: {summ.figurines} figurines, {summ.passed_qc}/{summ.candidates} passed QC, {summ.published} published, "
          f"{summ.meshes_published} meshes")
    info = asyncio.run(api.create_release(m.ReleaseCreate(species="dog"), m.StaffUser(username="gate8", role="admin")))
    bundle = (s.release_inbox[0] / f"{info.release_version}.tar").read_bytes()
    manifest, _ = release.read(bundle)
    assert release.release_errors(manifest) == [], "release manifest invalid"
    new_parts = [c for f in batch.figurines for c in f.candidates if c.status == "published"]
    print(f"studio: packed {info.release_version} ({info.bytes / 1e6:.1f} MB): {json.dumps(info.counts)}")

    # ---------------------------------------------------------------- a clean kiosk
    fresh(kiosk_var, PETPOP_SEED_PROXY_LIBRARY="0")
    (kiosk_var / "inbox").mkdir(parents=True)
    shutil.copy(s.release_inbox[0] / f"{info.release_version}.tar", kiosk_var / "inbox")
    from backend.api.service import BackendApi as KioskApi_

    ks = settings()
    kiosk = KioskApi_(ks)
    versions = kiosk.library.versions()
    ok = versions.get("dog") == info.release_version and "cat" not in versions
    print(f"kiosk: releases loaded {versions} (no proxy library)")
    rel = kiosk.library.active("dog").manifest
    from petpop_library.composition import sample

    from petpop_library import release as rel_mod

    _, rel_files = rel_mod.read((kiosk_var / "inbox" / f"{info.release_version}.tar").read_bytes())
    comp = sample(rel, layers=3, stamps=20, pet_name="Fresh", files=rel_files)
    fams = [c for c in new_parts if c.kind == "family"]
    if fams:  # a new figurine's family, on its own mesh: no part variants from another mesh, stamps on this mesh
        fam = next(f for f in rel["families"] if f["id"] == fams[0].id)
        comp = sample(rel, layers=3, stamps=20, pet_name="Fresh", files=rel_files, family=fam["id"])
        ok &= fam["mesh_id"] in {me["id"] for me in rel["meshes"]} and fam["mesh_id"] == comp["mesh_id"]
    used = [comp["family_id"], *comp["parts"].values()]
    sess = asyncio.run(kiosk.create_session(m.SessionCreate(kiosk_id="clean-kiosk")))
    st = asyncio.run(kiosk.create_composition(m.CompositionCreate(session_id=sess.session_id, composition=comp), "http://kiosk"))
    acc = asyncio.run(kiosk.export_composition(st.composition_id))
    result = Worker(ks, queue="kiosk").run_job(acc.job_id)
    st = asyncio.run(kiosk.get_composition(st.composition_id, "http://kiosk"))
    names = {a.name for a in st.artefacts}
    ok &= result == "done" and {"figure.3mf", "figure.stl", "composition.json"} <= names
    ok &= any(p.id in used for p in new_parts)
    print(f"kiosk: composition with {sum(p.id in used for p in new_parts)} new parts -> export {result}, ticket {acc.ticket}, "
          f"{len(names)} artefacts")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
