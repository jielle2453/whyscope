# Hardware (Stage II target)

Stage I runs on a laptop. Stage II moves the hub to a small appliance. Nothing below has been built or tested yet;
treat it as a bill of materials and an assembly plan to verify during Stage II week 1.

## Bill of materials

| part | spec | note |
|---|---|---|
| Computer | Raspberry Pi 5, 8 GB | 8 GB leaves room for Whisper-class ASR plus the LLM host process |
| Power | official Raspberry Pi 27 W USB-C PSU | the accelerator and USB audio need the full 5 A budget; weak supplies cause brown-outs |
| Cooling | official Raspberry Pi Active Cooler | ASR and the LLM keep the CPU busy; avoid thermal throttling in a closed enclosure |
| Storage | microSD, A2, 64 GB or larger | or an NVMe drive if the M.2 slot is not used by the accelerator |
| AI accelerator | ASUS UGen300 (Hailo-10H) | see the form-factor warning below |
| M.2 carrier | see "M.2 length" below | only needed if the UGen300 is an M.2 module |
| Camera | USB webcam, UVC, 1080p | used for single JPEG frames, not video streaming |
| Audio | USB speakerphone (mic + speaker, echo cancelling) | one device for both directions; keeps the child's voice close to the mic |
| Enclosure | 3D-printed or off-the-shelf case with airflow | Stage II week 4 |

### Form-factor warning (confirm before buying)

The plan assumes an **M.2 UGen300**. Check the ASUS datasheet and the exact SKU first. ASUS has marketed the
UGen300 as a **USB** accelerator. If yours is USB, ignore the M.2 carrier row and plug it into a Pi 5 USB 3.0 port;
the HailoRT driver path and the throughput budget then differ from the PCIe path, which is exactly what the week-1
"USB/PCIe GenAI check" in the [roadmap](roadmap.md) is for.

### M.2 length (only if the module is M.2)

Confirm whether the UGen300 module is **2242 or 2280**.

- The official **Raspberry Pi M.2 HAT+** supports **2230 and 2242** only. A 2280 module will not fit.
- For 2280, use a third-party board such as the **Pimoroni NVMe Base** or the **Geekworm X1001**.
  Check that the board's PCIe lanes and any keying match what the module needs (an NVMe-oriented carrier is a
  PCIe x1 slot; an accelerator that expects more lanes will still run at x1).

## Assembly steps

1. Fit the Active Cooler to the Pi 5 (thermal pad down, fan connector to the FAN header).
2. Flash Raspberry Pi OS (64-bit, Bookworm or newer) to the microSD with Raspberry Pi Imager; set hostname, user,
   Wi-Fi and SSH in the Imager's advanced options.
3. M.2 route: mount the HAT or carrier on the GPIO standoffs, connect the PCIe FFC cable to the Pi 5 PCIe port
   (lift the latch, insert the cable fully, close the latch), seat the module and fix it with the screw.
   USB route: skip this step.
4. Connect the USB webcam and USB speakerphone to the **blue USB 3.0** ports if the accelerator is not using them;
   if the accelerator is USB, give it a blue port and put webcam and speakerphone on the other blue port via a powered hub.
5. Connect the 27 W PSU last. Boot, then `sudo apt update && sudo apt full-upgrade -y && sudo reboot`.
6. For M.2, enable PCIe in `/boot/firmware/config.txt` (`dtparam=pciex1`, and `dtparam=pciex1_gen=3` only after
   the link is stable at gen 2). Reboot.

## Install HailoRT

Follow Hailo's own Raspberry Pi documentation for the exact packages for your device generation (the Hailo-10H
needs the HailoRT 5.x line and the GenAI model zoo; the older Hailo-8 AI Kit uses `hailo-all`). Start from:

- Hailo Developer Zone, Raspberry Pi 5 getting started: https://hailo.ai/developer-zone/
- Raspberry Pi AI documentation: https://www.raspberrypi.com/documentation/computers/ai.html

Then verify:

```
hailortcli fw-control identify     # device is visible, firmware version printed
hailortcli scan                    # PCIe or USB device listed
```

Record the HailoRT version, firmware version and the exact commands that worked in `docs/benchmarks.md`.

## Install Whyscope on the Pi

```
git clone <repo> whyscope && cd whyscope
scripts/install.sh --cpu          # CPU path first, to prove the hub runs on the Pi
# edit config.yaml: mode: hailo   (Stage II code; falls back to cpu behaviour today)
scripts/run.sh
```

Open `http://localhost:8000/kid` on a screen attached to the Pi, or serve the pages over HTTPS for other devices
(browsers block microphone access on plain HTTP outside localhost).

## Fallback: UGen300 on an x86 Linux mini PC

If the Pi 5 cannot drive the accelerator well enough (USB bandwidth, PCIe x1 limits, driver support), run the same
hub on an x86 Linux mini PC (for example an N100-class machine with 16 GB RAM) and plug the **USB** UGen300 into it.
The hub is plain Python and does not care about the CPU architecture. The Stage II metrics are then reported for the
mini PC, and the Pi result is documented as a negative finding with its cause.
