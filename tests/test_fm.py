from yapaia.fm import RdsState, fm_candidates, khz_to_mhz


def test_rds_state_collects_everything():
    rds = RdsState()
    for ps in ("SWR3", "SWR3", "NEWS"):
        rds.update({"pi": "0xD318", "ps": ps, "prog_type": "Pop Music", "tp": True, "bler": 3})
    rds.update({"radiotext": "SWR3  -  Jetzt:   Dua Lipa - Houdini", "alt_frequencies_a": [94300, 97500]})
    rds.update({"radiotext_plus": {"tags": [
        {"content-type": "item.artist", "data": "Dua Lipa"}, {"content-type": "item.title", "data": "Houdini"}]}})
    assert rds.pi == "0xD318"
    assert rds.name == "SWR3"  # most frequent PS, scrolling PS ignored
    assert rds.radiotext == "SWR3 - Jetzt: Dua Lipa - Houdini"
    assert rds.af == {94.3, 97.5}
    assert (rds.artist, rds.title) == ("Dua Lipa", "Houdini")
    assert rds.tp and rds.bler == 3


def test_pi_needs_confirmation():
    rds = RdsState()
    rds.update({"pi": "0xD318"})
    assert rds.pi is None
    rds.update({"pi": "0xD318"})
    assert rds.pi == "0xD318"


def test_khz_to_mhz():
    assert khz_to_mhz(97500) == 97.5
    assert khz_to_mhz(97.5) == 97.5
    assert khz_to_mhz(531) is None


def test_fm_candidates_finds_peaks_only():
    spectrum = {}
    f = 87.3
    while f < 108.2:
        spectrum[round(f, 3)] = -45.0
        f += 0.01
    for station in (94.3, 101.3):
        for k in list(spectrum):
            if abs(k - station) < 0.1:
                spectrum[k] = -20.0 if abs(k - station) < 0.06 else -30.0
    found = [f for f, _ in fm_candidates(spectrum, 100, 8)]
    assert found == [94.3, 101.3]


def test_parse_rtl_power_partial_output():
    from yapaia.fm import _parse_rtl_power

    out = "2026-09-28, 01:00:00, 174000000, 176000000, 200000.00, 100, -40.0, -30.5, nan\n" "garbage line\n"
    spec = _parse_rtl_power(out)
    assert spec == {174.0: -40.0, 174.2: -30.5}
