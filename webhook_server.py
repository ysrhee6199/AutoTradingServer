# webhook_server.py
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
from message import send_telegram_message

app = FastAPI()


@app.post("/webhook")
async def handle_webhook(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")

    # 로그에 원문을 남기면 원인 바로 보임
    await send_telegram_message(f"[Bot Alert]\n{raw}")
    return JSONResponse({"ok": True})

@app.post("/webhook2")
async def handle_webhook(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")

    # 로그에 원문을 남기면 원인 바로 보임
    if(raw == "LONG POSITION" or raw == "SHORT POSITION"):
        pass
    else:
        await send_telegram_message(f"[Bot Alert]\n{raw}")
    return JSONResponse({"ok": True})
    
if __name__ == "__main__":
    #uvicorn.run(app, host="0.0.0.0", port=443, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
    uvicorn.run(app, host="0.0.0.0", port=8000)
