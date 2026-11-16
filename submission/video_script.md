# Demo video script (target 9:30, maximum 10:00)

Language: English. Setup: laptop with the UGen300 plugged in, worker and hub running, kid page on a phone (or a second window),
parent page in another window. Use a fresh household (do not load `scripts/seed_demo.py` data) so the To-answer list starts empty.

| time | scene | shot | narration |
|---|---|---|---|
| 0:00-0:25 | Hook | Child's hand, a snail on a leaf; cut to the laptop with the UGen300 USB device in frame | "Children ask why all day. Whyscope answers at home, on the ASUS UGen300, with a parent in the loop. Nothing is uploaded." |
| 0:25-1:10 | Problem and idea | Slides 2-3 (or simple graphics) | "Cloud assistants hear your child's voice. Small LLMs make up facts. So children only hear curated text, and the UGen is the ears, the eyes and the helper." |
| 1:10-2:10 | The hardware running | Close-up of the UGen300; terminal: `hailortcli fw-control identify` (Hailo-10H, 5.3.2); then `POST http://127.0.0.1:8711/info` (curl) showing four models loaded: llm, whisper, yolo, clip_image | "One worker process owns the device, because only one process can open the USB. It holds four models at once: the LLM, Whisper-Small, YOLOv8s and the CLIP image encoder." |
| 2:10-3:30 | Live voice question | Kid page, hold the button, ask "Why does a snail have a shell?"; the first sentence appears and is spoken; show `/healthz` ugen block with the ASR backend = hailo | "Whisper-Small on the UGen hears the child: English word error rate 1.4 percent, about a second a clip. The first sentence is the knowledge entry's own, so it is spoken at once. Then one question back about the snail." |
| 3:30-3:50 | Reply turn | Tap one of the two answers | "The child guesses first and hears the answer after. It never says 'wrong'." |
| 3:50-4:50 | Camera object question | Hold an object (a ball or a toy) to the camera and ask about it | "YOLOv8s finds the object in about 20 milliseconds. The CLIP image encoder on the UGen turns it into an embedding, and a precomputed label table finds the entry. The photo is never saved." |
| 4:50-5:40 | Unsure and safety | Ask an unusual question: the child hears "I'm not sure, I'll ask your grown-up". Then a sensitive question and its deflection | "If we do not know, we say so. Sensitive topics go to a parent, who gets talking points." |
| 5:40-7:00 | Parent: To answer + LLM draft | Parent page To-answer list; wait for the idle draft ("Draft written by the device"); show the context used; edit a word; Approve; cut to the kid page: "Your grown-up found the answer!" and the spoken answer | "While the device is idle, the UGen's LLM drafts an answer for the parent, grounded in our facts. The parent checks it, edits it and approves. Only then does the child hear it, and it is kept as a family answer." |
| 7:00-7:50 | Households and pairing | Parent page Settings > Family: add a child, show the QR code, scan with the phone, show the device list | "One host, many children: households, parents with a PIN, devices paired by QR code." |
| 7:50-8:50 | Away mode via relay | Phone on mobile data (Wi-Fi off); the badge shows "Away (encrypted)"; ask a question; the answer returns; show a relay log or the tunnel test page to show only opaque frames | "Away from home, the phone reaches the hub through an end-to-end encrypted relay. The relay sees only opaque frames, and the hub dials out, so there is no port forwarding." |
| 8:50-9:20 | Offline jar | Turn off all network; ask; the badge shows Offline and the jar count; reconnect; the answer appears on the parent page with the original time | "With no connection, the curiosity jar keeps the question and sends it when the hub is reachable." |
| 9:20-9:50 | Results and close | Slides 10 and 11 (UGen numbers; held-out result {{V3_RIGHT}}), roadmap line | "Next: bigger models on HailoRT 5.4, a dedicated box, and a kid device. Whyscope: ask anywhere, answered at home." |

## Shot list (checklist)
1. UGen300 physical close-up, plugged into the laptop.
2. Terminal: `hailortcli scan` and `hailortcli fw-control identify`.
3. Worker `/info` with 4 models loaded (llm, whisper, yolo, clip_image).
4. `/healthz` "ugen" block (worker reachable, ASR backend hailo).
5. Kid page voice question (screen and audible speech).
6. Kid page camera object question.
7. Abstain and sensitive deflection.
8. Parent To-answer with draft, edit, approve; kid delivery.
9. Pairing QR scan.
10. Phone on mobile data: Away badge and relay question.
11. Offline jar, then reconnect.
12. Closing slides.

## Recording notes
- Record at 1080p; capture the phone with screen mirroring or a second camera.
- Voice questions must be English and clearly audible so the ASR can be seen working.
- Prepare an unusual question beforehand so a draft is generated during the take; the idle wait is 20 s, or cut it.
- The relay needs a secure context (https or localhost) in the phone browser: rehearse the away scene.
- Do not claim user studies. Say "prototype web pages; the product would be a kid wand and a parent app".
