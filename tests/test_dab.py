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


def test_usb_find_sticks_without_sysfs(tmp_path, monkeypatch):
    from yapaia import usb

    dev = tmp_path / "1-1"
    dev.mkdir()
    for name, val in {"idVendor": "0bda", "idProduct": "2838", "busnum": "1", "devnum": "7"}.items():
        (dev / name).write_text(val + "\n")
    other = tmp_path / "1-2"
    other.mkdir()
    for name, val in {"idVendor": "1d6b", "idProduct": "0002", "busnum": "1", "devnum": "1"}.items():
        (other / name).write_text(val + "\n")
    monkeypatch.setattr(usb, "SYSFS", tmp_path)
    assert [str(p) for p in usb.find_sticks()] == ["/dev/bus/usb/001/007"]
