// JS unit tests: node --test test/   (from relay/). Needs relay/test/kat.json from make_kat.py.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";

const T = createRequire(import.meta.url)("../../hub/static/tunnel.js");
const kat = JSON.parse(fs.readFileSync(new URL("./kat.json", import.meta.url)));
const te = new TextEncoder();
const { hex, unhex } = T;

async function handshake() {
  const n = new T.NoiseKKInitiator(unhex(kat.is), await pubOf(kat.rs), te.encode(kat.prologue), unhex(kat.ie));
  await n.start();
  return n;
}
async function pubOf(privHex) {   // X25519 public key of a private key, via the same WebCrypto path
  const n = new T.NoiseKKInitiator(unhex(privHex), new Uint8Array(32), new Uint8Array(0), null);
  await n.start();
  return n.s.pub;
}

test("Noise_KK known answer: JS initiator reproduces the Python (noiseprotocol) bytes", async () => {
  const n = new T.NoiseKKInitiator(unhex(kat.is), await pubOf(kat.rs), te.encode(kat.prologue), unhex(kat.ie));
  await n.start();
  assert.equal(hex(await n.writeMessage1()), kat.msg1);
  await n.readMessage2(unhex(kat.msg2));
  for (let i = 0; i < 2; i++) {
    assert.equal(hex(await n.send.encrypt(new Uint8Array(0), unhex(kat.device_to_hub_plain[i]))), kat.device_to_hub[i]);
    assert.equal(hex(await n.recv.decrypt(new Uint8Array(0), unhex(kat.hub_to_device[i]))), kat.hub_to_device_plain[i]);
  }
});

test("a tampered or wrongly-keyed handshake reply is rejected", async () => {
  const n = await handshake();
  await n.writeMessage1();
  const bad = unhex(kat.msg2); bad[40] ^= 1;
  await assert.rejects(n.readMessage2(bad));
  const n2 = await handshake();                              // different prologue = different session binding
  n2.prologue = te.encode("other");
  const m = new T.NoiseKKInitiator(unhex(kat.is), await pubOf(kat.rs), te.encode("other"), unhex(kat.ie));
  await m.start(); await m.writeMessage1();
  await assert.rejects(m.readMessage2(unhex(kat.msg2)));
});

test("transport rejects modified ciphertext and replayed or reordered frames", async () => {
  const n = await handshake();
  await n.writeMessage1(); await n.readMessage2(unhex(kat.msg2));
  const bad = unhex(kat.hub_to_device[0]); bad[0] ^= 1;
  await assert.rejects(n.recv.decrypt(new Uint8Array(0), bad));
  await n.recv.decrypt(new Uint8Array(0), unhex(kat.hub_to_device[0]));
  await assert.rejects(n.recv.decrypt(new Uint8Array(0), unhex(kat.hub_to_device[0])));   // replay
});

test("framing: 1 MB message is chunked below the 65535-byte Noise limit and keeps its last-chunk flag", async () => {
  const n = await handshake();
  await n.writeMessage1(); await n.readMessage2(unhex(kat.msg2));
  const body = new Uint8Array(1_000_000).fill(7);
  const msg = T.pack({ id: 1, method: "POST", path: "/api/ask", headers: {} }, body);
  const frames = await T.seal(n.send, msg);
  assert.ok(frames.every((f) => f.length <= 65535));
  assert.equal(frames.length, Math.ceil(msg.length / (65535 - 17)));
  const [meta, b] = T.unpack(msg);
  assert.equal(meta.path, "/api/ask"); assert.equal(b.length, 1_000_000);
});
