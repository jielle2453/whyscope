# Whyscope (好奇鏡) - English deck outline (14 slides)

Team SudoStudio. ASUS UGen AI League 2026, international online track, Stage II. Placeholders in {{double braces}} are filled
once measurements are final.

## 1. Title
- Whyscope: a "why" answerer for children aged 5-8 that lives at home
- Powered by the ASUS UGen300 USB (Hailo-10H)
- Team SudoStudio
- Voice and photos never leave the house
- Note: "Children ask why a hundred times a day. We built something that answers safely, at home, with a parent in the loop."
- Visual: logo (brand/), photo of a child's hand holding a snail next to the UGen300 and laptop.

## 2. Problem
- Children aged 5-8 ask endless "why" questions; adults cannot always answer or are not there
- Cloud assistants upload a child's voice and room; general chatbots can state wrong things confidently
- Small on-device LLMs hallucinate (we measured it)
- Parents want to know what the child asked and to answer the hard ones themselves
- Note: Set up the three tensions: privacy, correctness, parent involvement.
- Visual: three icons (cloud with a cross, wrong-answer bubble, parent silhouette).

## 3. Solution
- A hub on the family PC with a UGen300; the child talks, types or shows an object
- Answers come from curated, child-level text, spoken in short sentences, plus one question back
- Unsure means "I'm not sure, I'll ask your grown-up", and the parent gets the question
- Sensitive topics go straight to a parent with talking points
- Note: The child never gets raw LLM text as fact.
- Visual: one-line flow: child -> hub (UGen) -> answer, with a branch "unsure -> parent".

## 4. Demo flow
- Voice question (English) -> first sentence in about {{LATENCY_FIRST_SENTENCE_P50}}
- Show the camera an object -> answer about it
- Unknown question -> abstain -> appears in the parent's To-answer list with an LLM draft
- Parent approves -> child hears "Your grown-up found the answer!"
- Away from home through the relay; offline curiosity jar
- Note: This is the video in under 10 minutes; point to the timestamps.
- Visual: storyboard strip of 5 screenshots (docs/screens/).

## 5. The UGen300's role: ears, eyes, helper
- Ears: Whisper-Small English ASR, WER 1.4 %, about 1.0-1.2 s per clip (equal to faster-whisper small on CPU)
- Eyes: YOLOv8s (about 20 ms) + CLIP ViT-B/32 image encoder (cosine 0.961 vs OpenAI weights)
- Helper: the LLM drafts answers for the parent in the background when idle
- One process, one shared VDevice, four models loaded at once
- Note: Chinese ASR stays on CPU (UGen CER 10.7-15.3 % vs 2.7 %): an honest limit.
- Visual: the UGen300 photo with three labelled arrows (ears, eyes, helper) and a screenshot of worker /info listing 4 models.

## 6. Architecture
- Hub (FastAPI) + UGen worker (127.0.0.1:8711) + SQLite + knowledge base
- Kid and parent clients over the LAN with device tokens; PIN for sensitive actions
- Away: end-to-end encrypted relay; the hub dials out
- Falls back to CPU models if the worker is down
- Note: Only one process can open the USB device, hence the worker.
- Visual: the Mermaid diagram from docs/architecture.md, rendered.

## 7. How an answer is chosen
- Safety first, then knowledge entry (label guard + asks guard) -> family answer -> principle library -> abstain
- Facts only from curated, reviewed or parent-approved text
- The verbatim first sentence is spoken at once; the explanation follows
- The question back is guessable and about the object, never about the child
- Note: Retrieval, not generation, is what makes it safe.
- Visual: a funnel with the four stops and the abstain exit to the parent.

## 8. Safety and parent in the loop
- Sensitive topics (death, scary news, self-harm) are deflected to a parent, with talking points
- No device feelings, no flattery; voice rules enforced in code (at most 12 words per sentence in English)
- The parent approves every LLM draft before the child hears it; labelled "Draft written by the device"
- Wands see only their own child; PIN for export, clear, revoke, settings
- Note: A wrongly deflected question costs one conversation; a wrongly answered one can cost much more.
- Visual: parent To-answer screenshot with draft and Approve / Edit / Dismiss.

## 9. Why the design changed
- LLM answers kids -> it hallucinated -> facts moved to curated text and principles with abstention
- Worried the UGen lost its point -> repositioned as ears, eyes, helper
- Added accounts, relay and offline jar for "ask anywhere, one host, many kids"
- Note: This is a story about measuring, not guessing.
- Visual: timeline with three transitions.

## 10. Results: UGen numbers
- Whisper-Small on UGen: WER 1.4 %, 1.0-1.2 s per clip
- YOLOv8s about 20 ms; CLIP image encoder cosine 0.961 vs CPU
- Voice question to first sentence: {{LATENCY_FIRST_SENTENCE_P50}}; parent draft per item: {{DRAFT_LATENCY_S}}
- Four models resident on one device; load about 16 s
- Note: Measured at a 1.5 A USB-C port; may be faster at 3.0 A.
- Visual: bar chart UGen vs CPU for ASR WER and latency.

## 11. Results: answer quality
- Clean held-out set ({{HELDOUT_N}} questions): {{V3_RIGHT}} right, {{V3_WRONG}} wrong, {{V3_ABSTAIN}} sent to a parent
- Knowledge: 207 entries (93 curated, 114 AI drafts awaiting review), 71 principles (AI drafts awaiting review)
- Earlier measurement: the hub was right about 84 % of what it answered; a Wikipedia + LLM fallback produced false statements
- Note: Say plainly that judgements are AI-assisted and drafts are not yet human-reviewed.
- Visual: stacked bar: right / wrong / abstained, old vs new.

## 12. Multi-user and anywhere
- Households, several children each, parents with PIN, QR pairing of devices
- Away from home: Noise_KK_25519_AESGCM_SHA256 end to end, Ed25519-signed tickets; the relay sees opaque frames
- Cloudflare Workers + Durable Objects, portable to Docker, VPS or AWS
- Offline curiosity jar queues questions until the hub is reachable
- Note: One host serves many children.
- Visual: phone at a park -> relay -> home hub, with the jar icon.

## 13. Business model and roadmap
- Free at home on your own host; subscription for relay, reviewed knowledge packs, model updates
- Tiers: UGen300 USB on the family PC -> dedicated box (CM5 + Hailo-10H M.2)
- Next: HailoRT 5.4+ (Qwen3-4B / Gemma, Whisper-Medium), Qwen3-VL-2B follow-ups, team review of drafts, user studies
- Privacy is the product: voice and photos stay home
- Note: Pricing {{PRICE_SUBSCRIPTION_PER_MONTH}} is to be set.
- Visual: tier ladder graphic and a roadmap line.

## 14. Team and thanks
- Team SudoStudio: {{TEAM_MEMBERS}}
- Repo: {{REPO_URL}}; video: {{VIDEO_URL}}
- Thanks to ASUS and the UGen AI League
- Note: End on a child's question: "Why does a snail carry its house?"
- Visual: team photo and a QR code to the repo.
