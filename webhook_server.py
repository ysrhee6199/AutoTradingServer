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
    print("=== RAW BODY START ===")
    await send_telegram_message(f"[WEBHOOK RAW]\n{raw}")
    print("=== RAW BODY END ===")

    # 1) JSON 시도
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # 2) JSON 아니면 텍스트로 처리
        data = {"_raw": raw}

    print("PARSED:", data)
    return JSONResponse({"ok": True})
    
if __name__ == "__main__":
    #uvicorn.run(app, host="0.0.0.0", port=443, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
    uvicorn.run(app, host="0.0.0.0", port=8000)
