// Cloudflare Worker entry: routes /v1/host/<hubId> and /v1/client/<hubId> to one Durable Object per hub.
// The logic lives in hub.js so the same code also runs in plain Node (node-server.js).
import { DurableObject } from "cloudflare:workers";
import { HubCore } from "./hub.js";

export default {
  async fetch(req, env) {
    const path = new URL(req.url).pathname;
    const m = path.match(/^\/v1\/(host|client)\/([0-9a-f]{32})$/);
    if (path === "/") return new Response("whyscope relay\n");
    if (!m) return new Response("not found\n", { status: 404 });
    if (req.headers.get("Upgrade") !== "websocket") return new Response("websocket required\n", { status: 426 });
    return env.HUB.get(env.HUB.idFromName(m[2])).fetch(req);   // one Durable Object per hub id
  },
};

export class Hub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.core = new HubCore(ctx.storage, env.DEBUG_FRAMES === "1");
  }

  async fetch(req) {
    const [, , role, hubId] = new URL(req.url).pathname.split("/");
    const [client, server] = Object.values(new WebSocketPair());
    server.accept();
    if (role === "host") this.core.onHost(server, hubId); else this.core.onClient(server, hubId);
    return new Response(null, { status: 101, webSocket: client });
  }
}
