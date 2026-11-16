"""Run the course's voice memo job on a GitHub Actions runner."""

import json
import os
import subprocess
import urllib.request
from pathlib import Path


CLIP = "https://hq.mega.dev/media/two-places/dispatch-2-c14d2d05.mp3"
CALLS = []


def rpc(method, params):
    request = {"jsonrpc": "2.0", "id": len(CALLS) + 1, "method": method, "params": params}
    http = urllib.request.Request(
        os.environ["JOB_URL"],
        data=json.dumps(request).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    with urllib.request.urlopen(http, timeout=120) as response:
        body = response.read().decode()
        if response.headers.get("Content-Type", "").startswith("text/event-stream"):
            reply = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")][-1]
        else:
            reply = json.loads(body)
    CALLS.append({"request": request, "reply": reply})
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]


def tool(name, arguments):
    result = rpc("tools/call", {"name": name, "arguments": arguments})
    if result.get("isError"):
        raise RuntimeError(result)
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def run():
    first = tool("transcribe", {"url": CLIP})
    if os.environ["MODE"] == "capture":
        return {"transcript": first}

    notes = json.loads(os.environ["NOTES_JSON"])
    if not isinstance(notes, list) or not notes or any(not isinstance(n, str) or " @" not in n for n in notes):
        raise ValueError("NOTES_JSON must be a nonempty list of timed notes")
    step = first["step"]
    for note in notes:
        step = tool("memo_write", {"text": note, "step": step})["step"]
    found = tool("memo_search", {"step": step})
    step = found["step"]
    returned = found.get("notes", [])
    if len(returned) != len(notes) or any(
        item.get("at") != note.rsplit(" ", 1)[-1]
        or item.get("chars") != len(note)
        or item.get("stamps") != 1
        or not note.startswith(item.get("text", ""))
        for note, item in zip(notes, returned)
    ):
        raise RuntimeError("Memo search did not return every note")
    submitted = tool("submit", {"result": "\n".join(notes), "skillVersion": "1", "step": step})
    if submitted.get("status") != "accepted" or "receipt" not in submitted:
        raise RuntimeError(f"Job was not accepted: {submitted}")
    return {"transcript": first, "search": found, "submission": submitted}


def main():
    output = {}
    failed = False
    try:
        output["result"] = run()
    except Exception as exc:
        output["error"] = str(exc)
        failed = True
    output["calls"] = CALLS
    raw = Path("result.json")
    raw.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-in", str(raw), "-out", "result.enc", "-pass", "env:ARTIFACT_PASSPHRASE"],
        check=True,
    )
    raw.unlink()
    if failed:
        raise SystemExit("Remote worker failed; encrypted result artifact has details")


if __name__ == "__main__":
    main()
