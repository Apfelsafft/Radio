from yapaia.dab import norm_sid, split_dls


def test_split_dls():
    assert split_dls("SWR3: Coldplay - Yellow") == ("Coldplay", "Yellow")
    assert split_dls("SWR3 – Jetzt: Dua Lipa - Houdini") == ("Dua Lipa", "Houdini")
    assert split_dls("Nachrichten") == (None, None)
    assert split_dls("A - B - C") == (None, None)
    assert split_dls(None) == (None, None)


def test_norm_sid():
    assert norm_sid("0xD318") == "0xd318"
    assert norm_sid(54040) == "0xd318"
