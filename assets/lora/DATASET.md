# Runbook: petpop_style training images from a paid image model

This replaces step 1 of `README.md` (rendering the base meshes) as the source of the style. Renders of our own
meshes teach the LoRA the procedural look we are trying to leave. Nishant generates the images by hand in a
higher-quality image model and curates them. Claude Code writes the captions and the Kohya layout.

## 0. Before you start

- **Terms.** Check that the image service's terms let you use its outputs to train another model, and that
  you own the outputs for commercial use. Keep a note of the service, plan and date in `SOURCES.md` beside the set.
- **No brands.** Never put a toy brand, product line or company name in a prompt, and reject any image that
  copies a recognisable commercial product (box, logo, signature head shape). The style must be ours.
- **Size.** Square, at least 1024 x 1024, PNG or maximum-quality JPEG. Do not upscale small images.

## 1. Fix the look first (about 30 minutes)

1. Run the master prompt below for three or four breeds and iterate on its style block until one image is the
   look you want. This is the **anchor image**.
2. If the service supports a style reference (an image used to guide style, not content), attach the anchor
   to every later generation at a medium strength. This keeps 60 images consistent better than any wording.
3. Freeze the style block. From here on change only the breed block, the pose and the view.

## 2. Master prompt

Fill in the `[...]` parts; leave everything else word for word.

```text
A stylised vinyl collectible figurine of a [BREED], shown as a single toy on its own.
Breed details: [2-4 defining traits: ear shape, coat colours and markings, muzzle, tail].
Proportions: oversized rounded-square head roughly as wide as the body is tall, small compact body,
short sturdy legs, simplified sculpted fur rendered as a few smooth carved locks, not strands.
Face: solid glossy black button eyes set wide apart, small glossy black nose, small closed mouth,
optional simple sculpted brows. No pupils, no eyelashes, no open mouth.
Material: smooth matte vinyl with a soft satin sheen, flat clean colour regions with crisp edges
between markings, no fur texture, no painted gradients.
Pose: [sitting facing the camera | standing four-square], [VIEW].
Camera: eye level with the figure's chest, 85 mm product lens, whole figure in frame with margin
on every side, centred.
Lighting and background: soft even studio light, plain seamless pure white background,
only a faint soft contact shadow under the feet.
No text, no logo, no packaging, no box, no display base, no props, no second animal.
```

`[VIEW]` is one of:
- `front view, looking straight at the camera`
- `three-quarter view from the front left, head turned slightly towards the camera`
- `side view in profile facing left`
- `back view showing the back of the head, the back and the tail`

If the service has a separate negative prompt field, use:
`photorealistic, real fur strands, realistic eyes, plush toy, clay, text, logo, packaging, box, base, plinth,
multiple animals, cropped, dramatic lighting, dark background, coloured background, heavy shadow`

Breed details, three examples:
- Beagle: `long soft drop ears in tan, white muzzle and chest, white blaze up the forehead, tan and black saddle, white-tipped upright tail`
- Rottweiler: `black coat with rust-tan eyebrows, cheeks, chest and paws, short folded ears, broad square muzzle`
- Siberian Husky: `upright triangular ears, black or grey cap and back, white face mask with a widow's peak, curled bushy tail`

## 3. What to generate

The pipeline draws a front concept, then front, left, back and right views, so the LoRA must see every angle.
A front-only set gives a LoRA that cannot draw a back or a side.

| Group | Images | Contents |
| --- | --- | --- |
| Core | 60 | One per dog breed from the list below; 40 front and 20 three-quarter; mix sitting and standing |
| Angles | 20 | 10 breeds (varied ear and tail types) x side view and back view |
| Cats | 20 | Optional now, needed before cats ship: 20 cat breeds in the same style |

Generate 2 to 4 candidates per slot and keep the best one. Aim to keep about 80 to 100 images after curation;
60 is the usable minimum, as long as the angles group is in it.

Dog breeds (the kiosk's 61 presets): Pembroke Welsh Corgi, Cardigan Welsh Corgi, Labrador Retriever, Golden
Retriever, German Shepherd, French Bulldog, English Bulldog, Standard Poodle, Toy Poodle, Beagle, Dachshund, Pug,
Shih Tzu, Yorkshire Terrier, Chihuahua, Pomeranian, Siberian Husky, Alaskan Malamute, Samoyed, Shiba Inu, Akita,
Border Collie, Australian Shepherd, Shetland Sheepdog, Rough Collie, Boxer, Rottweiler, Dobermann, Great Dane,
Dalmatian, English Cocker Spaniel, Cavalier King Charles Spaniel, English Springer Spaniel, Bichon Frise, Maltese,
Havanese, Miniature Schnauzer, West Highland White Terrier, Scottish Terrier, Jack Russell Terrier, Staffordshire
Bull Terrier, American Pit Bull Terrier, Bull Terrier, Basset Hound, Bloodhound, Greyhound, Whippet, Italian
Greyhound, Bernese Mountain Dog, Saint Bernard, Newfoundland, Cane Corso, Boston Terrier, Pekingese, Lhasa Apso,
Papillon, Weimaraner, Vizsla, Bernedoodle, Labradoodle, Cockapoo.

Cover colour variety too: for breeds with several common coats (Labrador, Cocker Spaniel, Poodle, Dachshund,
Chihuahua, French Bulldog), use a different coat than you used for the other images.

## 4. Curate

Reject an image if any of these hold:
- the head shape, eye style, material or lighting drifts from the anchor;
- the background is not plain white or near white, or the shadow is more than a faint patch under the feet;
- any text, logo, base, box, prop, second animal, or cropped ear, tail or paw;
- anatomy errors: extra or merged legs, ears in the wrong place, two tails, melted paws;
- the breed is not recognisable at a glance, or the markings contradict the breed details;
- it is a near duplicate of an image you already kept (same breed, pose and view).

Then look at all the keepers side by side. They should read as one product line. If 10 % drift, regenerate them
rather than keeping them.

## 5. Name and hand over

Name each file `<breed>__<view>__<nn>.png` in lower case, with words joined by `-`:
`beagle__front__01.png`, `siberian-husky__back__01.png`, `maine-coon__three-quarter__01.png`.
Views: `front`, `three-quarter`, `side`, `back`.

Put the set in one folder with `SOURCES.md` (service, plan, date, master prompt as used). Do not commit the
images to git; copy the folder to the Mac at `~/petpop-genai/lora/raw/`, or upload it to the session.

## 6. What Claude Code does with it

1. Writes one caption per image: `petpop_style, ` followed by the content only (species, breed, coat colours
   and markings, pose, view, white background). The style is never described in words, so the trigger word
   carries it. Content comes from the file name plus a look at each image; you review the captions.
2. Lays the set out the way Kohya expects (`dataset/10_petpop_style/*.png` + `*.txt`; the 10 is repeats per
   epoch) and sets the epochs for the final count (about 1,000 to 1,500 steps in all).
3. Updates `kohya_petpop_style.toml` for where training runs. On a 24 GB NVIDIA card it is about an hour.
   On the M4 Pro it works but takes several hours, and needs a different config: no 8-bit optimiser on MPS.
4. Gate (`README.md` step 4): 10 held-out breeds, with and without the LoRA, same seeds, as one contact sheet
   for you to judge. The winning file is pinned with `scripts/models.py --pin` in `pipelines/comfy/models.yaml`
   and switched on in `config/genai/mac-m4pro.yaml` (`image.models.lora`).
