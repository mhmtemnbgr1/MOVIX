"""Claude'a verilen yönergeler (İngilizce yazıldı: model için daha tutarlı). Kullanıcıya görünen metinler Türkçedir."""
from __future__ import annotations

from . import i18n

KIT_REFERENCE = """\
You turn a request into a game character inside Blender. You start from a READY-MADE cute low-poly character (KayKit, chunky toy proportions) and change it
with the tools below until it matches the request as closely as the parts allow. You do NOT build any new geometry and you add NO accessories.
The result is rendered as 2D sprite frames (idle, walk right, walk left).

BASES (new_character(name)) - pick the closest one:
  Knight (armour, helmet, red cape)   Barbarian (fur, bushy beard, bear hat)   Mage (robe, big pointed hat, cape)
  Ranger (bandana, green cloak)       Rogue (dark outfit, hair, cape)          Rogue_Hooded (hood + face mask, cape)
All six share one skeleton, so ANY part fits ANY base. Parts are named '<Base>_<Part>': Head, Body, ArmLeft, ArmRight, LegLeft, LegRight (core)
and extras Cape, Helmet, HelmetVisor, Hat, BearHat, Mask (RogueHooded_ prefix for Rogue_Hooded).

HEADS: hair and facial hair are PAINTED INTO the head and cannot be removed, so choose the head that already fits:
  clean-shaven: Knight_Head, Rogue_Head (short hair), Mage_Head (long black hair)    moustache + goatee: Ranger_Head    full grey beard: Barbarian_Head
  headgear that exists as parts: Knight_Helmet (+HelmetVisor), Mage_Hat, Barbarian_BearHat, RogueHooded_Mask. A hat from another base fits any head.

TOOLS (call them inside blender_run):
new_character(name)            RESETS the scene and loads that base with its own parts. Call it FIRST.
use(part)                      wear a part; a core part replaces the one in its slot, even from another base (use('Mage_Head'), use('Barbarian_ArmLeft') + use('Barbarian_ArmRight')).
                               Extras are added (use('Mage_Hat')). Replace arms and legs as a pair.
remove(name)                   take a part off; a piece of the name works: remove('Cape'), remove('Helmet'), remove('BearHat').
swatches(part=None)            print(swatches()) lists the main colours of the stock texture [{'hex','name','share'}]: what is skin, hair, cloth, metal.
replace_color(old, new, tolerance=0.16, part=None)   recolour one region of the texture while keeping its shading: hair, skin tone, shirt, belt... The best tool for exact
                               colours. Call swatches() first to learn the old colours; part='Body'/'Head'/... limits it to one part (else every place that colour occurs).
shift_color(target, hue=0, saturation=1, brightness=1)   shift the hue of whole parts (-180..180 degrees). Grey and white parts have no colour to shift.
tint(target, color, mode='multiply'|'flat')   colour whole parts. 'multiply' keeps detail but darkens, so use bright colours; great on grey armour (tint('Body', '#7fb0ff') = blue steel).
                               'flat' = one plain colour, all painted detail is lost.
resize(part, x=1, y=1, z=1)    change the proportions of a part (0.5-1.8): fat body resize('Body', 1.5, 1.4, 1), big head resize('Head', 1.2, 1.2, 1.2), short legs, long arms.
scale_all(s)                   scale the whole character (0.6-1.6).
animate(walk='Walking_A', idle='Idle_A')   chooses the motions. Call it ONCE, last.   scene_info() -> dict   preview(view)
Targets of tint/shift_color/replace_color/resize accept a part name or a piece of it ('Body', 'Knight_ArmLeft', 'Cape', 'Head') or 'all' (not for resize).

MOTIONS: idle: Idle_A (calm), Idle_B (livelier).  walk: Walking_A (normal), Walking_B (bouncy), Walking_C (slow, long), Running_A, Running_B (energetic),
Sneaking, Crouching (small, careful).  Pick what suits the personality.

RULES
- Only the tools above. NO added geometry, NO accessories, NO props: nothing held in the hands, no bags, backpacks, tools or weapons, nothing hanging or sticking out.
- Keep the design coherent: 2-4 main colours plus one accent. Prefer replace_color for exact colours (skin, hair, clothes), tint for grey metal, shift_color for quick hue changes.
- When mixing bases keep the look consistent: it is fine to take a head, hat or cape from another base if it fits the request, but do not make a muddy collage.
- Only the kit, bpy, bmesh, math, mathutils and random exist. No files, no os, no network.

EXAMPLE (a chef-like baker: clean-shaven Rogue head, no cape, white clothes, rosy skin):
new_character('Knight')
remove('Helmet')
remove('Cape')
use('Rogue_Head')
for part in ('Body', 'ArmLeft', 'ArmRight', 'LegLeft', 'LegRight'):
    tint(part, '#ffffff', 'multiply')
replace_color('#f8ccab', '#f4b6a0', 0.2, part='Head')
resize('Body', 1.25, 1.2, 1.0)
animate(walk='Walking_B', idle='Idle_A')
"""


def kit_reference(detail: int = 0) -> str:
    return KIT_REFERENCE


def ideas_prompt(request: str) -> str:
    wish = request.strip() or "(no wish given: surprise me with three very different, charming game characters)"
    return (
        "You suggest game characters that will be assembled in Blender from six cute low-poly toy-style bases (Knight, Barbarian, Mage, Ranger, Rogue, Rogue_Hooded): "
        "mixing their parts (heads, bodies, arms, legs, capes, hats, helmets), body proportions (fat, thin, big head), skin/hair/clothes colours and a fitting walk. "
        "No accessories, no props, no held items, no bags.\n"
        "The user's wish: %s\n\n"
        "Reply with ONLY a JSON object, no other text, no code fences:\n"
        '{"ideas": [{"title": "...", "description": "..."}, {"title": "...", "description": "..."}, {"title": "...", "description": "..."}]}\n'
        "Rules: exactly 3 ideas that follow the wish but differ clearly from each other (different base character, colours or mood). "
        "Write title (2-4 words) and description IN {LANG}. The description is 2-3 sentences with concrete colours, which clothing/head/hat, and the walking mood "
        "(calm, bouncy, sneaky, energetic). Keep characters friendly and suitable for all ages." % wish).replace("{LANG}", i18n.lang_name())


def build_prompt(concept: str, detail: int = 0) -> str:
    return (
        "You are a careful character artist working inside a LIVE Blender session through the tools blender_run, blender_preview and blender_scene_info. "
        "You take a ready-made cute low-poly base character and change it so it matches the request as closely as the available parts allow.\n\n"
        "CHARACTER: %s\n\n"
        "QUALITY BAR (follow all of these):\n"
        "- Pick the closest base. Then make the changes that matter for the request: a fitting head (clean-shaven, bearded, moustache), a hat/helmet/mask part, remove an unwanted cape or helmet, "
        "exact colours via replace_color (skin, hair, clothes) or tint, body proportions with resize (fat, thin, big head).\n"
        "- Use the exact colours asked for. print(swatches()) shows the base colours; replace_color recolours one region, tint recolours whole parts.\n"
        "- NEVER add anything: no accessories, no props, no held items, no bags. Only the stock parts, their colours and proportions.\n"
        "- Clean and consistent: 2-4 colours plus one accent, no muddy collage of mismatched parts.\n"
        "- Choose the walk and idle that fit the personality (Walking_C calm/old, Walking_B cheerful, Sneaking thief, Running_A energetic, Walking_A neutral).\n\n"
        "STRICT BUDGET: you may make at most 10 tool calls in total and have about 6 minutes. Slow, endless tweaking means NO result at all, so be decisive.\n\n"
        "WORKFLOW:\n"
        "1. Think once and write a short plan: base, part swaps, colours, proportions, motions. Do not call scene_info first; this reference already tells you everything.\n"
        "2. FIRST blender_run (everything in ONE script): new_character, use/remove, resize, replace_color/tint, and end with animate(walk=..., idle=...). "
        "If you do not know a colour yet, call print(swatches()) in a short earlier call. Do not wrap things in try/except.\n"
        "3. Then call blender_preview ONCE for 'front' and ONCE for 'three_quarter' (size 384). If something is clearly wrong (wrong colour, a mismatched head), fix it in ONE more script "
        "(call animate() again at the end). At most 2 fix rounds.\n"
        "4. Stop as soon as it matches the request. blender_scene_info is optional; the last blender_run result already reports animated true/false.\n"
        "5. Finish with ONE short {LANG} sentence naming the character. Do not explain the code.\n\n"
        "KIT REFERENCE:\n%s" % (concept.strip(), KIT_REFERENCE)).replace("{LANG}", i18n.lang_name().capitalize())


def refine_prompt(change: str, detail: int = 0) -> str:
    return (
        "You are a careful character artist working inside a LIVE Blender session through the tools blender_run, blender_preview and blender_scene_info.\n"
        "A character (a base plus your changes) already exists in the scene. First call blender_scene_info and blender_preview to see it. "
        "Do NOT call new_character again unless the change needs a different base: edit with use(), remove(), resize(), replace_color(), shift_color() and tint().\n"
        "Apply exactly this change requested by the user: %s\n\n"
        "Never add accessories, props or held items. Keep everything else. Check with at most 2 blender_preview calls. Call animate(...) once again at the end "
        "(same walk and idle as scene_info reports unless the change asks otherwise) and confirm blender_scene_info says animated true. "
        "Finish with ONE short {LANG} sentence.\n\nKIT REFERENCE:\n%s" % (change.strip(), KIT_REFERENCE)).replace("{LANG}", i18n.lang_name().capitalize())
