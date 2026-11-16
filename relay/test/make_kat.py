"""Known-answer test for the JS Noise code: generates kat.json with the vetted `noiseprotocol` library using FIXED keys
(initiator = device, responder = hub), so tunnel.js must reproduce the same bytes. Run from the repo root:
  C:\\whyscope-venv\\Scripts\\python.exe relay\\test\\make_kat.py          (rewrites kat.json)
  ... make_kat.py --check                                                   (compares with kat.json)
"""
import json
import sys
from pathlib import Path

from noise.backends.default.keypairs import KeyPair25519
from noise.connection import Keypair, NoiseConnection

PROTO = b"Noise_KK_25519_AESGCM_SHA256"
K = {n: bytes([i] * 32) for i, n in enumerate(["is", "rs", "ie", "re"], start=1)}   # fixed private keys (test only)
PROLOGUE = b"whyscope-v1|0123456789abcdef0123456789abcdef|deadbeef"


def pub(priv):
    return KeyPair25519.from_private_bytes(priv).public_bytes


def conn(initiator):
    n = NoiseConnection.from_name(PROTO)
    (n.set_as_initiator if initiator else n.set_as_responder)()
    mine, theirs, eph = ("is", "rs", "ie") if initiator else ("rs", "is", "re")
    n.set_keypair_from_private_bytes(Keypair.STATIC, K[mine])
    n.set_keypair_from_public_bytes(Keypair.REMOTE_STATIC, pub(K[theirs]))
    n.set_prologue(PROLOGUE)
    n.start_handshake()
    n.noise_protocol.handshake_state.e = KeyPair25519.from_private_bytes(K[eph])
    return n


def make():
    i, r = conn(True), conn(False)
    m1 = i.write_message(b"")
    r.read_message(m1)
    m2 = r.write_message(b"")
    i.read_message(m2)
    c = [i.encrypt(b"\x01ping"), i.encrypt(b"\x01second")]       # device -> hub transport messages
    d = [r.encrypt(b"\x01pong"), r.encrypt(b"\x01reply2")]       # hub -> device
    assert r.decrypt(c[0]) == b"\x01ping" and i.decrypt(d[0]) == b"\x01pong"
    return {"protocol": PROTO.decode(), "prologue": PROLOGUE.decode(), **{k: v.hex() for k, v in K.items()},
            "msg1": m1.hex(), "msg2": m2.hex(), "device_to_hub": [x.hex() for x in c], "hub_to_device": [x.hex() for x in d],
            "device_to_hub_plain": ["01" + b"ping".hex(), "01" + b"second".hex()],
            "hub_to_device_plain": ["01" + b"pong".hex(), "01" + b"reply2".hex()]}


if __name__ == "__main__":
    f = Path(__file__).with_name("kat.json")
    v = make()
    if "--check" in sys.argv:
        assert json.loads(f.read_text()) == v, "kat.json differs"
        print("kat.json matches")
    else:
        f.write_text(json.dumps(v, indent=1))
        print("wrote", f)
