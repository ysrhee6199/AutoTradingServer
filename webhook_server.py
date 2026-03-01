# webhook_server.py
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import json
import os
from message import send_telegram_message
import trading

app = FastAPI()

# Mount the static directory to serve CSS and JS files
app.mount("/static", StaticFiles(directory="static"), name="static")

prev_balance = 0.0
win = 0
lose = 0

@app.get("/")
async def serve_dashboard():
    # Serve the main index.html file for the UI
    return FileResponse(os.path.join("static", "index.html"))

@app.post("/webhook")
async def handle_webhook(request: Request):
    global prev_balance, win, lose
    raw = (await request.body()).decode("utf-8", errors="replace")

    # 로그에 원문을 남기면 원인 바로 보임
    await send_telegram_message(f"[Bot Alert]\n{raw}")
    
    sig = ""
    if raw == "LONG POSITION":
        sig = "buy"
    elif raw == "SHORT POSITION":
        sig = "sell"
    else:
        return JSONResponse({"ok": False, "reason": "unsupported signal"}, status_code=400) 

    cur_pos = trading.get_current_position_side("BTCUSDT")
    if cur_pos == "none":
        prev_balance = trading.get_usdtm_futures_balance()
        trading.place_market_order_open(sig, margin_usdt=50.0, leverage=50)
    else:
        trading.close_position_percent("BTCUSDT", "long", 100)
        trading.close_position_percent("BTCUSDT", "short", 100)
        cur_balance = trading.get_usdtm_futures_balance()
        if(cur_balance - prev_balance > 0.0):
            win+=1
        else:
            lose+=1

        prev_balance = cur_balance
        trading.place_market_order_open(sig, margin_usdt=50.0, leverage=50)
        await send_telegram_message(f"[Bot Alert]\nCurrent_balance : {prev_balance} \nWin : {win}, Lose : {lose}")

    return JSONResponse({"ok": True})

@app.post("/webhook2")
async def handle_webhook2(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")

    # 로그에 원문을 남기면 원인 바로 보임
    if(raw == "LONG POSITION" or raw == "SHORT POSITION"):
        pass
    else:
        await send_telegram_message(f"[Bot Alert]\n{raw}")
        if raw == "SHORT TAKE PROFIT 1" or raw == "SHORT TAKE PROFIT 2":
            trading.close_position_percent("BTCUSDT", "short", 50)
        elif raw == "LONG TAKE PROFIT 1" or raw == "LONG TAKE PROFIT 2":
            trading.close_position_percent("BTCUSDT", "long", 50)

    return JSONResponse({"ok": True})
    
if __name__ == "__main__":
    #uvicorn.run(app, host="0.0.0.0", port=443, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
    uvicorn.run(app, host="0.0.0.0", port=8000)
