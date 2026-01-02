"""
Trading Configuration Manager - CLI Tool with JSON Schema Validation
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any
import jsonschema

CONFIG_DIR = Path("config")
TRADING_CONFIG_FILE = CONFIG_DIR / "trading_config.json"
RISK_CONFIG_FILE = Path("data") / "risk_config.json"

# JSON Schemas
TRADING_SCHEMA = {
    "type": "object",
    "properties": {
        "default_trade_size": {"type": "number", "minimum": 10},
        "default_currency": {"type": "string", "enum": ["USD", "ZAR"]},
        "check_interval_seconds": {"type": "integer", "minimum": 60},
        "enable_discord_alerts": {"type": "boolean"},
        "enable_telegram_alerts": {"type": "boolean"},
        "enable_email_alerts": {"type": "boolean"},
        "auto_trade_enabled": {"type": "boolean"},
        "dry_run_mode": {"type": "boolean"},
        "max_daily_trades": {"type": "integer", "minimum": 1},
        "cooldown_after_trade_minutes": {"type": "integer", "minimum": 0},
        "signal_confirmation_required": {"type": "integer", "minimum": 1},
    },
    "required": ["default_trade_size", "default_currency", "check_interval_seconds"],
    "additionalProperties": False
}

RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "max_positions": {"type": "integer", "minimum": 1},
        "position_size_pct": {"type": "number", "minimum": 0, "maximum": 1},
        "min_trade_size": {"type": "number", "minimum": 0},
        "stop_loss_pct": {"type": "number", "minimum": 0, "maximum": 1},
        "take_profit_pct": {"type": "number", "minimum": 0, "maximum": 1},
        "trailing_stop_pct": {"type": "number", "minimum": 0, "maximum": 1},
        "trading_fee_pct": {"type": "number", "minimum": 0},
        "slippage_pct": {"type": "number", "minimum": 0},
        "max_portfolio_risk": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["max_positions", "position_size_pct", "stop_loss_pct", "take_profit_pct"],
    "additionalProperties": False
}

DEFAULT_TRADING = {
    "default_trade_size": 100,
    "default_currency": "USD",
    "check_interval_seconds": 300,
    "enable_discord_alerts": True,
    "enable_telegram_alerts": False,
    "enable_email_alerts": False,
    "auto_trade_enabled": True,
    "dry_run_mode": False,
    "max_daily_trades": 50,
    "cooldown_after_trade_minutes": 5,
    "signal_confirmation_required": 1,
}

DEFAULT_RISK = {
    "max_positions": 5,
    "position_size_pct": 0.10,
    "min_trade_size": 10,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.05,
    "trailing_stop_pct": 0.03,
    "trading_fee_pct": 0.001,
    "slippage_pct": 0.0005,
    "max_portfolio_risk": 0.20,
}

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

def validate_config(config: Dict[str, Any], schema: Dict[str, Any], config_type: str):
    """Validate config against JSON schema."""
    try:
        jsonschema.validate(instance=config, schema=schema)
    except jsonschema.ValidationError as e:
        print(f"❌ Validation error in {config_type} config: {e.message}")
        return False
    return True

def load_config(file_path: Path, default: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    if not file_path.exists():
        return default.copy()
    try:
        with open(file_path, 'r') as f:
            config = json.load(f)
            # Merge defaults and validate
            merged = {**default, **config}
            if not validate_config(merged, schema, "trading" if "default_trade_size" in merged else "risk"):
                print("Using defaults due to validation failure")
                return default.copy()
            return merged
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in {file_path}, using defaults")
        return default.copy()

def save_config(file_path: Path, config: Dict[str, Any], schema: Dict[str, Any]):
    if not validate_config(config, schema, "trading" if "default_trade_size" in config else "risk"):
        print("❌ Save aborted: Config invalid")
        return
    file_path.parent.mkdir(exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(config, f, indent=4)

def show_config():
    trading = load_config(TRADING_CONFIG_FILE, DEFAULT_TRADING, TRADING_SCHEMA)
    risk = load_config(RISK_CONFIG_FILE, DEFAULT_RISK, RISK_SCHEMA)

    print("\n" + "="*70)
    print("CURRENT CONFIGURATION".center(70))
    print("="*70)

    print("\n📊 Trading Settings")
    for k, v in trading.items():
        if isinstance(v, bool):
            v = "✅" if v else "❌"
        print(f"  {k: <30}: {v}")

    print("\n⚠️ Risk Settings")
    for k, v in risk.items():
        if k.endswith("_pct"):
            v = f"{v*100:.1f}%"
        print(f"  {k: <30}: {v}")

    print("="*70)

def set_parameter(args):
    file_path = TRADING_CONFIG_FILE if args.type == "trading" else RISK_CONFIG_FILE
    default = DEFAULT_TRADING if args.type == "trading" else DEFAULT_RISK
    schema = TRADING_SCHEMA if args.type == "trading" else RISK_SCHEMA
    config = load_config(file_path, default, schema)

    if args.param not in config:
        print(f"Error: '{args.param}' not found in {args.type} config")
        return

    old = config[args.param]
    try:
        if isinstance(old, bool):
            config[args.param] = args.value.lower() in ('true', '1', 'yes', 'on')
        elif isinstance(old, int):
            config[args.param] = int(args.value)
        elif isinstance(old, float):
            config[args.param] = float(args.value)
        else:
            config[args.param] = args.value
    except ValueError:
        print(f"Error: Invalid value '{args.value}' for {args.param}")
        return

    # Basic extra validation
    if args.param.endswith("_pct") and not 0 <= config[args.param] <= 1:
        print(f"Warning: {args.param} should be between 0 and 1")
    if args.param == "max_positions" and config[args.param] < 1:
        print("Warning: max_positions should be >= 1")

    save_config(file_path, config, schema)
    print(f"Updated {args.type}.{args.param}: {old} → {config[args.param]}")
    show_config()

def apply_preset(args):
    if args.name.lower() not in PRESETS:
        print(f"Preset '{args.name}' not found")
        print(f"Available: {', '.join(PRESETS)}")
        return

    config = load_config(RISK_CONFIG_FILE, DEFAULT_RISK, RISK_SCHEMA)
    config.update(PRESETS[args.name.lower()])
    save_config(RISK_CONFIG_FILE, config, RISK_SCHEMA)
    print(f"Applied preset '{args.name}'")
    show_config()

def reset_configs():
    if input("Reset all configs? (y/n): ").lower() != 'y':
        return
    save_config(TRADING_CONFIG_FILE, DEFAULT_TRADING, TRADING_SCHEMA)
    save_config(RISK_CONFIG_FILE, DEFAULT_RISK, RISK_SCHEMA)
    print("All configs reset")
    show_config()

def main():
    parser = argparse.ArgumentParser(description="Trading Config Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show", help="Display current config")

    set_parser = subparsers.add_parser("set", help="Change a parameter")
    set_parser.add_argument("type", choices=["trading", "risk"])
    set_parser.add_argument("param")
    set_parser.add_argument("value")

    preset_parser = subparsers.add_parser("preset", help="Apply risk preset")
    preset_parser.add_argument("name", nargs="?", default=None)

    subparsers.add_parser("reset", help="Reset to defaults")

    args = parser.parse_args()

    if args.command == "show":
        show_config()
    elif args.command == "set":
        set_parameter(args)
    elif args.command == "preset":
        if args.name:
            apply_preset(args)
        else:
            print("Available presets:", ", ".join(PRESETS))
    elif args.command == "reset":
        reset_configs()

if __name__ == "__main__":
    main()