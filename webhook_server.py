# webhook_server.py
import uvicorn
from fastapi import FastAPI, Request
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
SYMBOL = "BTCUSDT"
MARGIN_USDT = 50.0
LEVERAGE = 50


def extract_order_id(resp):
    if isinstance(resp, dict):
        d = resp.get("data")
        if isinstance(d, dict):
            return d.get("orderId") or d.get("clientOid")
    return None


@app.post("/webhook")
async def handle_webhook(request: Request):
    global prev_balance, win, lose

    raw = (await request.body()).decode("utf-8", errors="replace")
    await send_telegram_message(f"[Bot Alert]\n{raw}")

    # ===== signal =====
    if raw == "LONG POSITION":
        sig = "buy"
        side = "long"
    elif raw == "SHORT POSITION":
        sig = "sell"
        side = "short"
    else:
        return JSONResponse({"ok": False, "reason": "unsupported signal"}, status_code=400)

    # 현재 DB open trade
    open_trade_id = db.get_open_trade_id(bot_id=BOT_ID, symbol=SYMBOL)

    cur_pos = trading.get_current_position_side(SYMBOL)

    # ===== 기존 포지션 있음 → close =====
    if cur_pos != "none":
        trading.close_position_percent(SYMBOL, "long", 100)
        trading.close_position_percent(SYMBOL, "short", 100)

        cur_balance = trading.get_usdtm_futures_balance()
        pnl = cur_balance - prev_balance

        if pnl > 0:
            win += 1
        else:
            lose += 1

        # DB close
        if open_trade_id:
            db.close_trade(
                trade_id=open_trade_id,
                realized_pnl_usdt=pnl,
                close_price=trading.get_market_price(SYMBOL),
                side=None,
                raw_signal=raw,
                close_meta={
                    "balance": cur_balance,
                    "pnl": pnl
                }
            )

        prev_balance = cur_balance

        await send_telegram_message(
            f"[Bot Alert]\nBalance: {prev_balance}\nWin: {win}, Lose: {lose}"
        )

    else:
        prev_balance = trading.get_usdtm_futures_balance()

    # ===== 새 포지션 open =====
    resp = trading.place_market_order_open(sig, margin_usdt=MARGIN_USDT, leverage=LEVERAGE)
    order_id = extract_order_id(resp)

    market_price = trading.get_market_price(SYMBOL)

    new_trade_id = db.create_trade(
        bot_id=BOT_ID,
        symbol=SYMBOL,
        open_side=side,
        leverage=LEVERAGE,
        margin_usdt=MARGIN_USDT,
        open_price=market_price,
        open_order_id=order_id,
        raw_signal=raw,
        open_meta={"resp": resp}
    )

    return JSONResponse({"ok": True, "trade_id": new_trade_id})


@app.post("/webhook2")
async def handle_webhook2(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")

    if raw == "LONG POSITION" or raw == "SHORT POSITION":
        return JSONResponse({"ok": True})

    await send_telegram_message(f"[Bot Alert]\n{raw}")

    tp_info = None
    if raw in ("SHORT TAKE PROFIT 1", "SHORT TAKE PROFIT 2"):
        tp_info = ("short", 50)
    elif raw in ("LONG TAKE PROFIT 1", "LONG TAKE PROFIT 2"):
        tp_info = ("long", 50)

    if tp_info:
        hold_side, percent = tp_info
        resp = trading.close_position_percent(SYMBOL, hold_side, percent)

        open_trade_id = db.get_open_trade_id(bot_id=BOT_ID, symbol=SYMBOL)
        if open_trade_id:
            db.add_event(
                trade_id=open_trade_id,
                event_type="tp",
                side=hold_side,
                percent=percent,
                price=trading.get_market_price(SYMBOL),
                raw_signal=raw,
                meta={"resp": resp}
            )

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)