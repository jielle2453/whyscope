# Roadmap

## Stage I (done)

A laptop hub (`mode: gpu`, RTX 4060 laptop): text and voice questions, a curated knowledge base, abstention, sensitive-topic
routing, a parent page. See [benchmarks.md](benchmarks.md).

## Stage II (now, submit 2026-12-03)

The same product running with an **ASUS UGen300 USB** as ears, eyes and helper ([ugen.md](ugen.md)): one worker, four models on one
shared device (LLM, Whisper-Small, YOLOv8s, CLIP image encoder), parent drafts, accounts with several children, encrypted relay,
offline curiosity jar. Results: {{V3_RIGHT}} correct on the clean held-out set ([eval/coverage_report.md](../eval/coverage_report.md)
for the earlier measurement).

## The story: how the design changed

1. **LLM answers the child.** The first idea was a small on-device LLM answering children's "why" questions.
2. **It hallucinated.** The 1.5B model gave false statements to children, even with retrieved passages
   ([eval/coverage_report.md](../eval/coverage_report.md)) and even with the right principle
   ([eval/principles/report.md](../eval/principles/report.md)). A child must not get raw LLM text as fact.
3. **Facts moved to curated text with abstention.** Answers now come from a curated knowledge base (207 entries) and a principle
   library (71 principles), with strict guards and an honest "I'm not sure, I'll ask your grown-up" that goes to a parent.
4. **Worry: did the UGen lose its point?** If the LLM no longer answers, what is the accelerator for?
5. **Repositioned: ears, eyes, helper.** Whisper-Small hears the child, YOLOv8s and CLIP see the object, and the LLM helps the parent
   by drafting answers that a person approves. Privacy (everything at home) and the parent in the loop stay central.
6. **Ask anywhere, one host many kids.** Households, several children, PIN-protected parents, QR pairing; an end-to-end encrypted
   relay for away from home; an offline curiosity jar that holds questions until the hub is reachable again.

## Next

| item | why |
|---|---|
| HailoRT 5.4+ | larger LLM (Qwen3-4B or Gemma) for better parent drafts; Whisper-Medium for better speech recognition, possibly Chinese |
| Qwen3-VL-2B vision-language model | follow-up "what is this?" questions about the camera image |
| Team review of drafts | review the 114 AI-draft entries and 71 principles (`reviewed_by`), then ship them as reviewed packs |
| Dedicated box | CM5 + Hailo-10H M.2 on a custom carrier board (Pi 5 + AI HAT+ 2 as the prototype); always-on at home |
| Kid wand and parent app | replace the prototype web pages with a kid device and a real parent app |
| User studies | learn what children ask and how parents use the To-answer list |
| Hosted relay as a service | subscription for away-from-home ([business.md](business.md)) |

Known limits we state openly: Chinese speech recognition stays on the CPU (UGen Whisper CER 10.7-15.3 % vs 2.7 %); drafts for
a parent can be weak when no fact fits; the USB-C port on the test laptop advertised only 1.5 A.
