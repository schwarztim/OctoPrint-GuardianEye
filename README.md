# GuardianEye — AI Print Failure Detection for OctoPrint

**Open-source, no subscription, 6 AI providers including 100% local/free with Ollama.**

GuardianEye watches your 3D prints through your webcam and uses AI vision to detect failures like spaghetti, bed detachment, and printing into air. When it sees a problem, it stops your print automatically — saving filament, time, and your sanity.

## Why GuardianEye over Obico / The Spaghetti Detective?

| Feature                     | GuardianEye                                        | Obico/TSD                            |
| --------------------------- | -------------------------------------------------- | ------------------------------------ |
| **Cost**                    | Free (open source, AGPLv3)                         | $4-12/month subscription             |
| **AI Providers**            | 6 (OpenAI, Azure, Anthropic, Grok, Gemini, Ollama) | Proprietary only                     |
| **Fully Offline**           | Yes, via Ollama                                    | No (or self-host their heavy server) |
| **Strike System**           | Configurable 1-10 strikes                          | Fixed internal logic                 |
| **Custom Prompts**          | Full prompt editor                                 | Not available                        |
| **Cost Tracking**           | Per-call cost estimation                           | N/A                                  |
| **False Positive Tracking** | Mark & track FP rate                               | Not available                        |
| **Transparency**            | See every verdict, reason, confidence              | Black box                            |

## Features

- **6 AI Vision Providers** — OpenAI, Azure OpenAI, Anthropic Claude, xAI Grok, Google Gemini, Ollama (local)
- **Configurable Strike System** — 1-10 consecutive failures needed before stopping (default: 3)
- **Stage-Aware Prompts** — Different detection sensitivity for early, mid, and late print stages
- **Battle-Tested Prompt** — Tuned to ignore pre-existing debris, purge blobs, and glue residue (the "poop test")
- **Real-Time Dashboard** — Live sidebar with status, strikes, snapshot thumbnail, and verdict
- **History Tab** — Full verdict history with thumbnails, confidence scores, latency, and cost
- **False Positive Tracking** — Mark false positives, track your FP rate over time
- **API Cost Tracking** — See exactly what each check costs (Ollama = always $0.00)
- **Multi-Channel Notifications** — Discord, Telegram, webhook (Home Assistant/IFTTT), OctoPrint popup
- **Custom Prompt Editor** — Full control over the AI prompt for power users
- **Auto-Start** — Monitoring begins automatically when a print starts

## Installation

### From OctoPrint Plugin Manager

1. Open OctoPrint Settings > Plugin Manager > Get More...
2. Paste this URL:
   ```
   https://github.com/schwarztim/OctoPrint-GuardianEye/archive/main.zip
   ```
3. Click Install

### From pip

```bash
pip install https://github.com/schwarztim/OctoPrint-GuardianEye/archive/main.zip
```

### For development

```bash
cd OctoPrint-GuardianEye
pip install -e .
```

## Quick Start

1. **Install the plugin** (see above)
2. **Choose a provider** in Settings > GuardianEye:
   - **Cheapest cloud:** Gemini (`gemini-2.0-flash`) — ~$0.0001/check
   - **Best balance:** OpenAI (`gpt-4o-mini`) — ~$0.0003/check
   - **Fully free/offline:** Ollama (`llava`) — $0.00/check
3. **Enter your API key** (not needed for Ollama)
4. **Click "Test Connection"** to verify it works
5. **Start a print** — monitoring begins automatically

## Supported Providers

| Provider          | Default Model            | ~Cost/Check | API Key Required | Notes                        |
| ----------------- | ------------------------ | ----------- | ---------------- | ---------------------------- |
| **OpenAI**        | gpt-4o-mini              | $0.0003     | Yes              | Best balance of cost/quality |
| **Azure OpenAI**  | gpt-4o-mini              | $0.0003     | Yes              | Enterprise/compliance needs  |
| **Anthropic**     | claude-sonnet-4-20250514 | $0.005      | Yes              | Highest quality analysis     |
| **xAI / Grok**    | grok-2-vision-latest     | $0.005      | Yes              | X.ai platform                |
| **Google Gemini** | gemini-2.0-flash         | $0.0001     | Yes              | Cheapest cloud option        |
| **Ollama**        | llava                    | $0.00       | No               | 100% local, fully offline    |

### Setting Up Ollama (Free/Offline)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a vision model
ollama pull llava

# That's it! Select "Ollama" in GuardianEye settings
```

## How It Works

### The 3-Strike System

GuardianEye doesn't stop your print on a single bad frame. Instead:

1. **Snapshot** — Captures a webcam image on a configurable interval (default: 60s)
2. **AI Analysis** — Sends the image + context-aware prompt to your chosen AI provider
3. **Verdict** — AI returns `OK` or `FAIL` with a reason
4. **Strike Counter** — `FAIL` increments the counter; `OK` resets it to zero
5. **Emergency Stop** — Only after N consecutive FAILs (default: 3) does it stop the print

This means a single ambiguous frame won't kill your print, but persistent spaghetti will be caught quickly.

### Stage-Aware Detection

The AI prompt adapts to the print stage:

- **Early (layer 1-5):** "Very little material is visible — this is NORMAL"
- **Mid:** "Objects should be visibly forming with stacked layers"
- **Late (>80%):** "Objects should be nearly complete with full height"

### The "Poop Test"

Our prompt is specifically trained to handle pre-existing debris on the bed:

> _ANY pre-existing objects, blobs, filament scraps, or debris sitting on the bed — these are leftovers from previous prints and are completely NORMAL._

This prevents false positives from old purge blobs, failed print remnants, or general bed mess.

## Settings Reference

| Setting                | Default | Description                            |
| ---------------------- | ------- | -------------------------------------- |
| **Enabled**            | On      | Master enable/disable                  |
| **Auto Start**         | On      | Start monitoring when print begins     |
| **Provider**           | openai  | AI vision provider                     |
| **Interval**           | 60s     | Seconds between checks (min 10)        |
| **Min Layer**          | 2       | Skip vision analysis before this layer |
| **Fail Strikes**       | 3       | Consecutive FAILs needed to stop       |
| **Layer Height**       | 0.2mm   | Used to estimate layer from Z height   |
| **Snapshot Retention** | 100     | Max snapshots kept on disk             |
| **Custom Prompt**      | (empty) | Override the default AI prompt         |
| **Cost Tracking**      | On      | Track per-call API costs               |

## Notifications

Configure in Settings > GuardianEye > Notifications:

- **OctoPrint Popup** — Always-on PNotify alert
- **Webhook** — POST JSON to any URL (Home Assistant, IFTTT, n8n)
- **Discord** — Webhook with red embed + snapshot attachment
- **Telegram** — Bot message with snapshot photo

## Cost Estimates

Running at default 60s interval during an 8-hour print (~480 checks):

| Provider  | Model            | Per Check | 8hr Print |
| --------- | ---------------- | --------- | --------- |
| Gemini    | gemini-2.0-flash | $0.0001   | ~$0.05    |
| OpenAI    | gpt-4o-mini      | $0.0003   | ~$0.14    |
| OpenAI    | gpt-4.1-mini     | $0.0003   | ~$0.14    |
| Anthropic | claude-haiku-4-5 | $0.001    | ~$0.48    |
| Anthropic | claude-sonnet-4  | $0.005    | ~$2.40    |
| Ollama    | llava            | $0.00     | $0.00     |

## FAQ

**Q: Will this work with my webcam?**
A: If your webcam serves JPEG snapshots via HTTP (like mjpeg-streamer), yes. This covers most OctoPrint webcam setups.

**Q: Does it work without internet?**
A: Yes, if you use Ollama. All other providers require internet access.

**Q: What happens if the AI API is down?**
A: API errors are non-fatal. The print continues; the check is simply skipped.

**Q: Can I use this with OctoPrint's built-in webcam?**
A: Yes. GuardianEye auto-detects your OctoPrint webcam snapshot URL.

**Q: How do I reduce false positives?**
A: Increase the strike count (e.g., 5 instead of 3), or use a more capable model. Mark false positives to track your FP rate.

## Architecture

```
OctoPrint Event (PrintStarted)
    → PrintMonitor.start()
        → RepeatedTimer(60s)
            → capture_snapshot(webcam_url)
            → build_vision_prompt(layer, progress)
            → VisionProvider.analyze(image, prompt)
            → Strike system (FAIL → increment, OK → reset)
            → 3 strikes → printer.cancel_print() + notify
            → send_plugin_message() → Knockout.js UI update
```

## Contributing

Contributions welcome! This is AGPLv3 — please keep it open.

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Test with `pip install -e .` in an OctoPrint dev environment
5. Open a PR

## License

[GNU Affero General Public License v3.0](LICENSE)

---

Built with frustration from too many spaghetti prints and inspired by the AI vision monitor in [bambu-lab-mcp](https://github.com/schwarztim/bambu-lab-mcp).
