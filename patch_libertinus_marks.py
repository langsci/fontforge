#!/usr/bin/env python3
from fontTools.ttLib import TTFont
from collections import defaultdict
from pathlib import Path
import sys

import offsets  # ← configuration lives here

SKIP_CHARS = {" ", "\t", "\n", "\r"}

# -------------------------
# Helpers
# -------------------------
def glyph_for_char(ttfont: TTFont, ch: str):
    uni = ord(ch)
    cmap = ttfont.getBestCmap()
    if cmap and uni in cmap:
        return cmap[uni]
    for st in ttfont["cmap"].tables:
        if st.isUnicode() and uni in st.cmap:
            return st.cmap[uni]
    return None

def iter_mark_subtables(ttfont: TTFont):
    """Yield (lookupType, subtable) for MarkToBase (4) and MarkToLigature (5)."""
    if "GPOS" not in ttfont:
        return
    gpos = ttfont["GPOS"].table
    if not getattr(gpos, "LookupList", None):
        return
    for lookup in gpos.LookupList.Lookup:
        if lookup.LookupType in (4, 5):
            for st in lookup.SubTable:
                yield lookup.LookupType, st

def expand_letter_tuples(pairs):
    expanded = []
    for letters, off in pairs:
        if not isinstance(letters, str) or not letters:
            raise SystemExit(f"Invalid letters entry: {letters!r}")
        off = int(off)
        for ch in letters:
            if ch in SKIP_CHARS:
                continue
            expanded.append((ch, off))
    return expanded

def build_glyph_offset_map(tt, x_pairs, y_pairs):
    acc = defaultdict(lambda: [0, 0])  # glyph -> [dx, dy]

    for ch, dy in expand_letter_tuples(y_pairs):
        g = glyph_for_char(tt, ch)
        if not g:
            raise SystemExit(f"Cannot map '{ch}' (U+{ord(ch):04X}) via cmap.")
        acc[g][1] += dy

    for ch, dx in expand_letter_tuples(x_pairs):
        g = glyph_for_char(tt, ch)
        if not g:
            raise SystemExit(f"Cannot map '{ch}' (U+{ord(ch):04X}) via cmap.")
        acc[g][0] += dx

    return {g: tuple(v) for g, v in acc.items() if v != [0, 0]}

def patch_font(in_path, out_path, x_pairs, y_pairs):
    tt = TTFont(in_path)
    if "GPOS" not in tt:
        raise SystemExit(f"No GPOS table in {in_path}")

    glyph_deltas = build_glyph_offset_map(tt, x_pairs, y_pairs)
    if not glyph_deltas:
        print(f"(No offsets for {in_path}; skipping.)")
        return False

    print(f"\n== {Path(in_path).name}")
    for g, (dx, dy) in glyph_deltas.items():
        print(f"  {g}: dx={dx}, dy={dy}")

    changed = 0

    for ltype, st in iter_mark_subtables(tt):

        # --- LookupType 4: MarkToBase ---
        if ltype == 4:
            if not (hasattr(st, "BaseCoverage") and hasattr(st, "BaseArray")):
                continue
            base_glyphs = st.BaseCoverage.glyphs

            for g, (dx, dy) in glyph_deltas.items():
                if g not in base_glyphs:
                    continue
                rec = st.BaseArray.BaseRecord[base_glyphs.index(g)]
                for anchor in rec.BaseAnchor:
                    if anchor is None:
                        continue
                    anchor.XCoordinate += dx
                    anchor.YCoordinate += dy
                    changed += 1

    # --- LookupType 5: MarkToLigature ---
        elif ltype == 5:
            if not (hasattr(st, "LigatureCoverage") and hasattr(st, "LigatureArray")):
                continue
            lig_glyphs = st.LigatureCoverage.glyphs

            for g, (dx, dy) in glyph_deltas.items():
                if g not in lig_glyphs:
                    continue

                lig_index = lig_glyphs.index(g)
                lig_attach = st.LigatureArray.LigatureAttach[lig_index]

                # A ligature can have multiple components (æ often counts as one, but can be >1)
                for comp in lig_attach.ComponentRecord:
                    # Each component has anchors per mark class
                    for anchor in comp.LigatureAnchor:
                        if anchor is None:
                            continue
                        anchor.XCoordinate += dx
                        anchor.YCoordinate += dy
                        changed += 1

    if changed == 0:
        raise SystemExit(f"No anchors changed in {in_path}")

    tt.save(out_path)
    print(f"✓ wrote {out_path} ({changed} anchors changed)")
    return True

# -------------------------
# Main
# -------------------------
def main():
    any_done = False

    for style, cfg in offsets.STYLES.items():
        in_path = cfg["in"]
        out_path = str(Path(in_path).with_stem(Path(in_path).stem + "-patched"))

        if not Path(in_path).is_file():
            raise SystemExit(f"Missing font file: {in_path}")

        did = patch_font(
            in_path,
            out_path,
            cfg.get("x", []),
            cfg.get("y", []),
        )
        any_done |= did

    if not any_done:
        raise SystemExit("No patched fonts produced.")

if __name__ == "__main__":
    main()
