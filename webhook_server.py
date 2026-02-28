# webhook_server.py
import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    print(data)
    # 처리 로직 구현
    return {"message": "Received"}
    
if __name__ == "__main__":
    #uvicorn.run(app, host="0.0.0.0", port=443, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
    uvicorn.run(app, host="0.0.0.0", port=8000)
