# offsets_family.py
#
# Per-style structured offsets.
# Each rule is: (base_char, combining_mark_char, dx, dy)

STYLES = {
    "Regular": {
        "in":  "LibertinusSerif-Regular.otf",
        "out": "LibertinusSerif-Regular-patched.otf",
        "offsets": [
            # ("a", "̋", -130, 0),
            # no effect
            ("u", "̰", 120, 100),
            ("ʊ", "̆", 120, 100)
        ],
    },

    "Italic": {
        "in":  "LibertinusSerif-Italic.otf",
        "out": "LibertinusSerif-Italic-patched.otf",
        "offsets": [
            ("a", "̰", 50, -10),#tilde below
            ("ɘ", "̰", -80, 0),#tilde below
            # ("K", "̀", -80, 100),#grave
        ],
    },

    "Semibold": {
        "in":  "LibertinusSerif-Semibold.otf",
        "out": "LibertinusSerif-Semibold-patched.otf",
        "offsets": [
            # ("a", "̋", 30, 0),
        ],
    },

    "SemiboldItalic": {
        "in":  "LibertinusSerif-SemiboldItalic.otf",
        "out": "LibertinusSerif-SemiboldItalic-patched.otf",
        "offsets": [
            ("a", "̋", -130, 0),#hungarian umlaut
            ("a", "̰", 50, -10),#tilde below
            ("a", "̱", 50, 0),#bar below
            ("ʊ", "̰", 200, 0),#tilde below
            ("ɑ", "̰", 100, 0),#tilde below
            # does not work
            # ("ɐ", "́", -200, 500),#
            # ("ʌ", "́", -200, 500),#
            ("ɔ", "́", -200, 500),#
            # ("ø", "́", -200, 500),#
            # ("ɵ", "́", -200, 5100),#
            # ("ʉ", "́", -200, 500),#
            # ("ʏ", "́", -200, 500),#
            # ("ɤ", "́", -200, 500),#
            # ("ɶ", "̰", -1200, 0),#tilde below
            # ("ʊ", "̇", -200, 500),#
        ],
    },
}
