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
SYMBOL = "ETHUSDT"
ORDER_BALANCE_RATIO = 0.2
BTC_LEVERAGE = 4
ETH_LEVERAGE = 3
cur_balance = 0
LONG_RISK_PERCENT = 12.0
SHORT_RISK_PERCENT = 8.0
FIXED_LEVERAGE = 10
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
    global prev_balance
    raw = (await request.body()).decode("utf-8", errors="replace").strip()

    if not raw:
        return JSONResponse({"ok": False, "reason": "empty body"}, status_code=400)

    if raw == "exit_long":
        await run_in_threadpool(trading.close_position_percent, SYMBOL, "long", 100)
        return JSONResponse({"ok": True, "type": "exit_long"})

    if raw == "exit_short":
        await run_in_threadpool(trading.close_position_percent, SYMBOL, "short", 100)
        return JSONResponse({"ok": True, "type": "exit_short"})

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(
            {"ok": False, "reason": "invalid json", "raw": raw},
            status_code=400
        )

    side = data.get("side")
    entry_approx = data.get("entryApprox")
    risk_dist = data.get("riskDist")

    if side not in ("LONG", "SHORT"):
        return JSONResponse(
            {"ok": False, "reason": "unsupported side", "payload": data},
            status_code=400
        )

    try:
        entry_approx_f = float(entry_approx)
        risk_dist_f = float(risk_dist)
    except (TypeError, ValueError):
        return JSONResponse(
            {"ok": False, "reason": "invalid entryApprox or riskDist", "payload": data},
            status_code=400
        )

    if risk_dist_f <= 0 or entry_approx_f <= 0:
        return JSONResponse(
            {"ok": False, "reason": "entryApprox and riskDist must be > 0", "payload": data},
            status_code=400
        )

    # TradingView 전략의 의미상 필요한 실제 포지션 배수
    # leverage_multiple = (entry * risk%) / riskDist
    if side == "LONG":
        risk_pct = LONG_RISK_PERCENT
    else:
        risk_pct = SHORT_RISK_PERCENT
    leverage_multiple = (entry_approx_f * (risk_pct / 100.0)) / risk_dist_f

    # 현재 보유 포지션 확인
    cur_pos = await run_in_threadpool(trading.get_current_position_side, SYMBOL)

    # side -> 거래 함수 입력값 변환
    sig = "buy" if side == "LONG" else "sell"

    # 반대 포지션 있으면 먼저 정리하고 싶으면 여기에 추가 가능
    # 지금은 기존 로직처럼 포지션 없을 때만 진입
    if cur_pos != "none":
        msg = (
            f"[Bitget][ETHUSDT]\n"
            f"ENTRY SKIPPED\n"
            f"Reason: existing position\n"
            f"Current Position: {cur_pos}\n"
            f"Side: {side}\n"
            f"Entry: {fmt(entry_approx_f)}\n"
            f"RiskDist: {fmt(risk_dist_f)}\n"
            f"Required Multiple: {fmt(leverage_multiple, 2)}x"
        )
        await send_telegram_message(msg)
        return JSONResponse(
            {"ok": False, "reason": "existing position", "current_position": cur_pos},
            status_code=400
        )

    total_equity = await run_in_threadpool(trading.get_usdtm_futures_total_equity)
    total_equity = float(total_equity)
    if(total_equity >= prev_balance):
        prev_balance = total_equity
    else:
        total_equity = prev_balance

    if total_equity <= 0:
        return JSONResponse({"ok": False, "reason": "insufficient balance"}, status_code=400)

    # 항상 10배 레버리지로 진입할 때 필요한 증거금
    # notional = equity * leverage_multiple
    # margin = notional / 10
    margin_usdt = round(total_equity * leverage_multiple / FIXED_LEVERAGE, 8)

    if margin_usdt <= 0:
        return JSONResponse({"ok": False, "reason": "calculated margin <= 0"}, status_code=400)

    # 필요한 배수가 10배보다 크면 계좌 전체 증거금으로도 부족할 수 있음
    # margin_usdt > total_equity 이면 불가능
    if margin_usdt > total_equity:
        msg = (
            f"[Bitget][ETHUSDT]\n"
            f"ENTRY REJECTED\n"
            f"Reason: required margin exceeds equity\n"
            f"Side: {side}\n"
            f"Entry: {fmt(entry_approx_f)}\n"
            f"RiskDist: {fmt(risk_dist_f)}\n"
            f"Required Multiple: {fmt(leverage_multiple, 2)}x\n"
            f"Fixed Leverage: {FIXED_LEVERAGE}x\n"
            f"Equity: {fmt(total_equity)}\n"
            f"Required Margin: {fmt(margin_usdt)}"
        )
        await send_telegram_message(msg)
        return JSONResponse(
            {"ok": False, "reason": "required margin exceeds equity", "required_margin": margin_usdt},
            status_code=400
        )

    # 실제 주문 실행
    await run_in_threadpool(
        trading.place_market_order_open,
        sig,                  # "buy" or "sell"
        margin_usdt,          # 증거금
        FIXED_LEVERAGE,       # 항상 10배
        SYMBOL,
    )

    # 텔레그램 알림
    msg = (
        f"[Bitget][ETHUSDT]\n"
        f"{side} ENTRY OPENED\n"
        f"Signal Side: {side}\n"
        f"Entry: {fmt(entry_approx_f)}\n"
        f"Required Multiple: {fmt(leverage_multiple, 2)}x\n"
    )
    await send_telegram_message(msg)
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

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] LONG SL UPDATE\n"
            f"Active SL: {fmt(active_sl)}\n"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "sl_update", "side": "LONG"})

    if event_type == "SHORT_SL_UPDATE":
        active_sl = data.get("activeShortSL")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] SHORT SL UPDATE\n"
            f"Active SL: {fmt(active_sl)}\n"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "sl_update", "side": "SHORT"})

    # 3) EXIT ALERT
    if event_type == "LONG_EXIT":
        reason = data.get("reason")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] LONG EXIT\n"
            f"Reason: {reason}\n"
        )

        await send_telegram_message(msg)
        return JSONResponse({"ok": True, "type": "exit_alert", "side": "LONG"})

    if event_type == "SHORT_EXIT":
        reason = data.get("reason")

        msg = (
            f"[TEST] Binance BTCUSD 30m \n"
            f"[BTCUSD] SHORT EXIT\n"
            f"Reason: {reason}\n"
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
