"""What an order costs (decisions 126, 137): line items read from the composition with the price list in
config/pricing.json. The figurine (PETPOP_PRICE_SGD overrides its price), each extra by kind (a shell part's kind;
'*' prices kinds the list does not name, so a new kind of extra needs no code), and options: hand-painted spots, each
marking beyond the free ones, a torso shape other than the standard one, a pose not in the free list. Lines priced
0.00 are left out. The payment asks for the total; the kiosk shows the lines as the customer designs (POST /quote)."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import models as m

CONFIG = Path(__file__).resolve().parents[2] / "config" / "pricing.json"
ZERO = Decimal("0.00")


def _money(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


@lru_cache
def _load(path: str, mtime: float) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def price_list() -> dict[str, Any]:
    """config/pricing.json (PETPOP_PRICING overrides the path), re-read when it changes."""
    p = Path(os.environ.get("PETPOP_PRICING") or CONFIG)
    return _load(str(p), p.stat().st_mtime)


def base_price() -> Decimal:
    env = os.environ.get("PETPOP_PRICE_SGD")
    return _money(env) if env else _money(price_list()["figurine"]["price"])


def _words(x: str) -> str:
    return x.replace("_", " ").strip().capitalize()


def _shell_kinds(manifest: dict[str, Any] | None) -> dict[str, tuple[str, str]]:
    """shell part id -> (kind, name) from the release, when there is one."""
    return {s["id"]: (s.get("kind") or s["id"], s.get("name") or _words(s.get("kind") or s["id"])) for s in (manifest or {}).get("shell_parts") or []}


def lines(composition: dict[str, Any], manifest: dict[str, Any] | None = None) -> list[tuple[str, Decimal]]:
    """(label, amount) per line: the figurine first, then extras and options with a price."""
    pl = price_list()
    out: list[tuple[str, Decimal]] = [(pl["figurine"].get("label") or "Figurine", base_price())]
    kinds = _shell_kinds(manifest)
    extras = pl.get("extras") or {}
    for s in composition.get("shells") or []:
        kind, name = kinds.get(s["part_id"], (s["part_id"].removeprefix("shell_"), _words(s["part_id"].removeprefix("shell_"))))
        rule = extras.get(kind) or extras.get("*")
        if rule:
            out.append((rule.get("label") or name, _money(rule["price"])))
    kit = composition.get("composition_version") == "3.0"
    for opt in pl.get("options") or []:
        oid = opt["id"]
        if oid == "stamps" and composition.get("stamps"):
            out.append((opt["label"], _money(opt["price"])))
        elif oid == "markings_over":
            n = len((composition.get("texture") or {}).get("markings") or []) if kit else len(composition.get("layers") or [])
            extra = max(0, n - int(opt.get("free", 0)))
            if extra:
                out.append((f"{opt['label']} ({extra})", _money(opt["each"]) * extra))
        elif oid == "shape" and kit and composition.get("preset_id", "default") != "default":
            sid = composition["preset_id"]
            prices = opt.get("prices") or {}
            out.append((opt["label"].format(name=_words(sid)), _money(prices.get(sid, prices.get("*", 0)))))
        elif oid == "pose" and kit and composition.get("pose_id") not in (opt.get("free") or []):
            pid = composition["pose_id"]
            prices = opt.get("prices") or {}
            out.append((opt["label"].format(name=_words(pid)), _money(prices.get(pid, prices.get("*", 0)))))
    return [out[0]] + [(label, a) for label, a in out[1:] if a != ZERO]


def quote(composition: dict[str, Any], manifest: dict[str, Any] | None = None) -> m.Quote:
    items = lines(composition, manifest)
    total = sum((a for _, a in items), ZERO)
    return m.Quote(items=[m.QuoteItem(label=label, amount=f"{a:.2f}") for label, a in items],
                   total=m.Price(amount=f"{total:.2f}", currency=price_list().get("currency", "SGD")))
