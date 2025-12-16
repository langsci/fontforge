# offsets_rules.py
STYLES = {
    "Regular": {
        "in": "LibertinusSerif-Regular.otf",

        # Raise acute-on-Q in MarkToBase (lookup type 4)
        # (base_chars, mark_chars, dx, dy)
        "mark_to_base": [
            ("Q", "́", 0, +60),
        ],

        # Compensate by lowering the acute mark itself (lookup type 6 Mark1Array)
        # (mark1_chars, dx, dy)
        "mark_to_mark_mark1": [
            ("́", 0, -60),
        ],
    }
}
