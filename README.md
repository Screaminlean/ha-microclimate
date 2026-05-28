<div align="center">
  <img src="https://raw.githubusercontent.com/Screaminlean/ha-microclimate/main/custom_components/ha-microclimate/images/icon_512.png" alt="HA Microclimate Logo" width="200"/>
</div>

# HA Microclimate

[![HACS](https://img.shields.io/badge/HACS-custom%20integration-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.5%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![Release](https://img.shields.io/github/v/release/Screaminlean/ha-microclimate)](https://github.com/Screaminlean/ha-microclimate/releases)
[![License](https://img.shields.io/github/license/Screaminlean/ha-microclimate)](LICENSE)
[![Issues](https://img.shields.io/github/issues/Screaminlean/ha-microclimate)](https://github.com/Screaminlean/ha-microclimate/issues)

[!NOTE]
**Disclaimer:** This is an unofficial, community-driven integration. It is not affiliated with, authorized, maintained, or endorsed by Microclimate or Blynk.

This project integrates Home Assistant with Connect-compatible devices through Blynk Cloud.

## Prerequisites

1. A Device Auth Token, you can obtain this from the [Web Dashboard](http://microclimate.blynk.cc/)
2. Home Assistant with HACS installed

## Installation

### HACS (Recommended)

1. Open HACS -> Integrations
2. Add this repository as a Custom Repository (category: Integration):
	https://github.com/Screaminlean/ha-microclimate
3. Install HA Microclimate
4. Restart Home Assistant

### Manual

Copy the integration folder into:

`custom_components/ha-microclimate`

Then restart Home Assistant.

## Configuration

1. Go to Settings -> Devices & Services
2. Click Add Integration
3. Search for HA Microclimate
4. Enter your Auth Token
5. Configure HTTP polling interval and finish pin setup

## Data Logging for Contributors

If you want to help map more pins or add support for other models, you can capture Blynk frames from the web dashboard.

Open browser dev tools on the dashboard page (F12) and run this in the console:

```javascript
(() => {
	if (window.__blynkDecodeHookInstalled) return;
	window.__blynkDecodeHookInstalled = true;

	const origDecode = TextDecoder.prototype.decode;
	const seen = [];
	window.__blynkDecoded = seen;

	function bytesToHex(u8) {
		return Array.from(u8).map(b => b.toString(16).padStart(2, "0")).join("");
	}

	TextDecoder.prototype.decode = function(input, options) {
		const out = origDecode.call(this, input, options);
		try {
			let u8 = null;
			if (input instanceof DataView) {
				u8 = new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
			} else if (input instanceof Uint8Array) {
				u8 = input;
			} else if (input instanceof ArrayBuffer) {
				u8 = new Uint8Array(input);
			}
			if (u8 && u8.length >= 6) {
				const hex = bytesToHex(u8);
				if (out.includes("5342") || out.includes("vw") || out.includes("aw") || out.includes("dw")) {
					const rec = { time: new Date().toISOString(), len: u8.length, text: out, hex };
					seen.push(rec);
					console.log("Blynk frame", rec);
				}
			}
		} catch (e) {}
		return out;
	};
	console.log("Hook installed. Make changes in the app now.");
})();
```

After performing your UI actions, export the captured frames:

```javascript
function framesToCSV(frames) {
	const rows = [];
	for (const f of frames) {
		const parts = f.text.split('\x00');
		if (parts.length >= 4 && parts[0] === '5342') {
			const pinType = parts[1];
			const pinNum = parts[2];
			const pin = pinType + pinNum;
			const value = parts.slice(3).join(' | ');
			rows.push([pin, value, f.len, f.time].join(','));
		}
	}
	return rows.join('\n');
}
console.log(framesToCSV(window.__blynkDecoded));
```

When sharing captures, please include:

1. Device model and firmware version
2. Exact action sequence (one setting change at a time)
3. The CSV output from the script
4. Any known side effects (for example, changing mode resetting schedule times or active alarms affecting values)

Use this template when posting data in issues or discussions:

```text
Model: <device model>
Firmware: <version>
Timezone: <for example Europe/London>

Test scope:
- <what setting you changed>
- <what was kept fixed>

Action sequence:
1. <starting state>
2. <single change>
3. <single change>

Known side effects during capture:
- <none OR describe schedule resets, alarm activity, page refreshes>

CSV output:
pin,value,len,time
<paste rows here>
```

## Docs

- Pin mapping CSV: [Evo_Blynk_Pins.csv](docs/Evo_Blynk_Pins.csv)

## Pin Map Generation

The integration uses a generated JSON pin map for runtime defaults (for example Select options and packed time helper defaults).

Source of truth remains CSV:

1. [docs/Evo_Blynk_Pins.csv](docs/Evo_Blynk_Pins.csv)
2. Generate JSON with:

```powershell
python scripts/generate_pin_map_json.py --csv docs/Evo_Blynk_Pins.csv --out custom_components/ha-microclimate/pin_map.json
```

## Project Identity

HA Microclimate is an independent integration with its own architecture, workflows, and roadmap.

## License

MIT License. See LICENSE.
