"""Studio's library (BRIEF Section 16, M8) through the contract, on the mock server and the real backend alike:
a batch is generated and curated into parts, a curator reviews, edits and publishes, an admin packs a release,
and the kiosk switches to it."""
from __future__ import annotations

import time

from petpop_library import release

from .oas import check
from .test_contract import K, S, login, new_session

def wait_batch(client, auth: dict, bid: str, timeout: float = 900) -> dict:
    t0 = time.time()
    while True:
        b = check(f"{S}/batches/{{batch_id}}", "get", client.get(f"{S}/batches/{bid}", headers=auth))
        if b["summary"]["finished"] == b["summary"]["figurines"]:
            return b
        assert time.time() - t0 < timeout, f"batch {bid} stuck: {b['summary']}"
        time.sleep(0.5)


def test_studio_library_from_batch_to_kiosk_release(client):
    op, cur, adm = login(client, "operator"), login(client, "curator"), login(client, "admin")

    # The starting library is the proxy release, published.
    lib = check(f"{S}/library/{{species}}", "get", client.get(f"{S}/library/dog", headers=op))
    assert lib["items"] and {i["status"] for i in lib["items"]} == {"published"}
    assert {i["kind"] for i in lib["items"]} == {"family", "region", "shell", "pattern"}
    rels = check(f"{S}/releases", "get", client.get(f"{S}/releases", headers=op))
    assert any(r["release_version"] == "release-dog-1" for r in rels["items"])

    # A batch: breeds x variants x seeds, each a full pipeline run, then curated into candidates.
    r = client.post(f"{S}/batches", headers=op, json={"species": "dog", "breeds": ["beagle", "pug"], "seeds": 1,
                                                       "variants": [{"label": "preset", "patch": {}}]})
    assert r.status_code == 201, r.text
    bid = check(f"{S}/batches", "post", r)["batch_id"]
    b = wait_batch(client, op, bid)
    assert b["summary"]["figurines"] == 2 and b["summary"]["failed"] == 0
    assert b["status"] == "review"
    assert any(x["batch_id"] == bid for x in check(f"{S}/batches", "get", client.get(f"{S}/batches", headers=op))["items"])
    fig = b["figurines"][0]
    assert fig["glb_url"] and fig["thumbnail_url"]
    cands = fig["candidates"]
    assert len(cands) == 6 and {c["kind"] for c in cands} == {"family", "region"}
    assert all({"symmetry_mm", "boundary_strain", "self_intersections", "passed", "reasons"} <= set(c["qc"]) for c in cands)
    assert all(c["status"] == ("rejected" if c["auto_rejected"] else "draft") for c in cands)

    # Review: curators only. Accept every candidate that passed QC, tag one, reject one.
    passing = [c for c in cands if not c["auto_rejected"]]
    assert passing, "QC should pass at least one part of a clean figurine"
    body = {"decisions": [{"item_id": c["id"], "action": "accept"} for c in passing]}
    assert client.post(f"{S}/batches/{bid}/review", headers=op, json=body).status_code == 403
    body["decisions"][0]["tags"] = ["hero"]
    reviewed = check(f"{S}/batches/{{batch_id}}/review", "post", client.post(f"{S}/batches/{bid}/review", headers=cur, json=body))
    statuses = {c["id"]: c for c in reviewed["figurines"][0]["candidates"]}
    assert all(statuses[c["id"]]["status"] == "accepted" for c in passing)
    assert "hero" in statuses[passing[0]["id"]]["tags"]
    assert client.post(f"{S}/batches/{bid}/review", headers=cur, json={"decisions": [{"item_id": "nope", "action": "reject"}]}).status_code == 404

    # Publish the accepted parts; a rejected one cannot be published.
    for c in passing:
        kind = c["kind"]
        p = check(f"{S}/library/{{species}}/{{kind}}/{{item_id}}/publish", "post",
                  client.post(f"{S}/library/dog/{kind}/{c['id']}/publish", headers=cur))
        assert p["status"] == "published" and p["published_version"] == p["version"] and p["thumbnail_url"]
    rejected = [c for c in cands if c["auto_rejected"]]
    if rejected:
        r = client.post(f"{S}/library/dog/{rejected[0]['kind']}/{rejected[0]['id']}/publish", headers=cur)
        assert r.status_code == 409

    # Pattern editor: editing a published layer starts version 2; publishing it supersedes version 1.
    pat = next(i for i in lib["items"] if i["kind"] == "pattern")
    patch = {"name": "Big blaze", "default_colour": "#fafafa", "coverage": {"min": 0.1, "max": 0.9, "default": 0.5}}
    assert client.patch(f"{S}/library/dog/pattern/{pat['id']}", headers=op, json=patch).status_code == 403
    edited = check(f"{S}/library/{{species}}/{{kind}}/{{item_id}}", "patch",
                   client.patch(f"{S}/library/dog/pattern/{pat['id']}", headers=cur, json=patch))
    assert edited["version"] == pat["version"] + 1 and edited["status"] == "draft" and edited["published_version"] == pat["version"]
    bad = client.patch(f"{S}/library/dog/pattern/{pat['id']}", headers=cur, json={"coverage": {"min": 0.8, "max": 0.2, "default": 0.5}})
    assert bad.status_code == 422
    pub = check(f"{S}/library/{{species}}/{{kind}}/{{item_id}}/publish", "post",
                client.post(f"{S}/library/dog/pattern/{pat['id']}/publish", headers=cur))
    assert pub["version"] == edited["version"] and pub["published_version"] == edited["version"]
    # Parts editor: rename and tag a shell.
    shell = next(i for i in lib["items"] if i["kind"] == "shell")
    renamed = check(f"{S}/library/{{species}}/{{kind}}/{{item_id}}", "patch",
                    client.patch(f"{S}/library/dog/shell/{shell['id']}", headers=cur, json={"name": "Red collar", "tags": ["classic"]}))
    assert renamed["name"] == "Red collar"

    # Release: admins only. Signed, schema-valid, with the new parts and the new pattern version.
    assert client.post(f"{S}/releases", headers=cur, json={"species": "dog"}).status_code == 403
    r = client.post(f"{S}/releases", headers=adm, json={"species": "dog"})
    assert r.status_code == 201, r.text
    info = check(f"{S}/releases", "post", r)
    assert info["release_version"] == "release-dog-2" and info["number"] == 2
    bundle = client.get(info["url"]).content
    manifest, files = release.read(bundle)
    assert release.release_errors(manifest) == []
    ids = {e["id"]: e for k in ("families", "region_deltas", "shell_parts", "pattern_layers") for e in manifest[k]}
    assert all(c["id"] in ids for c in passing)
    assert ids[pat["id"]]["version"] == pub["version"] and ids[pat["id"]]["default_colour"] == "#FAFAFA"
    assert ids[shell["id"]]["name"] != "Red collar"  # edited but not republished: the release keeps the published version

    # The kiosk switches to it and accepts a composition that uses the new parts.
    rel = check(f"{K}/library/{{species}}", "get", client.get(f"{K}/library/dog"))
    assert rel["release_version"] == "release-dog-2"
    region = next((c for c in passing if c["kind"] == "region"), None)
    if region:
        from petpop_library.composition import sample

        comp = sample(rel["manifest"], layers=2)
        comp["parts"][region["region"]] = region["id"]
        sid = new_session(client)
        r = client.post(f"{K}/compositions", json={"session_id": sid, "composition": comp})
        assert r.status_code == 201, r.text

    # Unpublish takes an item out of the next release.
    first = passing[0]
    un = check(f"{S}/library/{{species}}/{{kind}}/{{item_id}}/unpublish", "post",
               client.post(f"{S}/library/dog/{first['kind']}/{first['id']}/unpublish", headers=cur))
    assert un["status"] == "accepted" and un["published_version"] is None


def test_batch_validation(client):
    op = login(client, "operator")
    assert client.post(f"{S}/batches", headers=op, json={"species": "dog", "breeds": ["dragon"]}).status_code == 422
    r = client.post(f"{S}/batches", headers=op, json={"species": "dog", "breeds": ["beagle"] * 7, "seeds": 10})
    assert r.status_code == 422
    check(f"{S}/batches", "post", r)
    bad_variant = {"species": "cat", "breeds": ["siamese"], "variants": [{"label": "bad", "patch": {"ears": {"shape": "antenna"}}}]}
    assert client.post(f"{S}/batches", headers=op, json=bad_variant).status_code == 422
    assert client.get(f"{S}/batches/b_nope", headers=op).status_code == 404
    assert client.get(f"{S}/batches").status_code == 401
    assert client.post(f"{S}/library/dog/region/nope/publish", headers=login(client, "curator")).status_code == 404
