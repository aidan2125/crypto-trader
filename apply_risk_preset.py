#!/usr/bin/env python3
"""
Quick script to apply risk preset to risk_config.json
Usage: python apply_risk_preset.py [conservative|moderate|aggressive]
"""

import json
import sys
from pathlib import Path

RISK_CONFIG_PATH = Path("data") / "risk_config.json"

PRESETS = {
    "conservative": {
        "max_positions": 3,
        "position_size_pct": 0.05,
        "stop_loss_pct": 0.015,
        "take_profit_pct": 0.03,
        "trailing_stop_pct": 0.02,
    },
    "moderate": {
        "max_positions": 5,
        "position_size_pct": 0.10,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.05,
        "trailing_stop_pct": 0.03,
    },
    "aggressive": {
        "max_positions": 8,
        "position_size_pct": 0.15,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.10,
        "trailing_stop_pct": 0.05,
    }
}



def apply_preset(preset_name: str):
    if preset_name.lower() not in PRESETS:
        print(f"❌ Unknown preset: {preset_name}")
        print(f"Available: {', '.join(PRESETS.keys())}")
        return

    preset = PRESETS[preset_name.lower()]

    # Load existing config or create empty
    config = {}
    if RISK_CONFIG_PATH.exists():
        with open(RISK_CONFIG_PATH, 'r') as f:
            config = json.load(f)

    # Apply preset values
    old_values = {k: config.get(k) for k in preset}
    config.update(preset)

    # Save
    with open(RISK_CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

    print(f"\n✅ Applied '{preset_name}' preset")
    print("Updated parameters:")
    for k, v in preset.items():
        old = old_values.get(k)
        print(f"  {k: <25}: {old} → {v}")

    print("\nNew config saved to:", RISK_CONFIG_PATH)



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_risk_preset.py <preset>")
        print("Presets:", ", ".join(PRESETS.keys()))
        sys.exit(1)

    apply_preset(sys.argv[1])

