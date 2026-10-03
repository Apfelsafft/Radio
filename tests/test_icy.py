import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yapaia_beat/rootfs/opt/yapaia"))

from yapaia.icy import IcyWriter, icy_block, jetzt_titel  # noqa: E402


def test_titel():
    st = {"station": {"name": "SWR3"}, "playing": True, "title": "Show me love", "artist": "WizTheMc"}
    assert jetzt_titel(st) == "WizTheMc - Show me love"
    assert jetzt_titel({**st, "artist": None, "title": None, "radiotext": "Hallo"}) == "Hallo"
    assert jetzt_titel({**st, "playing": False}) == "SWR3"


def test_block():
    b = icy_block("A - B")
    assert b[0] * 16 == len(b) - 1
    assert b[1:].rstrip(b"\0") == b"StreamTitle='A - B';"
    assert icy_block(None) == b"\0"


def test_writer_interleaves_every_metaint_bytes():
    w = IcyWriter(metaint=10)
    out = w.feed(b"x" * 25, "T")
    # 10 audio, block, 10 audio, block, 5 audio
    blk = icy_block("T")
    assert out == b"x" * 10 + blk + b"x" * 10 + b"\0" + b"x" * 5
    # the next 5 bytes complete the interval; a new title is sent again
    out2 = w.feed(b"y" * 5, "U")
    assert out2 == b"y" * 5 + icy_block("U")


def test_stream_liefert_icy_nur_auf_wunsch():
    import asyncio

    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from yapaia import web as yweb

    class Audio:
        def __init__(self):
            self.q = asyncio.Queue()

        def add_client(self):
            for _ in range(3):
                self.q.put_nowait(b"m" * 10000)
            return self.q

        def remove_client(self, q):
            pass

    class Radio:
        audio = Audio()

        def wake(self):
            pass

        def changed(self):
            pass

        def status(self):
            return {"playing": True, "station": {"name": "SWR3"}, "title": "Lied", "artist": "Band"}

    async def lauf():
        app = web.Application()
        app["radio"] = Radio()
        app.router.add_get("/stream.mp3", yweb.stream)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/stream.mp3", headers={"Icy-MetaData": "1"})
            assert r.headers["icy-metaint"] == "16000"
            daten = await r.content.readexactly(16000 + 1 + 32)
            assert b"StreamTitle='Band - Lied';" in daten[16000:]
            r.close()
            r = await c.get("/stream.mp3")
            assert "icy-metaint" not in r.headers
            r.close()

    asyncio.run(lauf())
