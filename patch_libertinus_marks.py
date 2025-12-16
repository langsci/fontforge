#!/usr/bin/env python3
from fontTools.ttLib import TTFont
from collections import defaultdict
from pathlib import Path
import offsets  # config file

from collections import defaultdict, deque
SKIP_CHARS = {" ", "\t", "\n", "\r"}

def glyph_for_char(ttfont: TTFont, ch: str):
    """Resolve a single Unicode character to a glyph name via cmap."""
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


def gsub_targets(tt: TTFont, start_glyph: str, max_depth: int = 4):
    """
    Return a set of glyphs reachable from start_glyph via GSUB substitutions.
    Covers:
      - LookupType 1 (SingleSubst)
      - LookupType 3 (AlternateSubst)
    Limited depth to avoid weird cycles.
    """
    out = set([start_glyph])
    if "GSUB" not in tt:
        return out

    gsub = tt["GSUB"].table
    if not getattr(gsub, "LookupList", None):
        return out

    q = deque([(start_glyph, 0)])
    while q:
        g, d = q.popleft()
        if d >= max_depth:
            continue

        for lookup in gsub.LookupList.Lookup:
            for st in lookup.SubTable:
                # SingleSubst
                if lookup.LookupType == 1:
                    m = getattr(st, "mapping", None)
                    if m and g in m:
                        tgt = m[g]
                        if tgt not in out:
                            out.add(tgt)
                            q.append((tgt, d + 1))

                # AlternateSubst
                elif lookup.LookupType == 3:
                    cov = getattr(st, "Coverage", None)
                    alts = getattr(st, "AlternateSet", None)
                    if not cov or not alts:
                        continue
                    if g in cov.glyphs:
                        i = cov.glyphs.index(g)
                        for tgt in alts[i].Alternate:
                            if tgt not in out:
                                out.add(tgt)
                                q.append((tgt, d + 1))

    return out

def build_glyph_delta_map_from_offsets(tt: TTFont, offsets_list):
    """
    offsets_list: [(letters, dx, dy), ...] where letters is 1+ chars.
    Applies dx/dy to each character, and ALSO to likely GSUB-substituted variants
    of the base glyph, so italics/locl/alts still move.
    """
    acc = defaultdict(lambda: [0, 0])  # glyph -> [dx, dy]

    for letters, dx, dy in offsets_list:
        if not isinstance(letters, str) or not letters:
            raise SystemExit(f"ERROR: letters must be a non-empty string, got {letters!r}")
        dx = int(dx); dy = int(dy)

        for ch in letters:
            if ch in SKIP_CHARS:
                continue
            base = glyph_for_char(tt, ch)
            if not base:
                raise SystemExit(f"ERROR: Could not map '{ch}' (U+{ord(ch):04X}) via cmap.")

            # Patch base glyph + GSUB-derived variants (without overwriting)
            for g in gsub_targets(tt, base):
                acc[g][0] += dx
                acc[g][1] += dy

    return {g: (dx, dy) for g, (dx, dy) in acc.items() if dx or dy}

def patch_font(in_path: str, out_path: str, offsets_list):
    tt = TTFont(in_path)
    if "GPOS" not in tt:
        raise SystemExit(f"ERROR: No GPOS table in {in_path}")

    glyph_deltas = build_glyph_delta_map_from_offsets(tt, offsets_list)
    if not glyph_deltas:
        print(f"(No offsets for {in_path}; skipping.)")
        return False

    print(f"\n== {Path(in_path).name}")
    print("Targets (glyph -> dx, dy):")
    for g, (dx, dy) in glyph_deltas.items():
        print(f"  {g}: dx={dx}, dy={dy}")

    changed = 0

    for ltype, st in iter_mark_subtables(tt):

        # LookupType 4: MarkToBase
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

        # LookupType 5: MarkToLigature
        elif ltype == 5:
            if not (hasattr(st, "LigatureCoverage") and hasattr(st, "LigatureArray")):
                continue
            lig_glyphs = st.LigatureCoverage.glyphs

            for g, (dx, dy) in glyph_deltas.items():
                if g not in lig_glyphs:
                    continue
                attach = st.LigatureArray.LigatureAttach[lig_glyphs.index(g)]
                for comp in attach.ComponentRecord:
                    for anchor in comp.LigatureAnchor:
                        if anchor is None:
                            continue
                        anchor.XCoordinate += dx
                        anchor.YCoordinate += dy
                        changed += 1

    if changed == 0:
        raise SystemExit(
            f"ERROR: No anchors changed in {in_path}. "
            "Possibly the target glyphs are not covered by MarkToBase/MarkToLigature in this font."
        )

    tt.save(out_path)
    print(f"✓ wrote {out_path} ({changed} anchors changed)")
    return True

def main():
    any_done = False

    for style_name, cfg in offsets.STYLES.items():
        in_path = cfg["in"]
        out_path = str(Path(in_path).with_stem(Path(in_path).stem + "-patched"))
        offs = cfg.get("offsets", [])

        if not Path(in_path).is_file():
            raise SystemExit(f"Missing font file for {style_name}: {in_path}")

        did = patch_font(in_path, out_path, offs)
        any_done |= did

    if not any_done:
        raise SystemExit("No patched fonts produced.")

if __name__ == "__main__":
    main()
