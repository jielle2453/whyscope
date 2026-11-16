# LoRA on Hailo-10H (UGen300) - research (2026-11-16)

Verdict: **Possible only for Qwen2-1.5B-Instruct, not Qwen2.5-1.5B-Instruct, and only via an experimental, poorly documented toolchain.** High risk for a 2026-12-03 deadline.

## 1. How a LoRA gets into a HEF
- Tool: Hailo Dataflow Compiler (DFC) GenAI/LoRA flow (`ClientRunner(hw_arch="hailo10h")`, `load_lora_weights()`, `optimize()`, `compile()`). Starts from a Hailo-supplied pre-optimized HAR (`qwen2_1.5b_instruct.q.har`, ~40 GB) plus two ALLS files (`qwen2_1.5b_instruct.alls`, `..._compilation.alls`). A LoRA tutorial notebook ships in the Hailo AI Software Suite docker (`hailo tutorial`). Sources: [forum 18892](https://community.hailo.ai/t/har-cannot-be-recompiled-with-dfc-5-2-0-due-to-context-partition-topology-error-which-blocks-lora-deployment/18892), [forum 19497](https://community.hailo.ai/t/is-there-a-documented-flow-for-compiling-a-custom-fine-tuned-llm-to-the-hailo-10h-llm-pipeline/19497), [CSDN walkthrough](https://aicoding.csdn.net/6a687bd010ee7a33f2937279.html). Confidence: medium-high (staff statements via forum; walkthrough author says untested).
- Availability: DFC/HAR are on the Hailo Developer Zone behind free registration (account + EULA). Not pip/public. Confidence: medium (forum + ultralytics docs; I could not open the portal).
- OS: DFC requires Linux x86_64 (Ubuntu 20.04/22.04 / Hailo AI Software Suite docker). Windows would need WSL2 (a forum thread on DFC GPU under WSL exists). Confidence: medium.
- Hardware: one walkthrough claims 32 GB VRAM GPU + 128 GB RAM; compile of the stock HAR reportedly took ~15 h (55,472 s) then failed on DFC 5.2.0. Confidence: low-medium (single anecdotes). Our laptop RTX 4060 8 GB cannot do that; calibration/optimize likely needs a big cloud GPU box + large RAM/disk.
- Recipe constraints (staff-endorsed): LoRA on MLP only `gate_proj, up_proj, down_proj`, rank r=32, lora_alpha=64 (matches HAR scaffold, 84 LoRA positions). Another user used r=16. Confidence: medium-high.
- **Base models: Qwen2-1.5B-Instruct is the ONLY LoRA example/HAR.** Staff (2026-03-02): "We released HAR only for the LoRA model", and confirmed Qwen2 1.5B is the only LoRA example; no Qwen2.5-1.5B HAR exists (model zoo lists HEFs only, no HARs). [forum 18862](https://community.hailo.ai/t/where-can-we-find-the-qwen2-5-1-5b-instruct-har/18862), [MODELS.rst](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst). Confidence: high as of Mar 2026; may have changed in 5.4/5.5 (not verified).
- Custom (non-LoRA) LLM compile: staff say unsupported ("DFC supports only non-GenAI models for the time being", May 2026). [forum 19368](https://community.hailo.ai/t/hailo-10-ai-hat-2-converting-onnx-llms-to-hef-ollama-embedding-support/19368). Community [hailo-10h-llm-compiler](https://github.com/l-nmch/hailo-10h-llm-compiler) (MIT, Aug 2026) is experimental, validated only on a 25M model, multi-token generation degraded. Not usable for us.

## 2. Multiple adapters / runtime
- Multi-LoRA HEF: yes in principle; a user compiled one HEF with 3 adapters (router/engineer/responder), each as network groups `<name>__prefill` / `<name>__tbt`. Another hit `ValueError` on the 5th adapter. Confidence: medium (forum).
- Runtime selection: `LLM(vdevice, hef_path, lora_name="adapter")` (local pyhailort.py lines 4108-4123; HRT_3_LLM_Tutorial notebook also has `LORA_NAME`). Python/C++ GenAI API only; **hailo-ollama does not support LoRA** (staff, Mar 2026). Confidence: high.
- Reported failure: that 3-adapter HEF compiled with DFC 5.2.0 failed to load via `genai.LLM` with `HAILO_HEF_FILE_CORRUPTED(91)`; unresolved. [forum 19494](https://community.hailo.ai/t/qwen-compiled-lora-hef-successful-but-not-possible-to-create-llm-object-via-hailo-platform-genai/19494). Confidence: medium.
- Versions: HAR version must match DFC version (stock Qwen2 HAR was 5.1.0.dev0, rejected by DFC 5.3.0 as "too old"; staff say use the HAR/ALLS released with your DFC, archive filter on downloads page). [forum 19268](https://community.hailo.ai/t/har-version-mismatch-qwen2-1-5b-har-5-1-0-dev0-incompatible-with-dfc-5-3-0-lora-deployment-blocked/19268). HEF must be loadable by runtime: model-zoo table says models need HailoRT "> 5.1.1" to "> 5.4.0" and some only 5.5.0; a DFC 5.4/5.5 HEF very likely needs HailoRT 5.4/5.5 (a 5.3.0 DFC HEF on HailoRT 5.3.x is the safe pairing). Our runtime is 5.3.2, so we would need DFC 5.3.x (check archive) or upgrade the runtime/driver to match. Confidence: medium-low (inference).
- Reported DFC 5.2.0 compile failure "Context-Partition Topology Error" on stock HAR (version mismatch blamed by staff, not confirmed fixed).

## 3. Without the toolchain
- Local `hailo_platform` 5.3.2 (`genai/__init__.py`, `pyhailort.py`) only exposes the `lora_name` string; no adapter-file loader. `_pyhailort.pyd` has no readable LoRA strings. LoRA names are baked into the HEF as network groups. No evidence of any precompiled HEF accepting external adapter files. Confidence: high for local inspection, medium for "does not exist".
- Fallback: prompt/few-shot engineering, system prompt, RAG-style selection of reference answers, constrained output/post-processing, and shipping a rule-based "I don't know" gate on top of the stock Qwen2.5 HEF (or Qwen2 HEF). This needs no toolchain. Optionally train LoRA on the PC GPU only for a CPU/GPU demo path or as the documented future work.

## 4. Training side
- GPU: NVIDIA GeForce RTX 4060 Laptop, 8188 MiB VRAM (driver 566.07, 0 MiB used).
- 1.5B LoRA/QLoRA: fits comfortably with 4-bit QLoRA (~4-6 GB) via HF PEFT + TRL SFTTrainer (+bitsandbytes; bitsandbytes on native Windows works in recent versions, else WSL2) or Unsloth. Use r=32, alpha=64, targets gate/up/down only (Hailo constraint). Train on Qwen2-1.5B-Instruct if heading to Hailo. Note: Hailo compile re-quantizes the adapter (INT4/INT8 group-wise) so quality must be re-evaluated post-compile.
- The Hailo compile step, not training, is the bottleneck (see HW claims above).

## 5. Plan, time, risks
Agent-work estimate (assuming user supplies access):
1. User gets Developer Zone account, downloads DFC (version matching runtime, via archive filter), Qwen2 HAR + 2 ALLS, docs: user time ~1 h.
2. Dataset generation (persona, short sentences, IDK, choose-among-references): 2-3 h.
3. QLoRA training/eval on RTX 4060 (Qwen2-1.5B): 2-3 h.
4. Linux/WSL2 or cloud GPU box setup with DFC, 128 GB-class RAM, big disk (~40 GB HAR x several): 2-4 h.
5. `load_lora_weights` -> optimize (calibration) -> compile: 4-20 h wall-clock, high failure probability; debugging 4-10 h.
6. Run on UGen300 via `LLM(..., lora_name=...)` and verify the HEF loads on HailoRT 5.3.2: 1-3 h.
Total ~15-30 agent-hours plus long compile wall-clock; realistic only if no blockers.

Blocking risks: (a) Qwen2.5-1.5B unsupported for LoRA, so the product model would switch to Qwen2 (weaker, older); (b) DFC/HAR/HailoRT version mismatches and the reported topology error and HEF_FILE_CORRUPTED failures with no confirmed fix; (c) compile hardware needs (32 GB VRAM / 128 GB RAM claims) beyond this laptop; (d) DFC is Linux-only and registration-gated; (e) hailo-ollama can't use LoRA, so the app must call the Python/C++ API; (f) no official public tutorial text accessible to me (docs behind login), so the details are second-hand.

User must do: create Hailo Developer Zone account, accept EULA, download DFC + Qwen2-1.5B HAR/ALLS (+docs/LoRA notebook, check release notes for 5.4/5.5 possibly adding Qwen2.5 LoRA); provide a Linux/WSL2 machine or rent a cloud box (large RAM/GPU); decide whether to switch base model to Qwen2-1.5B. Recommended: start the fallback (prompt + reference-selection + IDK gate) now, and treat LoRA as a parallel stretch goal with a go/no-go checkpoint after the first successful compile (~Nov 25).

Also open: ask on the Hailo community whether Qwen2.5-1.5B LoRA HAR exists in DFC 5.4/5.5 (not verified; no 5.4/5.5 release notes found publicly).
