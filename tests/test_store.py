from yapaia.store import Store


def test_fm_merge_groups_by_pi(tmp_path):
    store = Store(tmp_path / "s.json")
    store.merge_fm([
        {"freq": 94.3, "pi": "0xD318", "name": "SWR3", "quality": 80},
        {"freq": 97.5, "pi": "0xD318", "name": "SWR3", "quality": 60},
        {"freq": 101.3, "pi": None, "name": "FM 101,3", "quality": 40},
    ])
    swr3 = store.get("fm-d318")
    assert swr3["freq"] == 94.3
    assert [f["freq"] for f in swr3["freqs"]] == [94.3, 97.5]
    assert store.get("fm-101300")["name"] == "FM 101,3"


def test_favorites_persist_and_order(tmp_path):
    store = Store(tmp_path / "s.json")
    store.merge_dab([
        {"sid": "0xd318", "name": "SWR3", "channel": "11D", "ensemble": "SWR BW S", "quality": 90},
        {"sid": "0x10bc", "name": "Deutschlandfunk", "channel": "5C", "quality": 70},
    ])
    store.set_favorite("dab-d318", True)
    store.set_favorite("dab-10bc", True)
    store.order_favorites(["dab-10bc", "dab-d318"])
    store.rename("dab-10bc", "DLF")
    again = Store(tmp_path / "s.json")
    assert again.favorites == ["dab-10bc", "dab-d318"]
    assert again.get("dab-10bc")["custom_name"] == "DLF"
    assert again.find_by_name("dlf")[0]["id"] == "dab-10bc"


def test_rescan_keeps_favorites_marks_unavailable(tmp_path):
    store = Store(tmp_path / "s.json")
    store.merge_fm([{"freq": 94.3, "pi": "0xD318", "name": "SWR3", "quality": 80}])
    store.set_favorite("fm-d318", True)
    store.merge_fm([{"freq": 88.8, "pi": "0xD3C3", "name": "SWR1 BW", "quality": 80}])
    assert store.favorites == ["fm-d318"]
    assert store.get("fm-d318")["available"] is False
