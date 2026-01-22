"""
Enhanced Crypto Trading Bot
Dynamic ATR-based Risk Management + Multi-Channel Alerts
"""

import logging
import os
import time
import json
import argparse
from datetime import datetime
import pandas as pd

from data.multi_coin_list import COIN_CURRENCY
from data.market_data import fetch_ohlcv
from strategies.enhanced_signals import enhanced_strategy
from reports.plot_signals import plot_signals
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message
from data.last_signal_store import load_last_signals, save_last_signals
from execution.enhanced_paper_trader import execute_paper_trade, summarize_paper_trades

# Import BacktestPro from run_backtest_simple (supports risk_config dict)
from run_backtest_simple import BacktestPro

# Supabase integration
try:
    from database.supabase_db import get_active_preset, insert_backtest_result
except ImportError:
    get_active_preset = None
    insert_backtest_result = None
    print("Warning: Supabase integration not available")

# Risk config
from risk.dynamic_risk import load_enhanced_risk_config as load_config

# Directories
os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# Logging
logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DEFAULT_CURRENCY = "USD"


def send_all_alerts(message: str, coin: str = "") -> dict:
    results = {"telegram": False, "email": False, "discord": False}

    try:
        if send_discord_message(message):
            results["discord"] = True
            logging.info(f"Discord alert sent: {coin}")
    except Exception as e:
        logging.error(f"Discord failed ({coin}): {e}")

    try:
        send_telegram_message(message)
        results["telegram"] = True
        logging.info(f"Telegram alert sent: {coin}")
    except Exception as e:
        logging.error(f"Telegram failed ({coin}): {e}")

    try:
        subject = f"{coin} Signal" if coin else "Bot Alert"
        send_email(subject=subject, body=message)
        results["email"] = True
        logging.info(f"Email alert sent: {coin}")
    except Exception as e:
        logging.error(f"Email failed ({coin}): {e}")

    return results


def run_for_coin(coin: str):
    try:
        currency = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)
        df = fetch_ohlcv(symbol=coin)
        if df is None or df.empty:
            logging.warning(f"{coin}: No data")
            return

        df = enhanced_strategy(df)
        if "signal" not in df.columns:
            logging.warning(f"{coin}: No signal generated")
            return

        try:
            plot_signals(df, filename=f"{coin.replace('/', '_')}_signals.png")
        except Exception as e:
            logging.error(f"{coin}: Plot error: {e}")

        current_signal = int(df["signal"].iloc[-1])
        price = float(df["close"].iloc[-1])
        
        atr = None
        if "atr" in df.columns and not df["atr"].isna().iloc[-1]:
            atr = float(df["atr"].iloc[-1])
        
        signal_quality = None
        if "signal_quality" in df.columns and not df["signal_quality"].isna().iloc[-1]:
            signal_quality = float(df["signal_quality"].iloc[-1])

        if current_signal not in [-1, 0, 1]:
            logging.warning(f"{coin}: Invalid signal {current_signal}")
            return

        last_signals = load_last_signals()
        previous_signal = last_signals.get(coin)

        if current_signal != previous_signal:
            trade_result = execute_paper_trade(
                coin=coin,
                signal=current_signal,
                price=price,
                currency=currency,
                atr=atr
            )

            signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}
            signal_name = signal_names.get(current_signal, str(current_signal))

            message_parts = [
                f"**SIGNAL CHANGE**",
                f"Coin: {coin}",
                f"Signal: {signal_name}",
                f"Price: ${price:.2f} {currency}",
                f"Previous: {signal_names.get(previous_signal, 'None')}"
            ]
            
            if atr is not None:
                message_parts.append(f"ATR: ${atr:.2f}")
            
            if signal_quality is not None:
                message_parts.append(f"Quality: {signal_quality:.0f}/100")
            
            message_parts.append(f"\nTrade: {trade_result or 'No action'}")
            message = "\n".join(message_parts)

            alert_results = send_all_alerts(message, coin)
            alerts_sent = ", ".join(k for k, v in alert_results.items() if v)

            last_signals[coin] = current_signal
            save_last_signals(last_signals)

            log_msg = f"{coin}: {previous_signal} → {current_signal}"
            if signal_quality:
                log_msg += f" | Quality: {signal_quality:.0f}"
            log_msg += f" | Alerts: {alerts_sent}"
            
            logging.info(log_msg)
            print(f"\n{message}\nAlerts: {alerts_sent}\n")
        else:
            logging.info(f"{coin}: No change (signal {current_signal})")

    except Exception as e:
        logging.error(f"{coin} error: {e}")
        print(f"ERROR {coin}: {e}")


def check_all_positions_for_exits():
    try:
        from execution.enhanced_paper_trader import load_json, POSITIONS_FILE
        
        positions = load_json(POSITIONS_FILE, {})
        
        if not positions:
            return
        
        for coin, position in list(positions.items()):
            try:
                df = fetch_ohlcv(symbol=coin, limit=1)
                if df is None or df.empty:
                    continue
                
                current_price = float(df["close"].iloc[-1])
                sl = position.get("stop_loss")
                tp = position.get("take_profit")
                currency = position.get("currency", DEFAULT_CURRENCY)
                
                if sl and current_price <= sl:
                    logging.info(f"{coin}: Stop Loss hit at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Stop Loss hit!")
                    execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    
                elif tp and current_price >= tp:
                    logging.info(f"{coin}: Take Profit hit at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Take Profit hit!")
                    execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    
            except Exception as e:
                logging.error(f"Error checking position {coin}: {e}")
                
    except Exception as e:
        logging.error(f"Error in check_all_positions_for_exits: {e}")


def run_startup_backtest_check():
    print("\n" + "═" * 80)
    print(" STARTUP BACKTEST HEALTH CHECK ".center(80))
    print("═" * 80 + "\n")

    try:
        risk_config = None
        
        if get_active_preset:
            try:
                supabase_preset = get_active_preset("moderate")
                if supabase_preset:
                    risk_config = supabase_preset
                    print("✓ Loaded 'moderate' preset from Supabase")
                    print("Using Supabase preset for backtest")
            except Exception as e:
                print(f"Supabase preset failed: {e}")

        if risk_config is None:
            risk_config = load_config()
            print("Using local config fallback for backtest")

        if risk_config is None:
            print("No risk config available → using defaults")
            risk_config = {}

        symbol = "BTC/USDT"
        timeframe = "1h"
        limit = 3000

        print(f"Fetching {symbol} {timeframe} data for backtest...")
        df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

        if df is None or df.empty:
            print("→ No data for backtest")
            return None

        df = enhanced_strategy(df)

        print("Running backtest simulation...")
        backtester = BacktestPro(initial_balance=10000, risk_config=risk_config)
        backtester.run(df, symbol=symbol, strategy_name="Enhanced Strategy")

        # Save backtest result to Supabase
        if insert_backtest_result:
            print("\nSaving startup backtest result to Supabase...")

            try:
                df_trades = pd.DataFrame(backtester.trades) if backtester.trades else pd.DataFrame()
                total_pnl = float(df_trades['pnl'].sum()) if not df_trades.empty else 0.0
                roi = float((backtester.balance / backtester.initial_balance - 1)) if backtester.initial_balance != 0 else 0.0
                win_rate = float((df_trades['pnl'] > 0).mean()) if not df_trades.empty else 0.0
                gross_profit = float(df_trades[df_trades['pnl'] > 0]['pnl'].sum()) if not df_trades.empty else 0.0
                gross_loss = float(abs(df_trades[df_trades['pnl'] <= 0]['pnl'].sum())) if not df_trades.empty else 0.0
                profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0
                equity_curve = pd.Series([backtester.initial_balance] + backtester.equity)
                max_dd = float((equity_curve / equity_curve.cummax() - 1).min()) if len(equity_curve) > 1 else 0.0
                avg_pnl = float(df_trades['pnl'].mean()) if not df_trades.empty else 0.0

                result = {
                    "preset_id": int(2),
                    "coin_id": int(1),
                    "run_time": datetime.now().isoformat(),
                    "timeframe": str(timeframe),
                    "num_candles": int(len(df)),
                    "num_trades": int(len(backtester.trades)),
                    "win_rate": win_rate,
                    "profit_factor": profit_factor,
                    "roi": roi,
                    "max_drawdown": max_dd,
                    "avg_pnl": avg_pnl,
                    "passed": bool(roi > 0)
                }

                success = insert_backtest_result(result)
                print(f"Startup backtest saved successfully: {success}")

            except Exception as e:
                print(f"Startup backtest save failed: {e}")
                import traceback
                traceback.print_exc()

        return None

    except Exception as e:
        print(f"Backtest health check failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main(continuous: bool = False, interval: int = 300):
    # Run backtest health check at startup
    run_startup_backtest_check()

    run_count = 0

    supabase_config = None
    if get_active_preset:
        try:
            supabase_config = get_active_preset("moderate")
        except Exception:
            supabase_config = None

    if supabase_config:
        config = supabase_config
        print("\nRisk Config from Supabase:")
        print(f"  Max Positions: {config['max_positions']}")
        print(f"  Risk/Trade: {config['risk_per_trade']*100:.1f}%")
    else:
        config = load_config()

    while True:
        run_count += 1
        print(f"\n{'='*70}")
        print(f"RUN #{run_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(70))
        print(f"{'='*70}\n")

        print("Risk Config:")
        print(f"  Max Positions: {config.get('max_positions', 5)}")
        print(f"  Max Risk/Trade: {config.get('max_loss_per_trade_pct', 0.02)*100:.1f}%")
        print(f"  ATR SL: {config.get('atr_multiplier_sl', 2.0)}× | TP: {config.get('atr_multiplier_tp', 3.0)}×\n")

        for coin in COIN_CURRENCY:
            print(f"→ {coin}")
            run_for_coin(coin)
            time.sleep(1)

        print("\n→ Checking open positions for exits...")
        check_all_positions_for_exits()

        print(f"\n{'='*70}")
        summarize_paper_trades()
        print(f"{'='*70}\n")

        if not continuous:
            break

        print(f"Next run in {interval} seconds...")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=300, help="Sleep interval in seconds")
    args = parser.parse_args()

    main(continuous=not args.once, interval=args.interval)
