# Hardware (Stage II)

Stage II runs the hub on an ordinary x86 laptop with an **ASUS UGen300 USB** (Hailo-10H, 8 GB LPDDR4, USB 3.1 Gen 2
Type-C). No custom hardware is built in this stage. **Verified setup: Windows 11, HailoRT 5.3.2.** Everything in
"Windows: what worked" below was run and measured on the device (2026-11-13/14); numbers are in
[benchmarks.md](benchmarks.md) and [ugen.md](ugen.md). The "Day one" checklist and the Ubuntu notes further down are the
generic/Linux path: the repo ships Linux scripts (`scripts/install.sh`, `run.sh`, `check_ugen.sh`) and the hub code has no
OS-specific branches, but **Ubuntu has not been run on the UGen300 by us**.

## What we use

| part | spec | note |
|---|---|---|
| AI accelerator | ASUS UGen300 USB (UGen300-USB-8G), Hailo-10H | one device; only ONE process can open it |
| Host (verified) | ASUS TUF Gaming A16 FA607PV laptop, Windows 11 Home | HailoRT 5.3.2; hub venv `C:\whyscope-venv` (Python 3.14); HailoRT venv `C:\whyscope-hailo-venv` (Python 3.13, cp313 wheel) |
| Host (secondary, untested) | x86 laptop/desktop, Ubuntu 24.04 LTS | ASUS publishes Linux drivers; not yet run by us |
| Phone | any phone with a browser | interface only: microphone, camera, speaker, screen |
| USB power meter | USB-C inline meter | energy per question (metric 5) |

The two Python venvs exist because the HailoRT wheels cover Python 3.10-3.13 while the hub's dependencies run on 3.14.
`hub/hailo_worker.py` (HailoRT venv, `127.0.0.1:8711`) is the single device-manager process: it holds one shared VDevice
with **four HEFs at once**: LLM (Qwen2.5-1.5B), Whisper-Small, YOLOv8s and the CLIP ViT-B/32 image encoder. A second process
cannot open the USB device (`LIBUSB_ERROR_ACCESS`). Measured: Whisper-Small English WER 1.4%, about 1.0-1.2 s per clip;
Whisper-Base 3.4%, 0.5 s; Chinese CER 10.7-15.3% on the UGen against 2.7% for faster-whisper on CPU, so Chinese ASR stays on
the CPU; vision about 20 ms; LLM load 8-12 s, Whisper-Small load 3.2 s. All tests ran on a USB-C port advertising only 1.5 A.
ASUS publishes drivers for Windows 10/11 and for x86 Linux (Ubuntu 22.04 / 24.04) on the
[UGen300-USB-8G support page](https://www.asus.com/motherboards-components/ai-accelerator/ugen/ugen300-usb-8g/helpdesk_download/?model2Name=UGen300-USB-8G).

## Future hardware (not built, not tested)

* **Dedicated box:** Raspberry Pi Compute Module 5 + Hailo-10H M.2 on a custom carrier board, always-on at home (see
  [business.md](business.md), [roadmap.md](roadmap.md)).
* **Prototype for that box:** Raspberry Pi 5 + AI HAT+ 2. Nothing in this repo has been run on either; the UGen300 on a
  Windows 11 laptop is the only hardware that has been measured.

## Windows: what worked (2026-11-13, Windows 11 Home, HailoRT 5.3.2)

1. Plug in the UGen300 with the bundled cable, no hub. Device Manager shows "UGen300 USB Loader" with an error until
   the driver is installed (USB `VID_0B05&PID_1D6F`).
2. Download `UGen300_USB_5.3.2_driver_Windows_amd64.zip` from the ASUS support page (check its SHA-256 against the
   page) and install `HailoRT_5.3.2_windows_installer.msi` with **all** components, for example from an administrator
   prompt: `msiexec /i HailoRT_5.3.2_windows_installer.msi /qb ADDLOCAL=ALL`. No reboot was needed.
3. The device becomes "UGen300 USB AI Accelerator (Hailo-10H)", status OK, and the `hailo_usb_service` service runs.
4. `hailortcli scan` lists `usb/003:002`; `hailortcli fw-control identify` prints Firmware Version 5.3.2 and
   Device Architecture HAILO10H. The firmware already matched the runtime, so the "Hailo USB FW Update" tool was not needed.
   It warned that the USB-C port advertises only 1.5 A and the module "may run in reduced-performance mode"; use a port
   that advertises 3.0 A for benchmarks. On the test laptop (ASUS TUF Gaming A16 FA607PV, BIOS 311) **both** USB-C
   ports advertise 1.5 A, even with the charger connected; the advertised current is set by the port hardware, not by a
   Windows setting. All Windows numbers in benchmarks.md were measured at 1.5 A.
5. The Python wheels in `C:\Program Files\HailoRT\python` cover Python 3.10 to 3.13 (not 3.14):
   `py install 3.13`, `py -V:3.13 -m venv C:\whyscope-hailo-venv`, then
   `pip install "C:\Program Files\HailoRT\python\hailort-5.3.2-cp313-cp313-win_amd64.whl"` (plus the matching numpy wheel).
6. Model: start `hailo-ollama.exe` (listens on 0.0.0.0:8000, so stop it before running the hub on the same port) and
   pull `qwen2.5:1.5b` (`POST /api/pull`). The 2.35 GB HEF lands in
   `%LOCALAPPDATA%\hailo-ollama\models\blob\sha256_0856a10c...` and is used directly as `hailo.llm_hef`. The download
   ran at about 0.35 MB/s and took about 65 minutes.
7. `python scripts\check_ugen.py --hef <that file>` loads the model in about 7.5 s and runs Whyscope compose on the device.
8. **Hub on another Python (verified 2026-11-14).** The hub's dependencies (torch, faster-whisper, sentence-transformers)
   were installed in a Python 3.14 venv, and the HailoRT wheel needs 3.13. Instead of reinstalling, the UGen300 runs in a
   small worker on the 3.13 venv and the hub talks to it on localhost:
   ```
   C:\whyscope-hailo-venv\Scripts\python -m hub.hailo_worker     # loads the HEF (8 s), listens on 127.0.0.1:8711 only
   # config.yaml: mode: hailo, hailo.llm_hef: <HEF from step 6>, hailo.worker: http://127.0.0.1:8711
   scripts\run.ps1                                                  # the hub, on its own venv
   ```
   The worker exposes the same three calls as `HailoLLM` (load, prime, complete); the stop rule travels as data
   (`hailo.stopper`). Without `hailo.worker` the hub loads the HEF in-process as before. End to end through the hub:
   about 4.2 s (age 6) to 5.7 s (age 7-8) per full answer, the first sentence in under 25 ms (text questions).
9. **The worker as the UGen300's device manager (verified 2026-11-14).** Only one process can open the USB device (a
   second one fails with LIBUSB_ERROR_ACCESS), so the worker is the one owner and the hub never touches the device. On
   start it loads, on one VDevice, every model whose key is set: `hailo.llm_hef`, `hailo.whisper_hef`, `hailo.yolo_hef`,
   `hailo.clip_image_hef` (about 16 s in all: LLM 8-12 s, Whisper-Small 3.2 s, Base 1.5 s, yolov8s 0.3 s, CLIP 0.6 s).
   A model that fails to load is listed with its error in `POST /info` and the others still work. Endpoints (all
   127.0.0.1 only): `/info`, `/prime`, `/complete`, `/transcribe?lang=en` (raw float32 mono 16 kHz PCM in, `{"text","ms"}`
   out), `/detect` and `/clip_image` (a JPEG, or a preprocessed uint8 array with `Content-Type: application/x-raw-u8`;
   the HailoRT venv has no Pillow, so the hub preprocesses and sends the array: 640x640 letterbox for yolo, 224x224
   crop for CLIP). LLM and Whisper calls are serialized (`GENAI_LOCK`), each vision model has its own lock.
   Hub side: `listen.backend_by_lang: {en: hailo, zh: faster-whisper}`; if the worker is down or errors, that request
   is answered by faster-whisper, vision falls back to the hub's own models, compose to the template, and everything
   comes back when the worker is restarted (no hub restart). `/healthz` has a `ugen` block (worker reachable, models
   loaded, ASR per language with the backend that answered last, vision, compose) and an honest `vision` block.
   Vision: yolov8s picks the main object, the UGen CLIP image encoder (OpenAI ViT-B/32) embeds the crop, and the
   precomputed label table (`vision.clip_labels`) picks the KB entry; no CLIP text encoder runs in the hub.
   Measured through the hub (50 English clips, voice question to first sentence, then waiting for each answer):

   | English ASR | listen p50 / p95 | first sentence p50 / p95 | WER (step 0) |
   |---|---|---|---|
   | Hailo Whisper-Small (chosen) | 1.05 s / 4.9 s | 1.07 s / 5.0 s | 1.4% |
   | Hailo Whisper-Base | 0.45 s / 0.55 s | 0.47 s / 0.57 s | 3.4% |
   | faster-whisper small, CPU | 1.5 s / 4.1 s | 1.56 s / 4.2 s | (step 0: CPU reference) |

   The p95 tails (about 4-5 s) appear when the previous answer's LLM call is still running on the worker or the CPU, in
   both the Hailo and the CPU runs; they are not the ASR itself (idle Small is 0.9-1.2 s). Small was kept: the first
   word is about 0.6 s later than with Base, but it halves the error rate. Chinese stays on faster-whisper
   (about 1.2-1.6 s per question). Vision through the worker: yolov8s 23-28 ms and CLIP image 20-22 ms on the device;
   a photo through the hub (decode, letterbox, both models, label pick) takes 55-120 ms. With the worker down: ASR
   answered by faster-whisper, template answers; a voice+photo question took 12-15 s (CPU YOLO and Whisper loads), back
   to about 5 s (voice, photo, LLM answer) once the worker was up again.

## Day one: bring-up checklist (generic / Linux; the Windows path is above)

Do these in order and stop at the first step that fails.

1. **Plug in** the UGen300 to a USB-C port that supports at least 10 Gbps (USB 3.1/3.2 Gen 2), not through a hub.
2. **See it on the bus:** `lsusb` lists a new device. Write down its ID line.
3. **Install HailoRT 5.x** from the ASUS UGen300 download page or the Hailo Developer Zone
   (https://hailo.ai/developer-zone/), following the ASUS guide for the **USB** version. The Hailo-10H needs the
   **5.x** line; 4.x is for Hailo-8 and fails with "not enough free devices".
4. **Talk to it:**
   ```
   hailortcli scan                    # the device is listed
   hailortcli fw-control identify     # firmware version printed
   ```
   A permission error usually means the udev rules from the HailoRT package are not installed or not reloaded
   (`sudo udevadm control --reload-rules && sudo udevadm trigger`, then unplug and plug again).
5. **Python binding:** install the HailoRT Python wheel that matches the HailoRT version and your Python version, then
   `python3 -c "from hailo_platform import VDevice; from hailo_platform.genai import LLM; print('ok')"`.
6. **GenAI sample:** install the Hailo GenAI model zoo package and run the ASUS LLM tutorial (or Hailo's
   `simple_llm_chat`). Note the HEF file it downloads for `qwen2.5-instruct:1.5b` and put its path in `config.yaml` under
   `hailo.llm_hef`.
7. **Whyscope check:** `scripts/check_ugen.sh` repeats steps 2, 4 and 5; `scripts/check_ugen.sh --compose` also sends
   three Whyscope compose requests to the UGen300 and prints their times.
8. **Record** the HailoRT version, firmware version, HEF file names and the exact commands that worked in
   [benchmarks.md](benchmarks.md).

## Run Whyscope on the UGen300

```
git clone https://github.com/jielle2453/whyscope && cd whyscope
scripts/install.sh --cpu          # hub dependencies (Windows: scripts\install.ps1); also start the worker, see step 8-9
# config.yaml: mode: hailo, and hailo.llm_hef: <path from step 6>
python3 scripts/make_cert.py      # once: self-signed certificate so phones can use the microphone
scripts/run.sh                    # serves https://<host-ip>:8000 when certs/ exists
```

Open `https://<host-ip>:8000/kid` on the phone, accept the certificate warning once, and allow the microphone.

### Port clash with hailo-ollama

`hailo-ollama` (Hailo's Ollama-compatible server) also listens on port 8000 by default. The hub does not need it: in
`mode: hailo` it uses the LLM HEF directly (through the worker, or in-process without `hailo.worker`). If you run hailo-ollama anyway, start the hub
on another port (`WHYSCOPE_PORT=8443 scripts/run.sh`).

### One device, one GenAI model at a time

The worker (or the in-process hub) opens a single shared `VDevice` (`hub/hailo.py`) and runs Hailo GenAI calls (LLM and
Whisper) one at a time behind `GENAI_LOCK`: they must not generate in parallel on the same device. Vision models have their
own locks. Do not start a second Python process that opens the device while the worker runs.

## Multi-host test (W3)

The UGen300 has no storage of its own, so the child's settings, the KB version and the log do not live on it. Each host
keeps a hub; the **state bundle** (export from one hub, import into the next) carries them. The test: answer questions on
host 1, export, unplug the UGen300, plug it into host 2, import, and time the first answer there.

## Android (detection only)

Android support for the UGen300 is offered to B2B partners only, and the USB firmware loader is not available for ARM,
so the AI cannot run on a phone in Stage II. The only check: connect the UGen300 to an Android phone with a USB-C cable
and see with a USB device info app whether the phone detects and powers it. Record the result either way.
