# webhook_server.py
import uvicorn
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
import trading
from message import send_telegram_message
from db import DB
import json

app = FastAPI()

# ===== 기존 상태 유지 =====
prev_balance = 0.0
win = 0
lose = 0

# ===== DB =====
db = DB()
db.init_schema()

BOT_ID = "pc01"
BTC_SYMBOL = "BTCUSDT"
ETH_SYMBOL = "ETHUSDT"
ORDER_BALANCE_RATIO = 0.2
BTC_LEVERAGE = 4
ETH_LEVERAGE = 3
cur_balance = 0
SIGNAL_MAP = {
    "buy": "buy",
    "sell": "sell",
    "exit_long": "exit",
    "exit_short": "exit",
}

def extract_order_id(resp):
    if isinstance(resp, dict):
        d = resp.get("data")
        if isinstance(d, dict):
            return d.get("orderId") or d.get("clientOid")
    return None


@app.post("/webhook")
async def handle_webhook(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")

    sig = SIGNAL_MAP.get(raw)
    if sig is None:
        return JSONResponse({"ok": False, "reason": "unsupported signal"}, status_code=400) 

    cur_pos = await run_in_threadpool(trading.get_current_position_side, BTC_SYMBOL)

    if sig in ("buy", "sell"):
        if cur_pos == "none":
            total_equity = await run_in_threadpool(trading.get_usdtm_futures_total_equity)
            margin_usdt = round(total_equity * ORDER_BALANCE_RATIO, 8)
            if margin_usdt <= 0:
                return JSONResponse({"ok": False, "reason": "insufficient balance"}, status_code=400)
            await run_in_threadpool(
                trading.place_market_order_open,
                sig,
                margin_usdt,
                BTC_LEVERAGE,
                BTC_SYMBOL,
            )
    else:
        if cur_pos in ("long", "both"):
            await run_in_threadpool(trading.close_position_percent, BTC_SYMBOL, "long", 100)
        if cur_pos in ("short", "both"):
            await run_in_threadpool(trading.close_position_percent, BTC_SYMBOL, "short", 100)
    
    await send_telegram_message(f"[Bitget][BTCUSDT]\n{raw}")
    return JSONResponse({"ok": True})


@app.post("/webhook2")
async def handle_webhook2(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")

    sig = SIGNAL_MAP.get(raw)
    if sig is None:
        return JSONResponse({"ok": False, "reason": "unsupported signal"}, status_code=400) 

    cur_pos = await run_in_threadpool(trading.get_current_position_side, ETH_SYMBOL)

    if sig in ("buy", "sell"):
        if cur_pos == "none":
            total_equity = await run_in_threadpool(trading.get_usdtm_futures_total_equity)
            margin_usdt = round(total_equity * ORDER_BALANCE_RATIO, 8)
            if margin_usdt <= 0:
                return JSONResponse({"ok": False, "reason": "insufficient balance"}, status_code=400)
            await run_in_threadpool(
                trading.place_market_order_open,
                sig,
                margin_usdt,
                ETH_LEVERAGE,
                ETH_SYMBOL,
            )
    else:
        if cur_pos in ("long", "both"):
            await run_in_threadpool(trading.close_position_percent, ETH_SYMBOL, "long", 100)
        if cur_pos in ("short", "both"):
            await run_in_threadpool(trading.close_position_percent, ETH_SYMBOL, "short", 100)
    
    await send_telegram_message(f"[Bitget][ETHUSDT]\n{raw}")
    return JSONResponse({"ok": True})


def fmt(v, nd=4):
    if v is None:
        return "None"
    try:
        return f"{float(v):.{nd}f}"
    except Exception:
        return str(v)


@app.post("/webhook3")
async def handle_webhook3(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace").strip()

    if not raw:
        return JSONResponse({"ok": False, "reason": "empty body"}, status_code=400)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(
            {"ok": False, "reason": "invalid json", "raw": raw},
            status_code=400
        )

    event_type = data.get("event")
    side = data.get("side")

    # 1) ENTRY ALERT
    if side in ("LONG", "SHORT") and event_type is None:
        pos_size = data.get("posSize")
        risk_dist = data.get("riskDist")
        stop_loss = data.get("stopLoss")
        take_profit = data.get("takeProfit")
        entry_approx = data.get("entryApprox")

        assumed_equity = 100.0
        risk_percentage = 6.0
        assumed_risk_amount = assumed_equity * (risk_percentage / 100.0)

        calc_pos_size = None
        position_notional = None
        leverage_multiple = None

        try:
            risk_dist_f = float(risk_dist)
            entry_approx_f = float(entry_approx)

            if risk_dist_f > 0:
                # 자산 100, 리스크 6% 기준으로 새로 계산
                calc_pos_size = assumed_risk_amount / risk_dist_f
                position_notional = calc_pos_size * entry_approx_f
                leverage_multiple = position_notional / assumed_equity
        except Exception:
            pass

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] {side} ENTRY\n"
            f"Entry: {fmt(entry_approx)}\n"
            f"SL: {fmt(stop_loss)}\n"
            f"TP: {fmt(take_profit)}\n"
            f"Required Multiple: {fmt(leverage_multiple, 2)}x"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "entry_alert", "side": side})

    # 2) STOP LOSS UPDATE ALERT
    if event_type == "LONG_SL_UPDATE":
        active_sl = data.get("activeLongSL")
        trail_sl = data.get("trailLongSL")
        avg_price = data.get("avgPrice")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] LONG SL UPDATE\n"
            f"AvgPrice: {fmt(avg_price)}\n"
            f"Active SL: {fmt(active_sl)}\n"
            f"Trail SL: {fmt(trail_sl)}"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "sl_update", "side": "LONG"})

    if event_type == "SHORT_SL_UPDATE":
        active_sl = data.get("activeShortSL")
        trail_sl = data.get("trailShortSL")
        avg_price = data.get("avgPrice")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] SHORT SL UPDATE\n"
            f"AvgPrice: {fmt(avg_price)}\n"
            f"Active SL: {fmt(active_sl)}\n"
            f"Trail SL: {fmt(trail_sl)}"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "sl_update", "side": "SHORT"})

    # 3) EXIT ALERT
    if event_type == "LONG_EXIT":
        reason = data.get("reason")
        exit_price = data.get("exitPrice")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] LONG EXIT\n"
            f"Reason: {reason}\n"
            f"ExitPrice: {fmt(exit_price)}"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "exit_alert", "side": "LONG"})

    if event_type == "SHORT_EXIT":
        reason = data.get("reason")
        exit_price = data.get("exitPrice")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] SHORT EXIT\n"
            f"Reason: {reason}\n"
            f"ExitPrice: {fmt(exit_price)}"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "exit_alert", "side": "SHORT"})

    return JSONResponse(
        {"ok": False, "reason": "unsupported payload", "payload": data, "raw": raw},
        status_code=400
    )

if __name__ == "__main__":
    cur_balance = trading.get_usdtm_futures_balance()
    uvicorn.run(app, host="0.0.0.0", port=8000)
