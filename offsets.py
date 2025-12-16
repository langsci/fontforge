# offsets.py
# =========================
# Offsets by CHARACTER(s)
# (letters, dx, dy)
# letters can be a string of 1+ characters; dx/dy apply to each character.
# dx < 0 = left, dy > 0 = up
# =========================

STYLES = {
    "Regular": {
        "in": "LibertinusSerif-Regular.otf",
        "offsets": [
            ("ɴ", 30, 10),
            ("æ", -10,  0),
            ("ɶ", 150,  0),
            ("ɵ", 50,  0),
            ("ʉ", 50,  0),
            ("ʊ", 50,  0),
            ("ʏ", 50,  0),
            # ("M",   0, 40),
        ],
    },

    "Italic": {
        "in": "LibertinusSerif-Italic.otf",
        "offsets": [
            # has effect in output
            ("ɘ", 140,  0),
            ("ɪ", 140,  0),
            ("ɯ", 120,  0),
            ("ɲ", 120,  0),
            ("ŋ", 120,  0),
            ("ɳ", 120,  0),
            ("ɱ", 120,  0),
            # testing
            #  ...
            #complex  issues
            # ("M", 0,  0), #  ` OK  ̂ breve too low and too right
            # ("N", 0,  0), ´~̄ and uncommon onesOK. ` ̂ breve too low and too right
            # has no  effect in output
            # ("ʉ", 1120,  0),
            # ("ʏ", 1120,  0),
            # ("ø", 1120,  0),
            # ("ɵ", 1120,  0),
            # ("ɤ", 1120,  0),
            # ("ʉ", 1120,  0),
            # ("ɐ", 1120,  0),
            # ("ɒ", 1120,  0),
            # ("ɑ", 1120,  0),
            # ("ɶ", 1120,  0),
            # ("ɔ", 1120,  0),
            # ("ʌ", 1120,  0),
            # ("ɞ", 1120,  0),
            # ("ɜ", 1120,  0),
            # ("ɛ", 1120,  0),
            # ("ɴ", -125,  100),
            # ("ə", 140,  0),
            # not needed
            # euœæamnAEIOUYnɯiyɨ
            # ("æ", 0,  0),
        ],
    },

    "Semibold": {
        "in": "LibertinusSerif-Semibold.otf",
        "offsets": [
            ("M", 0, 300),
        ],
    },

    "SemiboldItalic": {
        "in": "LibertinusSerif-SemiboldItalic.otf",
        "offsets": [
            ("M", 100, 0),
        ],
    },
}
