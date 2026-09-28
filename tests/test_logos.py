from yapaia.logos import LogoManager, _best_match


def test_best_match_prefers_exact_name_and_real_logo():
    candidates = [
        {"name": "SWR3 Elchradio", "favicon": "https://x/elch.png", "clickcount": 5000},
        {"name": "SWR3", "favicon": "https://x/favicon.ico", "clickcount": 10},
        {"name": "SWR 3", "favicon": "https://x/swr3.png", "clickcount": 900},
        {"name": "Radio Something", "favicon": "https://x/other.png", "clickcount": 99999},
    ]
    assert _best_match("swr3", candidates)["favicon"] == "https://x/swr3.png"


def test_best_match_rejects_unrelated():
    assert _best_match("dasding", [{"name": "Antenne Bayern", "favicon": "https://x/a.png"}]) is None


def test_placeholder_svg(tmp_path):
    lm = LogoManager(tmp_path, online=False, country="DE")
    svg = lm.placeholder({"id": "fm-d318", "name": "SWR3", "band": "fm"}).decode()
    assert svg.startswith("<svg") and "SWR" in svg and "FM" in svg


def test_custom_logo_has_priority(tmp_path):
    lm = LogoManager(tmp_path, online=False, country="DE")
    (tmp_path / "fm-d318.png").write_bytes(b"cached")
    lm.save_custom("fm-d318", b"custom", "image/png")
    assert lm.path("fm-d318").read_bytes() == b"custom"
    lm.remove_custom("fm-d318")
    assert lm.path("fm-d318").read_bytes() == b"cached"
