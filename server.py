from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
import time
from fastapi import HTTPException
from fastapi.responses import HTMLResponse


app = FastAPI()

MiB = 1024 * 1024
SECRET_TOKEN = "jyvf5cgh8gyg"

def generate_bytes(total_bytes: int):
    chunk = b"A" * 65536
    remaining = total_bytes

    while remaining > 0:
        n = min(len(chunk), remaining)
        yield chunk[:n]
        remaining -= n


@app.get("/")
def homepage(size: int = Query(5, ge=1, le=200), token: str | None = None):

    if token != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    return HTMLResponse(f"""
    <html>
    <body>
        <p id="result">Running test...</p>

        <script>
        const size = {size};
        const token = "{token}";

        async function runTest() {{
            const start = performance.now();

            const response = await fetch(`/speedtest/download?size_mib=${{size}}&token=${{token}}`);
            const blob = await response.blob();

            const end = performance.now();
            const duration = (end - start) / 1000;

            const res = await fetch("/speedtest/result", {{
                method: "POST",
                headers: {{"Content-Type": "application/json"}},
                body: JSON.stringify({{
                    size_bytes: blob.size,
                    duration_sec: duration,
                    token: token
                }})
            }});

            const data = await res.json();

            document.getElementById("result").innerText =
                "Speed: " + data.speed_mbps + " Mbps";
        }}

        window.onload = runTest;
        </script>
    </body>
    </html>
    """)
    
@app.get("/speedtest/download")
def download_test(
    size_mib: int = Query(5, ge=1, le=200),
    token: str | None = None
):

    if token != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    total_bytes = size_mib * MiB

    return StreamingResponse(
        generate_bytes(total_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(total_bytes),
            "Cache-Control": "no-store"
        }
    )

class SpeedResult(BaseModel):
    size_bytes: int
    duration_sec: float
    token: str | None = None


@app.post("/speedtest/result")
def result(data: SpeedResult):

    if data.token != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    speed_mbps = (data.size_bytes * 8) / data.duration_sec / 1_000_000

    return {
        "speed_mbps": round(speed_mbps, 2),
        "duration_sec": data.duration_sec
    }
    
# --------------------
# HEALTH CHECK
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="localhost", port=8080)