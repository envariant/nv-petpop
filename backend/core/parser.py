"""Rule-based Stage A parser over vocab.json (BRIEF Sections 6.1 and 13).

Turns free text into a PetSpec patch using only schema enumerations. Anything it cannot map goes to
`personality` (non-physical traits) or `free_text_unmapped`. Fields the user tapped are never touched.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .breeds import all_breeds
from .spec import apply_patch, flatten, is_tapped, set_path
from .vocab import vocab

STOP = set("""a an the and or but with of is are was has have his her its their my our your he she it they
him them this that very really quite so too just also to in on at for from by as be been being who which
one little bit loves love likes like about named called s""".split())

BREED_GENERIC = set("""terrier retriever shepherd spaniel hound welsh english german dog mountain domestic
shorthair longhair cat american standard miniature bull toy king charles pit italian scottish west highland
white great saint russian blue turkish british exotic forest norwegian cornish devon orange alaskan rough
siberian staffordshire jack frise inu coon tabby""".split())

NICKNAMES = {
    "dog": {"lab": "labrador", "gsd": "german_shepherd", "alsatian": "german_shepherd", "frenchie": "french_bulldog",
            "staffie": "staffy", "westie": "west_highland", "yorkie": "yorkshire_terrier",
            "sausage dog": "dachshund", "doxie": "dachshund", "pom": "pomeranian", "berner": "bernese",
            "doodle": "labradoodle", "pittie": "pitbull", "cav": "cavalier", "sheltie": "sheltie"},
    "cat": {"moggy": "domestic_shorthair", "tortie": "tortoiseshell", "coon": "maine_coon", "wegie": "norwegian_forest"},
}


@dataclass
class ParseResult:
    patch: dict[str, Any] = field(default_factory=dict)
    changed_fields: list[str] = field(default_factory=list)
    personality: list[str] = field(default_factory=list)
    free_text_unmapped: str = ""
    blocked: bool = False
    ms: int = 0


class _Text:
    def __init__(self, text: str) -> None:
        self.raw = text
        self.s = " " + re.sub(r"[^a-z0-9' -]+", " ", text.lower().replace("-", " ")) + " "
        self.used = [False] * len(self.s)

    def find(self, phrase: str) -> list[tuple[int, int]]:
        p = phrase.lower().replace("-", " ")
        hits = []
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", self.s):
            if not any(self.used[m.start():m.end()]):
                hits.append((m.start(), m.end()))
        return hits

    def take(self, span: tuple[int, int]) -> None:
        for i in range(*span):
            self.used[i] = True

    def next_words(self, end: int, n: int = 2) -> list[str]:
        return self.s[end:].split()[:n]

    def leftover(self) -> str:
        chars = [c if not u else " " for c, u in zip(self.s, self.used)]
        words = [w for w in "".join(chars).split() if w not in STOP and len(w) > 1]
        return " ".join(words)


def _breed_aliases(species: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    seen: dict[str, int] = {}
    for b in all_breeds(species):
        if b["id"] == "mixed":
            continue
        names = {b["label"].lower(), b["id"].replace("_", " ")}
        for w in re.findall(r"[a-z]+", b["label"].lower()):
            if len(w) >= 3 and w not in BREED_GENERIC:
                names.add(w)
                seen[w] = seen.get(w, 0) + 1
        out.extend((n, b) for n in names)
    by_id = {b["id"]: b for b in all_breeds(species)}
    out.extend((nick, by_id[bid]) for nick, bid in NICKNAMES.get(species, {}).items() if bid in by_id)
    # Single words shared by several breeds (e.g. "corgi") resolve to the first listed breed.
    out.sort(key=lambda t: -len(t[0]))
    return out


def _colour_lookup() -> list[tuple[str, str]]:
    pairs = [(syn, name) for name, e in vocab()["palette"].items() for syn in e["synonyms"]]
    return sorted(pairs, key=lambda t: -len(t[0]))


def _eye_lookup() -> list[tuple[str, str]]:
    pairs = [(syn, name) for name, e in vocab()["eye_palette"].items() for syn in e["synonyms"]]
    return sorted(pairs, key=lambda t: -len(t[0]))


def parse(text: str, species: str, current_spec: dict[str, Any] | None = None,
          tapped_fields: list[str] | None = None) -> ParseResult:
    t0 = time.perf_counter()
    v = vocab()
    tapped = set(tapped_fields or [])
    res = ParseResult()
    if not text.strip():
        return res
    t = _Text(text)
    flat: dict[str, Any] = {}

    if any(t.find(word) for word in v["blocklist"]):
        res.blocked = True
        for word in v["blocklist"]:
            for span in t.find(word):
                t.take(span)

    # 1. Breed names. A newly named breed brings its preset first (merge order: preset, taps, text).
    for alias, b in _breed_aliases(species):
        hits = t.find(alias)
        if hits:
            if not current_spec or current_spec.get("breed", {}).get("id") != b["id"]:
                flat.update(flatten(b["preset"]))
            flat["breed.id"] = b["id"]
            flat["breed.label"] = b["label"]
            flat["breed.confidence"] = 0.9
            for h in hits:
                t.take(h)
            break
    for syn in v["slots"]["species"][species]["synonyms"] + ["dog", "cat"]:
        for span in t.find(syn):
            t.take(span)

    # 2. Accessories with an optional colour word in front ("red collar").
    acc_list: list[dict[str, Any]] = []
    colours = _colour_lookup()
    for value, e in v["slots"]["accessories.type"].items():
        for syn in sorted(e["synonyms"], key=len, reverse=True):
            for span in t.find(syn):
                t.take(span)
                acc: dict[str, Any] = {"type": value, "colour_hex": "#D33F3F", "colour_name": "red"}
                before = t.s[: span[0]].split()[-2:]
                for csyn, cname in colours:
                    if " ".join(before).endswith(csyn):
                        acc["colour_hex"] = v["palette"][cname]["hex"]
                        acc["colour_name"] = cname
                        idx = t.s.rfind(csyn, 0, span[0])
                        t.take((idx, idx + len(csyn)))
                        break
                if value == "collar":
                    acc["tag"] = True
                if all(a["type"] != value for a in acc_list):
                    acc_list.append(acc)
    if acc_list:
        flat["accessories"] = acc_list

    # 3. Every enumerated slot by synonym, longest phrases first (markings before plain colours).
    candidates: list[tuple[str, str, Any]] = []
    for slot, values in v["slots"].items():
        if slot in ("species", "accessories.type", "accessories.tag", "body.pose"):
            continue
        for value, e in values.items():
            for syn in e["synonyms"]:
                candidates.append((syn, slot, value))
    candidates.sort(key=lambda c: -len(c[0]))
    markings: list[str] = []
    for syn, slot, value in candidates:
        hits = t.find(syn)
        if not hits:
            continue
        if slot.startswith("eyes.colour") or slot == "nose.colour":
            pass
        for h in hits:
            t.take(h)
        typed: Any = {"true": True, "false": False}.get(value, value)
        if slot == "colour.markings":
            if typed not in markings:
                markings.append(typed)
            continue
        if slot == "eyes.colour":
            flat["eyes.colour"] = typed
            flat["eyes.hex"] = v["eye_palette"][typed]["hex"]
            continue
        flat[slot] = typed
    if markings:
        flat["colour.markings"] = markings

    # 4. Colour words: "<colour> eyes" -> eyes, "<colour> nose" handled above, else coat base then secondary.
    eye_words = _eye_lookup()
    coat: list[str] = []
    for syn, name in colours + [(s, "__eye__" + n) for s, n in eye_words]:
        for span in t.find(syn):
            nxt = t.next_words(span[1], 2)
            if name.startswith("__eye__"):
                if any(w.startswith("eye") for w in nxt):
                    eye = name[len("__eye__"):]
                    flat["eyes.colour"] = eye
                    flat["eyes.hex"] = v["eye_palette"][eye]["hex"]
                    t.take(span)
                continue
            if any(w.startswith("eye") for w in nxt):
                continue
            t.take(span)
            coat.append((span[0], name))  # type: ignore[arg-type]
    coat_names = [n for _, n in sorted(coat)]  # type: ignore[misc]
    if coat_names:
        flat["colour.base"] = {"name": coat_names[0], "hex": v["palette"][coat_names[0]]["hex"]}
        second = next((n for n in coat_names[1:] if n != coat_names[0]), None)
        if second:
            flat["colour.secondary"] = {"name": second, "hex": v["palette"][second]["hex"]}
            flat.setdefault("colour.pattern", "bicolour")

    # 5. Personality: known trait words plus "loves <x>" phrases, max 4.
    personality: list[str] = []
    for m in re.finditer(r"\bloves? ([a-z]+(?: [a-z]+)?)", t.s):
        phrase = "loves " + " ".join(w for w in m.group(1).split() if w not in STOP)[:24]
        if phrase.strip() != "loves" and phrase not in personality:
            personality.append(phrase.strip())
            t.take((m.start(), m.end()))
    for word in v["personality_words"]:
        if word.startswith("loves"):
            continue
        for span in t.find(word):
            t.take(span)
            if word not in personality:
                personality.append(word)
    personality = personality[:4]
    if personality:
        flat["personality"] = personality

    # 6. Drop anything the user tapped; tapped always wins.
    flat = {k: val for k, val in flat.items() if not is_tapped(k, tapped)}
    patch: dict[str, Any] = {}
    for k, val in flat.items():
        set_path(patch, k, val)
    res.patch = patch
    res.personality = personality
    res.free_text_unmapped = t.leftover()[:300]
    if current_spec is not None:
        _, res.changed_fields = apply_patch(current_spec, patch, tapped)
    else:
        res.changed_fields = sorted(flat)
    res.ms = int((time.perf_counter() - t0) * 1000)
    return res
