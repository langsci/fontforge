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
            # ("a", "̰" 100, 0),
        ],
    },

    "Italic": {
        "in":  "LibertinusSerif-Italic.otf",
        "out": "LibertinusSerif-Italic-patched.otf",
        "offsets": [
            # ("a", "̋", 30, 0),
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
            ("a", "̋", -130, 0),
            ("a", "̰", 100, 0),
        ],
    },
}
