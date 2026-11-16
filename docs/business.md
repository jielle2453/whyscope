# Business model

Whyscope is an on-device "why" answerer for children aged 5 to 8 with a parent in the loop. The business keeps the part that
should be private (voice, photos, the child's questions) free and at home, and charges for the parts that cost us something to
run or to keep correct.

## Who pays for what

| | free, on the family's own host | subscription |
|---|---|---|
| Ask at home (voice, typing, camera) | yes | |
| Parent page: To answer, week view, talking-point cheat sheets, family answers | yes | |
| Several children and parents per household, QR pairing | yes | |
| Away from home: encrypted relay, curiosity jar sync | | yes |
| Reviewed knowledge packs (new topics, new languages, each with a named reviewer and sources) | base pack | updates and extra packs |
| Model updates for the UGen (better parent drafts, better speech models) | | yes |

Why this split: the relay is a running service with a real cost (Cloudflare Workers and Durable Objects, or a VPS), and
reviewed content costs people's time. Neither is needed for the core promise of "a safe answer at home, nothing uploaded".
Pricing is not fixed: {{PRICE_SUBSCRIPTION_PER_MONTH}} per household per month is a placeholder to be set after cost
measurement.

## Hardware tiers

| tier | hardware | who it is for | status |
|---|---|---|---|
| Entry | ASUS UGen300 USB (Hailo-10H, 8 GB) on the family's own PC or laptop | families who already have a computer; the demo setup | working prototype (this repo) |
| Box | dedicated box: Raspberry Pi Compute Module 5 + Hailo-10H M.2 on a custom carrier board | families who want an always-on device without a PC | later; Pi 5 + AI HAT+ 2 as the prototype |
| Kid device | "wand" (microphone, camera, speaker) paired to the box or PC | the child | later; today's kid web page is a prototype client |

One host serves many children: a household can have several children and several parents, each device paired by QR and limited
to its own role.

## Cost to run

* **At home:** no per-question cloud cost. Everything runs on the family's host and the UGen. Electricity and the one-off
  hardware are the family's.
* **Relay:** forwards opaque encrypted frames only, so it is cheap and stateless apart from the connection. It is written to run on
  Cloudflare Workers + Durable Objects and is portable (a plain Node server for Docker, a VPS or AWS: `relay/node-server.js`).
  Cost per household per month: {{RELAY_COST_PER_HOUSEHOLD}} (to be measured).
* **Content:** the main recurring cost is review. Of 207 knowledge entries, 93 are curated and 114 are AI drafts awaiting team
  review; 71 principles are AI drafts awaiting review. Review capacity sets how fast packs can ship.
* **Hardware (bill of materials):** UGen300 {{UGEN300_PRICE}}; dedicated box {{BOX_BOM}}.

## Privacy as the product

* Voice and photos are processed at home in memory and **never uploaded**; only question and answer text is stored (retention
  default 30 days, export and clear behind the parent PIN).
* No cloud AI is called at run time (`cloud_fallback: false`).
* Away from home, traffic is end-to-end encrypted between the child's device and the hub (Noise_KK_25519_AESGCM_SHA256, hub
  Ed25519-signed tickets). The relay cannot read it and a revoked device loses its relay key.
* Safety: sensitive topics are deflected to a parent with talking points; unsure answers go to the parent, not guessed
  ([safety.md](safety.md)).

## Go to market

Start with the entry tier for families that own a Windows or Linux PC, free at home; convert on away-from-home use and reviewed
packs; then offer the box. Partnerships (schools, libraries, content reviewers) are possible later. User studies will guide
pricing and content; none are claimed here.

## Licensing

Code Apache-2.0, knowledge entries CC BY-SA 4.0, models keep their own licenses ([models.md](models.md)). YOLOv8 is AGPL-3.0:
check terms (or switch detector) before selling a product.
