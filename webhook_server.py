# webhook_server.py
import uvicorn
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
import trading
from message import send_telegram_message
from db import DB

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
    
    await send_telegram_message(f"[BTCUSDT]\n{raw}")
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
    
    await send_telegram_message(f"[ETHUSDT]\n{raw}")
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    cur_balance = trading.get_usdtm_futures_balance()
    uvicorn.run(app, host="0.0.0.0", port=8000)
