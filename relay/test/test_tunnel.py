"""Python unit tests for hub/tunnel.py. From the repo root:  C:\\whyscope-venv\\Scripts\\python.exe -m unittest relay.test.test_tunnel"""
import json
import tempfile
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from hub import tunnel as T


class Tests(unittest.TestCase):
    def pair(self):
        d = tempfile.mkdtemp()
        s = T.Store(d)
        b = s.pair("Wand", "kid", "ws://relay.invalid")
        dev = b["device"]
        cli = T.Channel(True, bytes.fromhex(dev["priv"]), bytes.fromhex(b["hub_pub"]), T.prologue(b["host_id"], dev["id"]))
        hub = T.Channel(False, s.xk, bytes.fromhex(dev["pub"]), T.prologue(b["host_id"], dev["id"]))
        reply = hub.accept(cli.hello())
        cli.finish(reply)
        return s, b, cli, hub

    def test_handshake_and_roundtrip(self):
        s, b, cli, hub = self.pair()
        self.assertTrue(cli.ready and hub.ready)
        msg = T.pack({"id": 1, "method": "GET", "path": "/healthz", "headers": {}})
        out = [hub.feed(f) for f in cli.seal(msg)]
        self.assertEqual(out, [msg])

    def test_large_message_is_chunked(self):
        s, b, cli, hub = self.pair()
        msg = T.pack({"id": 2}, bytes(range(256)) * 4000)       # about 1 MB
        frames = cli.seal(msg)
        self.assertGreater(len(frames), 15)
        self.assertTrue(all(len(f) <= T.NOISE_MAX for f in frames))
        got = [hub.feed(f) for f in frames]
        self.assertEqual(got[:-1], [None] * (len(frames) - 1))
        self.assertEqual(got[-1], msg)

    def test_oversize_and_tamper_and_replay(self):
        s, b, cli, hub = self.pair()
        f = cli.seal(b"hello")[0]
        bad = bytearray(f); bad[3] ^= 1
        with self.assertRaises(Exception):
            hub.feed(bytes(bad))
        s2, b2, cli2, hub2 = self.pair()
        f = cli2.seal(b"hello")[0]
        hub2.feed(f)
        with self.assertRaises(Exception):
            hub2.feed(f)                                      # replay
        s3, b3, cli3, hub3 = self.pair()
        with self.assertRaises(ValueError):
            for fr in cli3.seal(b"x" * (T.MAX_MESSAGE + 100)):
                hub3.feed(fr)

    def test_wrong_device_key_fails_handshake(self):
        s, b, cli, hub = self.pair()
        other = s.pair("Other")["device"]
        cli = T.Channel(True, bytes.fromhex(other["priv"]), bytes.fromhex(b["hub_pub"]), T.prologue(b["host_id"], b["device"]["id"]))
        hub = T.Channel(False, s.xk, bytes.fromhex(b["device"]["pub"]), T.prologue(b["host_id"], b["device"]["id"]))
        with self.assertRaises(Exception):
            hub.accept(cli.hello())

    def test_ticket_is_signed_and_bound_to_hub(self):
        s, b, *_ = self.pair()
        _, body, sig = b["ticket"].split(".")
        pub = ed25519.Ed25519PublicKey.from_public_bytes(s.ed_pub)
        pub.verify(T.unb64u(sig), f"whyscope-ticket-v1|{b['host_id']}|{body}".encode())
        with self.assertRaises(InvalidSignature):
            pub.verify(T.unb64u(sig), f"whyscope-ticket-v1|{'0' * 32}|{body}".encode())
        self.assertEqual(json.loads(T.unb64u(body))["d"], b["device"]["id"])
        self.assertEqual(b["host_id"], T.host_id_of(s.ed_pub))

    def test_revoke_removes_device(self):
        s, b, *_ = self.pair()
        self.assertEqual(s.revoke("Wand"), [b["device"]["id"]])
        self.assertNotIn(b["device"]["id"], s.devices())
        self.assertIn(b["device"]["id"], s.revoked())

    def test_kid_role_scope(self):
        a = T.allowed
        self.assertTrue(a("kid", "POST", "/api/ask?wait=1", b"{}"))
        self.assertTrue(a("kid", "GET", "/api/ask/abc", b""))
        self.assertTrue(a("kid", "POST", "/api/settings", b'{"language":"en"}'))
        self.assertFalse(a("kid", "POST", "/api/settings", b'{"retention_days":1}'))
        self.assertFalse(a("kid", "GET", "/api/data/export", b""))
        self.assertFalse(a("kid", "POST", "/api/data/clear", b""))
        self.assertFalse(a("kid", "GET", "/static/../x", b""))
        self.assertTrue(a("parent", "GET", "/api/data/export", b""))
        self.assertFalse(a("parent", "GET", "//evil.example/x", b""))

    def test_qr_string_roundtrip(self):
        s, b, *_ = self.pair()
        self.assertEqual(T.parse_qr_string(T.qr_string(b)), b)


if __name__ == "__main__":
    unittest.main()
