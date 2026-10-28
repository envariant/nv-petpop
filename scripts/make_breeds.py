#!/usr/bin/env python3
"""Generate data/breeds/{dog,cat}.json from the compact tables below.

Each row: id | label | size build legs | muzzle_len muzzle_w brachy | ear shape size tip |
tail type length curl | coat length texture fluff | base secondary pattern markings | eyes nose | prompt_hint
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / "data/schema/vocab.json").read_text())
PALETTE = VOCAB["palette"]
EYES = VOCAB["eye_palette"]

DOGS = """
corgi_pembroke|Pembroke Welsh Corgi|small stocky short|medium medium n|erect large rounded|bob short none|short smooth 0.3|red white saddle_with_white_chest white_blaze,white_socks,white_chest|brown black|Long low body on very short legs, large erect triangular ears, fox-like face.
corgi_cardigan|Cardigan Welsh Corgi|small stocky short|medium medium n|erect large rounded|plume long none|short smooth 0.35|blue_grey white merle white_chest,white_socks|brown black|Long low body with a full brushy tail, big rounded upright ears and a fox-like head.
labrador|Labrador Retriever|large standard medium|medium wide n|drop medium rounded|straight medium none|short smooth 0.2|gold - solid -|brown black|Broad friendly head with soft drop ears and an otter-like tail. Solid sturdy athletic build.
golden_retriever|Golden Retriever|large standard medium|medium medium n|drop medium rounded|plume long none|long silky 0.6|gold - solid -|brown black|Feathered golden coat with a gentle face and soft drop ears. Plumed tail and kind dark eyes.
german_shepherd|German Shepherd|large standard long|long medium n|erect large pointed|plume long none|medium smooth 0.4|tan black saddle_with_white_chest dark_mask|brown black|Large erect pointed ears and a long wedge-shaped muzzle. Black saddle over a tan coat with a bushy tail.
french_bulldog|French Bulldog|small stocky short|short wide y|erect large rounded|bob short none|short smooth 0.1|fawn - solid dark_mask|brown black|Large rounded bat ears on a square flat-faced head. Compact muscular body with a stub tail.
bulldog|English Bulldog|medium stocky short|short wide y|rose small rounded|bob short none|short smooth 0.1|white fawn bicolour -|brown black|Wide wrinkled flat face with a pushed-in nose and small rose ears. Very broad low stocky body.
poodle_standard|Standard Poodle|large slim long|long narrow n|drop medium rounded|straight medium none|medium curly 0.7|white - solid -|brown black|Tight curly coat with a topknot and long elegant muzzle. Long drop ears and proud upright stance.
poodle_toy|Toy Poodle|tiny slim medium|medium narrow n|drop medium rounded|straight short none|medium curly 0.8|cream - solid -|brown black|Tiny dog with a cloud of tight curls and long fluffy drop ears. Fine muzzle and bright eyes.
beagle|Beagle|small standard medium|medium medium n|drop large rounded|straight medium none|short smooth 0.2|tan white tricolour white_blaze,white_chest,white_socks|brown black|Classic tricolour hound with long soft drop ears and a white-tipped upright tail.
dachshund|Dachshund|small slim short|long narrow n|drop large rounded|straight long none|short smooth 0.1|red - solid -|brown black|Very long low sausage body on tiny legs with a long muzzle and long drop ears.
pug|Pug|small stocky short|short wide y|rose small rounded|curled short tight|short smooth 0.1|fawn black solid dark_mask|brown black|Round wrinkly flat face with a black mask and big round eyes. Tightly curled tail over the back.
shih_tzu|Shih Tzu|tiny standard short|short wide y|drop medium rounded|plume medium slight|long silky 0.8|white gold bicolour white_blaze|brown black|Long flowing silky coat and a flat sweet face with a topknot. Plumed tail curled over the back.
yorkshire_terrier|Yorkshire Terrier|tiny slim short|medium narrow n|erect small pointed|straight short none|long silky 0.6|blue_grey tan saddle_with_white_chest -|brown black|Tiny terrier with a long silky steel-blue and tan coat. Small erect V-shaped ears.
chihuahua|Chihuahua|tiny slim medium|short narrow n|erect large pointed|curled medium slight|short smooth 0.1|fawn - solid -|brown black|Apple-domed head with huge erect ears and big round eyes on a tiny body.
pomeranian|Pomeranian|tiny stocky short|short medium n|erect small pointed|plume medium tight|long fluffy 1.0|ginger - solid -|brown black|A round ball of fluff with a fox-like face and tiny erect ears. Plumed tail fanned over the back.
husky|Siberian Husky|large standard medium|medium medium n|erect medium pointed|plume long slight|medium fluffy 0.6|grey white bicolour white_chest,white_socks|blue black|Wolf-like face mask with striking blue eyes and erect triangular ears. Thick fluffy sickle tail.
malamute|Alaskan Malamute|large stocky medium|medium wide n|erect small pointed|plume long tight|long fluffy 0.8|grey white bicolour white_chest,dark_mask|brown black|Powerful heavy-boned sled dog with a cap and mask pattern. Plumed tail curled over the back.
samoyed|Samoyed|large standard medium|medium medium n|erect small rounded|plume long tight|long fluffy 1.0|white - solid -|brown black|Snow-white fluffy cloud of a coat with a smiling face. Small erect ears and plumed curled tail.
shiba_inu|Shiba Inu|small standard medium|medium medium n|erect small pointed|curled medium tight|short smooth 0.4|red cream bicolour white_chest|brown black|Fox-like face with small triangular ears and cream cheeks. Thick tail tightly curled over the back.
akita|Akita|large stocky medium|medium wide n|erect small pointed|curled long tight|medium fluffy 0.5|red white bicolour white_chest|brown black|Bear-like broad head with small erect ears and deep-set eyes. Big plush tail curled over the back.
border_collie|Border Collie|medium slim medium|medium narrow n|semi_erect medium rounded|plume long none|medium silky 0.5|black white bicolour white_blaze,white_chest,white_socks|brown black|Alert intelligent face with semi-erect tipped ears and a white blaze. Black and white feathered coat.
australian_shepherd|Australian Shepherd|medium standard medium|medium medium n|semi_erect medium rounded|bob short none|medium silky 0.5|blue_grey white merle white_blaze,white_chest|blue black|Marbled blue merle coat with copper points and a white blaze. Tipped ears and a bobbed tail.
sheltie|Shetland Sheepdog|small slim medium|long narrow n|semi_erect small pointed|plume long none|long fluffy 0.8|gold white sable white_chest,white_socks|brown black|Miniature collie with a long refined wedge head and a big white ruff. Tipped ears and plumed tail.
rough_collie|Rough Collie|large slim long|long narrow n|semi_erect small pointed|plume long none|long fluffy 0.8|gold white sable white_chest,white_blaze|brown black|Long elegant wedge-shaped head and a magnificent white mane. Tipped ears and long plumed tail.
boxer|Boxer|large standard long|short wide y|drop medium rounded|bob short none|short smooth 0.1|fawn white bicolour white_chest,dark_mask|brown black|Square short muzzle with a black mask and an underbite smile. Lean muscular body with a short tail.
rottweiler|Rottweiler|large stocky medium|medium wide n|drop small rounded|bob short none|short smooth 0.1|black tan bicolour points|brown black|Broad powerful black dog with rust markings on the cheeks, chest and legs. Small drop ears.
doberman|Dobermann|large slim long|long narrow n|erect large pointed|bob short none|short smooth 0.1|black tan bicolour points|brown black|Sleek elegant black and rust dog with a long muzzle and tall erect ears.
great_dane|Great Dane|large slim long|long medium n|drop medium rounded|straight long none|short smooth 0.1|black white spotted -|brown black|Giant gentle dog with a long rectangular head and drop ears. Harlequin black and white patches.
dalmatian|Dalmatian|large slim long|medium medium n|drop medium rounded|straight long none|short smooth 0.1|white black spotted -|brown black|White coat covered in round black spots. Gentle face with soft drop ears and a long tail.
cocker_spaniel|English Cocker Spaniel|medium standard medium|medium medium n|drop large rounded|bob short none|medium silky 0.6|gold - solid -|brown black|Long silky feathered ears and a soft domed head. Merry face with a bobbed tail.
cavalier|Cavalier King Charles Spaniel|small standard short|short medium n|drop large rounded|plume medium none|long silky 0.6|red white bicolour white_blaze,white_chest|brown black|Big dark round eyes and long feathered ears. Chestnut and white silky coat.
springer_spaniel|English Springer Spaniel|medium standard medium|medium medium n|drop large rounded|bob short none|medium silky 0.5|chocolate white bicolour white_blaze,white_chest|brown liver|Liver and white spaniel with long wavy ears and a friendly face.
bichon_frise|Bichon Frise|tiny standard short|short medium n|drop small rounded|plume medium tight|long curly 1.0|white - solid -|brown black|A powder puff of white curls with a round head and dark eyes. Plumed tail over the back.
maltese|Maltese|tiny slim short|short narrow n|drop medium rounded|plume medium slight|long silky 0.8|white - solid -|brown black|Tiny dog with a floor-length pure white silky coat and dark button eyes.
havanese|Havanese|tiny standard short|short medium n|drop medium rounded|plume medium tight|long silky 0.8|cream - solid -|brown black|Small sturdy dog with a long silky wavy coat and a cheerful face.
schnauzer_mini|Miniature Schnauzer|small standard medium|medium medium n|semi_erect small pointed|bob short none|medium wiry 0.4|grey silver bicolour -|brown black|Rectangular bearded face with bushy eyebrows and a moustache. Salt-and-pepper wiry coat.
west_highland|West Highland White Terrier|small stocky short|short medium n|erect small pointed|straight short none|medium wiry 0.6|white - solid -|brown black|White wiry-coated terrier with a round chrysanthemum face and small pointed ears.
scottish_terrier|Scottish Terrier|small stocky short|long medium n|erect small pointed|straight short none|medium wiry 0.4|black - solid -|brown black|Low sturdy black terrier with a long bearded head and erect pointed ears.
jack_russell|Jack Russell Terrier|small slim medium|medium medium n|semi_erect small pointed|straight short none|short smooth 0.2|white tan bicolour -|brown black|Small white terrier with tan patches on the head. Folded button ears and a lively face.
staffy|Staffordshire Bull Terrier|medium stocky medium|short wide n|rose small rounded|straight medium none|short smooth 0.1|grey white bicolour white_chest|brown black|Broad muscular head with strong cheeks and a wide smile. Small rose ears and a stocky body.
pitbull|American Pit Bull Terrier|medium stocky medium|medium wide n|rose small rounded|straight medium none|short smooth 0.1|blue_grey white bicolour white_chest|brown grey|Wide wedge-shaped head with a big grin and small rose ears. Muscular compact body.
bull_terrier|Bull Terrier|medium stocky medium|long medium n|erect medium pointed|straight medium none|short smooth 0.1|white - solid -|brown black|Distinctive egg-shaped head with small triangular eyes and erect ears.
basset_hound|Basset Hound|medium stocky short|long wide n|drop large rounded|straight long none|short smooth 0.1|tan white tricolour white_blaze,white_chest,white_socks|brown black|Very long velvety ears and droopy eyes on a long low heavy body.
bloodhound|Bloodhound|large standard long|long wide n|drop large rounded|straight long none|short smooth 0.1|red - solid -|brown black|Long wrinkled droopy face with extremely long ears and sad eyes.
greyhound|Greyhound|large slim long|long narrow n|rose small pointed|long_thin long none|short smooth 0.1|grey - solid -|brown black|Lean aerodynamic sighthound with a long narrow head and small folded rose ears.
whippet|Whippet|medium slim long|long narrow n|rose small pointed|long_thin long none|short smooth 0.1|fawn white bicolour white_chest|brown black|Slender graceful sighthound with a narrow head, rose ears and long thin tail.
italian_greyhound|Italian Greyhound|tiny slim long|long narrow n|rose small pointed|long_thin long none|short smooth 0.1|grey white bicolour white_chest|brown grey|Tiny delicate sighthound with a fine long muzzle and folded rose ears.
bernese|Bernese Mountain Dog|large stocky medium|medium wide n|drop medium rounded|plume long none|long silky 0.7|black tan tricolour white_blaze,white_chest|brown black|Big tricolour mountain dog with a white blaze and chest. Soft drop ears and a bushy tail.
saint_bernard|Saint Bernard|large stocky medium|short wide n|drop medium rounded|plume long none|medium smooth 0.5|red white bicolour white_blaze,white_chest,dark_mask|brown black|Giant gentle dog with a massive head, dark mask and white blaze.
newfoundland|Newfoundland|large stocky medium|medium wide n|drop small rounded|plume long none|long fluffy 0.8|black - solid -|brown black|Huge fluffy black bear of a dog with a broad head and small drop ears.
cane_corso|Cane Corso|large stocky long|short wide n|drop small rounded|straight medium none|short smooth 0.1|grey - solid -|brown grey|Large muscular mastiff with a broad square head and short muzzle.
boston_terrier|Boston Terrier|small standard medium|short wide y|erect large pointed|bob short none|short smooth 0.1|black white tuxedo white_blaze,white_chest|brown black|Tuxedo-coated small dog with a square flat face, big round eyes and large erect ears.
pekingese|Pekingese|tiny stocky short|short wide y|drop medium rounded|plume medium tight|long fluffy 0.9|gold - solid dark_mask|brown black|Lion-like mane with a flat face and dark mask. Long feathered ears.
lhasa_apso|Lhasa Apso|small standard short|short medium n|drop medium rounded|plume medium tight|long silky 0.8|gold - solid -|brown black|Long heavy straight coat that parts down the back. Small face and plumed tail over the back.
papillon|Papillon|tiny slim medium|medium narrow n|erect large pointed|plume long tight|long silky 0.6|white red bicolour white_blaze|brown black|Tiny dog with large fringed butterfly ears and a white blaze.
weimaraner|Weimaraner|large slim long|long medium n|drop large rounded|bob short none|short smooth 0.1|silver - solid -|amber grey|Sleek silver-grey dog with light amber eyes and long drop ears.
vizsla|Vizsla|large slim long|long medium n|drop large rounded|straight long none|short smooth 0.1|red - solid -|amber brown|Lean golden-rust pointer with long silky drop ears and a red nose.
bernedoodle|Bernedoodle|large standard medium|medium medium n|drop medium rounded|plume long none|long curly 0.8|black tan tricolour white_blaze,white_chest|brown black|Big curly tricolour doodle with a teddy-bear face and soft drop ears.
labradoodle|Labradoodle|large standard medium|medium medium n|drop medium rounded|plume long none|long curly 0.8|cream - solid -|brown black|Shaggy curly teddy-bear coat with a friendly face and soft drop ears.
cockapoo|Cockapoo|small standard medium|medium medium n|drop large rounded|plume medium none|long curly 0.8|gold - solid -|brown black|Small curly-coated doodle with long fluffy ears and a sweet round face.
"""

CATS = """
domestic_shorthair|Domestic Shorthair|medium standard medium|medium medium n|erect medium pointed|long_thin long none|short smooth 0.2|grey white tabby white_chest|green pink|Everyday house cat with a rounded head and upright pointed ears. Striped tabby coat.
domestic_longhair|Domestic Longhair|medium standard medium|medium medium n|erect medium pointed|plume long none|long fluffy 0.7|ginger white bicolour white_chest|amber pink|Fluffy long-haired house cat with a full ruff and plumed tail.
tabby_orange|Orange Tabby|medium stocky medium|medium medium n|erect medium pointed|long_thin long none|short smooth 0.2|ginger cream tabby -|amber pink|Classic ginger tabby with bold swirling stripes and an M on the forehead.
tuxedo|Tuxedo Cat|medium standard medium|medium medium n|erect medium pointed|long_thin long none|short smooth 0.2|black white tuxedo white_chest,white_socks|green pink|Black cat with a white bib and white socks like a dinner suit.
calico|Calico Cat|medium standard medium|medium medium n|erect medium pointed|long_thin long none|short smooth 0.2|white ginger calico -|green pink|White cat with bold patches of ginger and black.
tortoiseshell|Tortoiseshell|medium standard medium|medium medium n|erect medium pointed|long_thin long none|short smooth 0.2|black ginger calico -|amber black|Mottled brindled coat of black and ginger woven together.
siamese|Siamese|medium slim long|long narrow n|erect large pointed|long_thin long none|short smooth 0.1|cream chocolate colourpoint points|blue pink|Slender cat with a long wedge head and very large ears. Cream body with dark points and blue eyes.
persian|Persian|medium stocky short|short wide y|erect small rounded|plume medium none|long fluffy 1.0|white - solid -|copper pink|Very flat round face with tiny ears and a huge flowing coat.
maine_coon|Maine Coon|large stocky long|medium wide n|erect large pointed|plume long none|long fluffy 0.9|tan black tabby white_chest|amber black|Giant shaggy cat with lynx-tipped tufted ears, a ruff and a huge bushy tail.
ragdoll|Ragdoll|large standard medium|medium medium n|erect medium rounded|plume long none|long silky 0.8|cream grey colourpoint points,white_socks|blue pink|Large soft colourpoint cat with mitted white paws and deep blue eyes.
british_shorthair|British Shorthair|medium stocky short|short wide n|erect small rounded|straight medium none|short fluffy 0.5|blue_grey - solid -|copper grey|Round chubby cheeks on a round head with small ears. Dense plush blue-grey coat.
scottish_fold|Scottish Fold|medium stocky short|short wide n|folded small rounded|straight medium none|short fluffy 0.4|silver grey tabby -|amber pink|Round owl-like face with ears folded flat forward. Big round eyes.
bengal|Bengal|medium slim long|medium medium n|erect small rounded|straight medium none|short smooth 0.1|gold black spotted -|green black|Athletic wild-looking cat with leopard rosettes on a golden coat.
sphynx|Sphynx|medium slim long|medium medium n|erect large rounded|long_thin long none|short smooth 0.0|cream - solid -|green pink|Hairless wrinkled cat with huge bat-like ears and lemon-shaped eyes.
russian_blue|Russian Blue|medium slim medium|medium narrow n|erect large pointed|long_thin long none|short silky 0.3|blue_grey - solid -|green grey|Elegant silver-blue cat with vivid green eyes and a gentle smile.
abyssinian|Abyssinian|medium slim long|medium narrow n|erect large pointed|long_thin long none|short smooth 0.1|red tan solid -|amber pink|Slender ruddy ticked cat with large alert ears and almond eyes.
norwegian_forest|Norwegian Forest Cat|large stocky medium|medium medium n|erect large pointed|plume long none|long fluffy 1.0|silver white tabby white_chest|green pink|Big woolly cat with a thick mane, tufted ears and a bushy tail.
birman|Birman|medium standard medium|medium medium n|erect medium rounded|plume long none|long silky 0.7|cream chocolate colourpoint points,white_socks|blue pink|Silky colourpoint cat with pure white gloves on all four paws.
exotic_shorthair|Exotic Shorthair|medium stocky short|short wide y|erect small rounded|straight medium none|short fluffy 0.5|cream - solid -|copper pink|Teddy-bear-like flat-faced cat with plush short fur and tiny ears.
devon_rex|Devon Rex|small slim long|short narrow n|erect large rounded|long_thin long none|short curly 0.3|grey - solid -|amber pink|Pixie-like cat with enormous low-set ears and a wavy curly coat.
cornish_rex|Cornish Rex|small slim long|long narrow n|erect large rounded|long_thin long none|short curly 0.2|white chocolate bicolour -|amber pink|Greyhound-like curly-coated cat with tall ears and an egg-shaped head.
savannah|Savannah|large slim long|medium narrow n|erect large pointed|straight medium none|short smooth 0.1|gold black spotted -|amber black|Tall leggy spotted cat with very large upright ears.
himalayan|Himalayan|medium stocky short|short wide y|erect small rounded|plume medium none|long fluffy 1.0|cream chocolate colourpoint points|blue pink|Flat-faced long-haired cat with colourpoint markings and blue eyes.
turkish_angora|Turkish Angora|medium slim medium|medium narrow n|erect large pointed|plume long none|long silky 0.6|white - solid -|blue pink|Fine-boned white cat with a silky coat and a plumed tail.
manx|Manx|medium stocky short|medium medium n|erect medium rounded|bob short none|short fluffy 0.3|black - solid -|copper black|Round tailless cat with a rounded rump and round head.
"""

ACCENT_BY_SPECIES = {"dog": "#FF8A3D", "cat": "#7A5CFF"}
TUFTED = {"maine_coon", "norwegian_forest", "savannah"}


def colour(name: str) -> dict:
    return {"name": name, "hex": PALETTE[name]["hex"]}


def parse(table: str, species: str) -> list[dict]:
    out = []
    for line in table.strip().splitlines():
        (bid, label, body, head, ears, tail, coat, col, eyesnose, hint) = line.split("|")
        size, build, legs = body.split()
        mlen, mw, brachy = head.split()
        eshape, esize, etip = ears.split()
        ttype, tlen, tcurl = tail.split()
        clen, ctex, cfluff = coat.split()
        base, sec, pattern, marks = col.split()
        eyes, nose = eyesnose.split()
        preset = {
            "body": {"size": size, "build": build, "leg_length": legs, "pose": "sitting"},
            "head": {"muzzle_length": mlen, "muzzle_width": mw, "brachycephalic": brachy == "y"},
            "ears": {"shape": eshape, "size": esize, "tip": etip},
            "tail": {"type": ttype, "length": tlen, "curl": tcurl},
            "coat": {"length": clen, "texture": ctex, "fluffiness": float(cfluff)},
            "colour": {
                "base": colour(base),
                "pattern": pattern,
                "markings": [] if marks == "-" else marks.split(","),
            },
            "eyes": {"colour": eyes, "hex": EYES[eyes]["hex"], "heterochromia": False},
            "nose": {"colour": nose},
        }
        if species == "cat":
            preset["ears"]["tufted"] = bid in TUFTED
        if sec != "-":
            preset["colour"]["secondary"] = colour(sec)
        out.append({"id": bid, "species": species, "label": label, "prompt_hint": hint.strip(), "preset": preset})
    return out


def mixed(species: str) -> dict:
    base = parse(DOGS if species == "dog" else CATS, species)[0]
    rec = json.loads(json.dumps(base))
    rec.update(
        id="mixed",
        label="Mixed / not sure",
        prompt_hint=f"A friendly mixed-breed {species} with balanced, typical proportions.",
    )
    p = rec["preset"]
    p["body"] = {"size": "medium", "build": "standard", "leg_length": "medium", "pose": "sitting"}
    p["head"] = {"muzzle_length": "medium", "muzzle_width": "medium", "brachycephalic": False}
    p["colour"] = {"base": colour("tan"), "pattern": "solid", "markings": []}
    return rec


def main() -> None:
    for species, table in (("dog", DOGS), ("cat", CATS)):
        records = parse(table, species) + [mixed(species)]
        doc = {"species": species, "accent": ACCENT_BY_SPECIES[species], "breeds": records}
        path = ROOT / "data/breeds" / f"{species}.json"
        path.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"{path.relative_to(ROOT)}: {len(records)} breeds")


if __name__ == "__main__":
    main()
