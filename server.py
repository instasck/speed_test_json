from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

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


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


@app.get("/")
def homepage(
    request: Request,
    size: int = Query(10, ge=1, le=200),
    streams: int = Query(4, ge=1, le=16),
    token: str | None = None
):
    if token != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    client_ip = get_client_ip(request)

    return HTMLResponse(f"""
    <html>
    <body>
        <p id="result">Running test...</p>

        <script>
        const size = {size};
        const streams = {streams};
        const token = "{token}";
        const clientIp = "{client_ip}";

        async function downloadOne(index) {{
            const response = await fetch(`/speedtest/download?size_mib=${{size}}&token=${{token}}&r=${{Math.random()}}`);

            if (!response.ok) {{
                throw new Error("Download failed for stream " + index + " with status " + response.status);
            }}

            const reader = response.body.getReader();
            let totalBytes = 0;

            while (true) {{
                const {{ done, value }} = await reader.read();
                if (done) break;
                totalBytes += value.length;
            }}

            return totalBytes;
        }}

        async function runTest() {{
            try {{
                const start = performance.now();

                const results = await Promise.all(
                    Array.from({{ length: streams }}, (_, i) => downloadOne(i + 1))
                );

                const end = performance.now();
                const duration = (end - start) / 1000;
                const totalBytes = results.reduce((sum, val) => sum + val, 0);

                const res = await fetch("/speedtest/result", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{
                        size_bytes: totalBytes,
                        duration_sec: duration,
                        token: token
                    }})
                }});

                if (!res.ok) {{
                    throw new Error("Result request failed with status " + res.status);
                }}

                const data = await res.json();

                document.getElementById("result").innerText =
                    "Speed: " + data.speed_mbps.toFixed(2) + " Mbps " +
                    "Size: " + size + " MiB " +
                    "Streams: " + streams + " " +
                    "IP: " + clientIp;
            }} catch (err) {{
                document.getElementById("result").innerText = "Error: " + err.message;
            }}
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
            "Cache-Control": "no-store, no-transform",
            "Content-Encoding": "identity"
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


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080)
