#!/usr/bin/env python3
from fontTools.ttLib import TTFont
from pathlib import Path
from collections import deque, defaultdict

import offsets           # triples (base, dx, dy)
import offsets_family    # 4-tuples (base, diacritic, dx, dy)

SKIP_CHARS = {" ", "\t", "\n", "\r"}

# ---------------------------
# cmap + GSUB helpers
# ---------------------------
def glyph_for_char(tt: TTFont, ch: str):
    if len(ch) != 1:
        raise SystemExit(f"ERROR: expected single character, got {ch!r}")
    uni = ord(ch)
    cmap = tt.getBestCmap()
    if cmap and uni in cmap:
        return cmap[uni]
    for st in tt["cmap"].tables:
        if st.isUnicode() and uni in st.cmap:
            return st.cmap[uni]
    return None

def gsub_targets(tt: TTFont, start_glyph: str, max_depth: int = 6):
    """Follow GSUB SingleSubst (1) + AlternateSubst (3) to include common variants (e.g. a.sc)."""
    out = {start_glyph}
    if "GSUB" not in tt:
        return out
    gsub = tt["GSUB"].table
    ll = getattr(gsub, "LookupList", None)
    if not ll:
        return out

    q = deque([(start_glyph, 0)])
    while q:
        g, d = q.popleft()
        if d >= max_depth:
            continue
        for lookup in ll.Lookup:
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

def expand_chars(s: str):
    """Iterate characters in a possibly multi-character base string, skipping whitespace."""
    if not isinstance(s, str) or not s:
        raise SystemExit(f"ERROR: base must be a non-empty string, got {s!r}")
    for ch in s:
        if ch in SKIP_CHARS:
            continue
        yield ch

def mark_candidates(tt: TTFont, mark_glyph: str):
    """Likely mark glyphs used in GPOS (handles uni030B vs hungarumlaut)."""
    go = set(tt.getGlyphOrder())
    cands = []

    def add(g):
        if g in go and g not in cands:
            cands.append(g)

    add(mark_glyph)

    # Special-case: combining double acute often appears as uni030B or hungarumlaut
    if mark_glyph == "uni030B":
        add("hungarumlaut")
    if mark_glyph == "hungarumlaut":
        add("uni030B")

    # Any dotted variants (uni030B.case, etc.)
    for g in tt.getGlyphOrder():
        if g.startswith(mark_glyph + "."):
            add(g)

    return cands

# ---------------------------
# Iterate GPOS subtables
# ---------------------------
def iter_gpos_lookups(tt: TTFont, lookup_type: int):
    gpos = tt["GPOS"].table
    ll = getattr(gpos, "LookupList", None)
    if not ll:
        return
    for li, lookup in enumerate(ll.Lookup):
        if lookup.LookupType != lookup_type:
            continue
        for si, st in enumerate(lookup.SubTable):
            yield li, si, st

# ---------------------------
# Patcher A: base-anchor shifts from offsets.py triples
# (base, dx, dy) -> shift ALL BaseAnchor/LigatureAnchor classes for that base glyph
# ---------------------------
def apply_base_anchor_shifts(tt: TTFont, triples, style_name: str):
    if not triples:
        return 0

    # accumulate per glyph (so repeated bases sum)
    base_delta = defaultdict(lambda: [0, 0])  # glyph -> [dx, dy]

    for base_str, dx, dy in triples:
        dx = int(dx); dy = int(dy)
        for ch in expand_chars(base_str):
            g = glyph_for_char(tt, ch)
            if not g:
                raise SystemExit(f"[{style_name}] ERROR: could not cmap-map base {ch!r} (U+{ord(ch):04X}).")
            base_delta[g][0] += dx
            base_delta[g][1] += dy

    base_delta = {g: (dx, dy) for g, (dx, dy) in base_delta.items() if dx or dy}
    if not base_delta:
        return 0

    edits = 0

    # MarkToBase (4): shift BaseAnchor for all classes
    for li, si, st in iter_gpos_lookups(tt, 4):
        if not all(hasattr(st, a) for a in ("BaseCoverage", "BaseArray")):
            continue
        base_cov = st.BaseCoverage.glyphs
        base_set = set(base_cov)

        for bg, (dx, dy) in base_delta.items():
            if bg not in base_set:
                continue
            b_idx = base_cov.index(bg)
            rec = st.BaseArray.BaseRecord[b_idx]
            for anchor in rec.BaseAnchor:
                if anchor is None:
                    continue
                anchor.XCoordinate += dx
                anchor.YCoordinate += dy
                edits += 1

    # MarkToLigature (5): shift LigatureAnchor for all classes, all components
    for li, si, st in iter_gpos_lookups(tt, 5):
        if not all(hasattr(st, a) for a in ("LigatureCoverage", "LigatureArray")):
            continue
        lig_cov = st.LigatureCoverage.glyphs
        lig_set = set(lig_cov)

        for bg, (dx, dy) in base_delta.items():
            if bg not in lig_set:
                continue
            l_idx = lig_cov.index(bg)
            attach = st.LigatureArray.LigatureAttach[l_idx]
            for comp in attach.ComponentRecord:
                for anchor in comp.LigatureAnchor:
                    if anchor is None:
                        continue
                    anchor.XCoordinate += dx
                    anchor.YCoordinate += dy
                    edits += 1

    return edits

# ---------------------------
# Patcher B: mark-to-base per (base, diacritic, dx, dy) from offsets_family.py
# -> shift ONLY the base anchor for the diacritic's mark class
# ---------------------------
def apply_mark_to_base_rules(tt: TTFont, rules, style_name: str):
    if not rules:
        return 0

    prepared = []
    for base_ch, diac_ch, dx, dy in rules:
        dx = int(dx); dy = int(dy)

        if len(base_ch) != 1:
            raise SystemExit(f"[{style_name}] ERROR: base in 4-tuple must be single char, got {base_ch!r}")
        if len(diac_ch) != 1:
            raise SystemExit(f"[{style_name}] ERROR: diacritic in 4-tuple must be single char, got {diac_ch!r}")

        base_g = glyph_for_char(tt, base_ch)
        mark_g = glyph_for_char(tt, diac_ch)
        if not base_g or not mark_g:
            raise SystemExit(f"[{style_name}] ERROR: could not cmap-map ({base_ch!r},{diac_ch!r}).")

        base_variants = gsub_targets(tt, base_g)
        mark_glyphs = mark_candidates(tt, mark_g)
        prepared.append((base_ch, diac_ch, base_variants, mark_glyphs, dx, dy))

    edits = 0

    for li, si, st in iter_gpos_lookups(tt, 4):  # MarkToBase only
        if not all(hasattr(st, a) for a in ("MarkCoverage", "BaseCoverage", "MarkArray", "BaseArray")):
            continue

        mark_cov = st.MarkCoverage.glyphs
        base_cov = st.BaseCoverage.glyphs
        mark_set = set(mark_cov)
        base_set = set(base_cov)

        for base_ch, diac_ch, base_variants, mark_glyphs, dx, dy in prepared:
            present_bases = [b for b in base_variants if b in base_set]
            if not present_bases:
                continue

            hit_mark = next((m for m in mark_glyphs if m in mark_set), None)
            if not hit_mark:
                continue

            m_idx = mark_cov.index(hit_mark)
            m_class = st.MarkArray.MarkRecord[m_idx].Class

            for bg in present_bases:
                b_idx = base_cov.index(bg)
                rec = st.BaseArray.BaseRecord[b_idx]
                if m_class >= len(rec.BaseAnchor):
                    continue
                anchor = rec.BaseAnchor[m_class]
                if anchor is None:
                    continue
                anchor.XCoordinate += dx
                anchor.YCoordinate += dy
                edits += 1

    return edits

# ---------------------------
# Style resolution
# ---------------------------
def resolve_style_paths(style_name: str):
    """
    Decide input/output filenames for a style.
    Preference order:
      1) offsets_family STYLES entry
      2) offsets STYLES entry
      3) derived from input by adding -patched
    """
    fam = offsets_family.STYLES.get(style_name, {})
    anch = offsets.STYLES.get(style_name, {})

    in_path = fam.get("in") or anch.get("in")
    if not in_path:
        return None, None

    out_path = fam.get("out") or anch.get("out")
    if not out_path:
        p = Path(in_path)
        out_path = str(p.with_stem(p.stem + "-patched"))
    return in_path, out_path

# ---------------------------
# Main
# ---------------------------
def main():
    # Use union of styles mentioned in either file
    style_names = sorted(set(offsets.STYLES.keys()) | set(offsets_family.STYLES.keys()))
    if not style_names:
        raise SystemExit("ERROR: No styles found in offsets.py or offsets_family.py")

    any_done = False

    for style in style_names:
        in_path, out_path = resolve_style_paths(style)
        if not in_path:
            continue

        if not Path(in_path).is_file():
            raise SystemExit(f"[{style}] ERROR: missing font file: {in_path}")

        tt = TTFont(in_path)
        if "GPOS" not in tt:
            raise SystemExit(f"[{style}] ERROR: no GPOS table in {in_path}")

        triples = offsets.STYLES.get(style, {}).get("offsets", [])
        rules4 = offsets_family.STYLES.get(style, {}).get("offsets", [])

        edits_a = apply_base_anchor_shifts(tt, triples, style)
        edits_b = apply_mark_to_base_rules(tt, rules4, style)

        total = edits_a + edits_b
        if total == 0:
            print(f"[{style}] no changes matched; skipping save.")
            continue

        tt.save(out_path)
        print(f"[{style}] ✓ wrote {out_path} (base-anchor edits={edits_a}, mark-to-base edits={edits_b}, total={total})")
        any_done = True

    if not any_done:
        raise SystemExit("No patched fonts produced (no edits matched any lookups).")

if __name__ == "__main__":
    main()
