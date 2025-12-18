#!/usr/bin/env python3
from fontTools.ttLib import TTFont
from collections import defaultdict, deque
from pathlib import Path
import sys

import offsets_rules as cfg

SKIP_CHARS = {" ", "\t", "\n", "\r"}

# -----------------------------
# Unicode char -> glyph name
# -----------------------------
def glyph_for_char(ttfont: TTFont, ch: str):
    uni = ord(ch)
    cmap = ttfont.getBestCmap()
    if cmap and uni in cmap:
        return cmap[uni]
    for st in ttfont["cmap"].tables:
        if st.isUnicode() and uni in st.cmap:
            return st.cmap[uni]
    return None

# -----------------------------
# GSUB expansion (helps italics / alts)
# Covers SingleSubst (1) + AlternateSubst (3)
# -----------------------------
def gsub_targets(tt: TTFont, start_glyph: str, max_depth: int = 4):
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
            lt = lookup.LookupType
            for st in lookup.SubTable:
                if lt == 1:  # SingleSubst
                    m = getattr(st, "mapping", None)
                    if m and g in m:
                        tgt = m[g]
                        if tgt not in out:
                            out.add(tgt)
                            q.append((tgt, d + 1))

                elif lt == 3:  # AlternateSubst
                    cov = getattr(st, "Coverage", None)
                    altsets = getattr(st, "AlternateSet", None)
                    if not cov or not altsets:
                        continue
                    if g in cov.glyphs:
                        i = cov.glyphs.index(g)
                        for tgt in altsets[i].Alternate:
                            if tgt not in out:
                                out.add(tgt)
                                q.append((tgt, d + 1))

    return out

# -----------------------------
# Expand strings of chars in rules
# -----------------------------
def expand_chars(s: str):
    for ch in s:
        if ch in SKIP_CHARS:
            continue
        yield ch

# -----------------------------
# Iterate relevant GPOS subtables
# -----------------------------
def iter_gpos_mark_subtables(ttfont: TTFont):
    if "GPOS" not in ttfont:
        return
    gpos = ttfont["GPOS"].table
    if not getattr(gpos, "LookupList", None):
        return
    for lookup in gpos.LookupList.Lookup:
        if lookup.LookupType in (4, 5, 6):  # MarkToBase, MarkToLigature, MarkToMark
            for st in lookup.SubTable:
                yield lookup.LookupType, st

# -----------------------------
# Build rule-expanded glyph sets
# -----------------------------
def chars_to_glyphs(tt: TTFont, chars: str, expand_gsub: bool):
    """
    Convert a string of 1+ characters to a set of glyph names.
    If expand_gsub=True, include likely GSUB-substituted variants too.
    """
    out = set()
    for ch in expand_chars(chars):
        g = glyph_for_char(tt, ch)
        if not g:
            raise SystemExit(f"ERROR: Could not map '{ch}' (U+{ord(ch):04X}) via cmap.")
        if expand_gsub:
            out |= gsub_targets(tt, g)
        else:
            out.add(g)
    return out

# -----------------------------
# Patch engine
# -----------------------------
def patch_font(in_path: str, out_path: str, style_cfg: dict):
    tt = TTFont(in_path)
    if "GPOS" not in tt:
        raise SystemExit(f"ERROR: No GPOS table in {in_path}")

    # Prepare rules -> glyph sets (GSUB-expand bases, not marks by default)
    mark_to_base_rules = []
    for base_chars, mark_chars, dx, dy in style_cfg.get("mark_to_base", []):
        base_glyphs = chars_to_glyphs(tt, base_chars, expand_gsub=True)
        mark_glyphs = chars_to_glyphs(tt, mark_chars, expand_gsub=False)
        mark_to_base_rules.append((base_glyphs, mark_glyphs, int(dx), int(dy)))

    mark2_deltas = defaultdict(lambda: [0, 0])  # mark2 glyph -> [dx, dy]
    for mark2_chars, dx, dy in style_cfg.get("mark_to_mark_mark2", []):
        for g in chars_to_glyphs(tt, mark2_chars, expand_gsub=False):
            mark2_deltas[g][0] += int(dx)
            mark2_deltas[g][1] += int(dy)
    mark2_deltas = {g: tuple(v) for g, v in mark2_deltas.items() if v != [0, 0]}

    mark1_deltas = defaultdict(lambda: [0, 0])  # mark1 glyph -> [dx, dy]
    for mark1_chars, dx, dy in style_cfg.get("mark_to_mark_mark1", []):
        for g in chars_to_glyphs(tt, mark1_chars, expand_gsub=False):
            mark1_deltas[g][0] += int(dx)
            mark1_deltas[g][1] += int(dy)
    mark1_deltas = {g: tuple(v) for g, v in mark1_deltas.items() if v != [0, 0]}

    if not mark_to_base_rules and not mark2_deltas and not mark1_deltas:
        print(f"(No rules for {in_path}; skipping.)")
        return False

    print(f"\n== {Path(in_path).name}")
    if mark_to_base_rules:
        print(f"  mark_to_base rules: {len(mark_to_base_rules)}")
    if mark2_deltas:
        print(f"  mark_to_mark_mark2 glyphs: {len(mark2_deltas)}")
    if mark1_deltas:
        print(f"  mark_to_mark_mark1 glyphs: {len(mark1_deltas)}")

    changed = 0

    for ltype, st in iter_gpos_mark_subtables(tt):

        # -------------------------
        # LookupType 4: MarkToBase
        # -------------------------
        if ltype == 4 and mark_to_base_rules:
            if not all(hasattr(st, a) for a in ("MarkCoverage", "BaseCoverage", "MarkArray", "BaseArray")):
                continue

            mark_cov = st.MarkCoverage.glyphs
            base_cov = st.BaseCoverage.glyphs

            for base_glyphs, mark_glyphs, dx, dy in mark_to_base_rules:
                # For each mark in this rule that is present in this subtable, find its class
                for mg in (mark_glyphs & set(mark_cov)):
                    m_idx = mark_cov.index(mg)
                    m_class = st.MarkArray.MarkRecord[m_idx].Class

                    # For each base glyph in this rule present in this subtable, move only that class anchor
                    for bg in (base_glyphs & set(base_cov)):
                        b_idx = base_cov.index(bg)
                        b_rec = st.BaseArray.BaseRecord[b_idx]
                        if m_class >= len(b_rec.BaseAnchor):
                            continue
                        anchor = b_rec.BaseAnchor[m_class]
                        if anchor is None:
                            continue
                        anchor.XCoordinate += dx
                        anchor.YCoordinate += dy
                        changed += 1

        # -------------------------
        # LookupType 5: MarkToLigature
        # -------------------------
        elif ltype == 5 and mark_to_base_rules:
            if not all(hasattr(st, a) for a in ("MarkCoverage", "LigatureCoverage", "MarkArray", "LigatureArray")):
                continue

            mark_cov = st.MarkCoverage.glyphs
            lig_cov = st.LigatureCoverage.glyphs

            for base_glyphs, mark_glyphs, dx, dy in mark_to_base_rules:
                # Determine mark classes for marks present here
                present_marks = (mark_glyphs & set(mark_cov))
                if not present_marks:
                    continue

                mark_classes = []
                for mg in present_marks:
                    m_idx = mark_cov.index(mg)
                    mark_classes.append(st.MarkArray.MarkRecord[m_idx].Class)

                # For each ligature base present here, move anchors for those classes
                for bg in (base_glyphs & set(lig_cov)):
                    l_idx = lig_cov.index(bg)
                    lig_attach = st.LigatureArray.LigatureAttach[l_idx]
                    for comp in lig_attach.ComponentRecord:
                        for m_class in mark_classes:
                            if m_class >= len(comp.LigatureAnchor):
                                continue
                            anchor = comp.LigatureAnchor[m_class]
                            if anchor is None:
                                continue
                            anchor.XCoordinate += dx
                            anchor.YCoordinate += dy
                            changed += 1

        # -------------------------
        # LookupType 6: MarkToMark
        # -------------------------
        elif ltype == 6 and (mark2_deltas or mark1_deltas):
            # Need Mark1Coverage/Mark2Coverage and arrays
            if not all(hasattr(st, a) for a in ("Mark1Coverage", "Mark2Coverage", "Mark1Array", "Mark2Array")):
                continue

            mark1_cov = st.Mark1Coverage.glyphs
            mark2_cov = st.Mark2Coverage.glyphs

            # mark2: move Mark2Record.Mark2Anchor[class] for matching mark2 glyphs
            if mark2_deltas:
                for g, (dx, dy) in mark2_deltas.items():
                    if g not in mark2_cov:
                        continue
                    idx = mark2_cov.index(g)
                    rec = st.Mark2Array.Mark2Record[idx]
                    for anchor in rec.Mark2Anchor:
                        if anchor is None:
                            continue
                        anchor.XCoordinate += dx
                        anchor.YCoordinate += dy
                        changed += 1

            # mark1: move MarkRecord.MarkAnchor for matching mark1 glyphs
            if mark1_deltas:
                for g, (dx, dy) in mark1_deltas.items():
                    if g not in mark1_cov:
                        continue
                    idx = mark1_cov.index(g)
                    mrec = st.Mark1Array.MarkRecord[idx]
                    anchor = mrec.MarkAnchor
                    if anchor is None:
                        continue
                    anchor.XCoordinate += dx
                    anchor.YCoordinate += dy
                    changed += 1

    if changed == 0:
        raise SystemExit(
            f"ERROR: No anchors changed in {in_path}. "
            "Common causes: the base/mark isn’t covered by the relevant GPOS lookups, "
            "or the mark uses a different attachment class/lookup than expected."
        )

    tt.save(out_path)
    print(f"✓ wrote {out_path} ({changed} anchor edits)")
    return True

def main():
    any_done = False
    for style_name, s in cfg.STYLES.items():
        in_path = s["in"]
        if not Path(in_path).is_file():
            raise SystemExit(f"Missing font file for {style_name}: {in_path}")

        out_path = str(Path(in_path).with_stem(Path(in_path).stem + "-patched"))
        did = patch_font(in_path, out_path, s)
        any_done |= did

    if not any_done:
        raise SystemExit("No patched fonts produced (all styles skipped).")

if __name__ == "__main__":
    main()
