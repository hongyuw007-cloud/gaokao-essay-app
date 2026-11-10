"""Capture functional screenshots from a Chrome/Edge DevTools CDP session."""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

import websocket


class DevTools:
    def __init__(self, websocket_url: str) -> None:
        self.ws = websocket.create_connection(websocket_url, timeout=180)
        self.next_id = 1

    def call(self, method: str, **params):
        message_id = self.next_id
        self.next_id += 1
        self.ws.send(
            json.dumps(
                {"id": message_id, "method": method, "params": params},
                ensure_ascii=False,
            )
        )
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method} failed: {message['error']}")
            return message.get("result", {})

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            awaitPromise=await_promise,
            returnByValue=True,
        )
        exception = result.get("exceptionDetails")
        if exception:
            raise RuntimeError(f"Page JavaScript failed: {exception}")
        return result.get("result", {}).get("value")

    def screenshot(self, output_path: Path) -> None:
        data = self.call(
            "Page.captureScreenshot",
            format="png",
            fromSurface=True,
            captureBeyondViewport=False,
        )
        output_path.write_bytes(base64.b64decode(data["data"]))

    def close(self) -> None:
        self.ws.close()


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--port", type=int, default=9333)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--existing-only", action="store_true")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    pages = json.loads(
        urllib.request.urlopen(
            f"http://127.0.0.1:{args.port}/json/list",
            timeout=15,
        ).read()
    )
    page = next(
        (
            item
            for item in pages
            if item.get("type") == "page"
            and (
                item.get("url") == "about:blank"
                or str(item.get("url", "")).startswith(args.base_url.rstrip("/"))
            )
        ),
        None,
    )
    if page is None:
        raise RuntimeError("No suitable browser page was found")
    devtools = DevTools(page["webSocketDebuggerUrl"])

    try:
        devtools.call("Page.enable")
        devtools.call("Runtime.enable")
        devtools.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        devtools.call("Page.navigate", url=args.base_url)
        time.sleep(2)
        devtools.evaluate("localStorage.removeItem('gaokao_essay_session_v2'); location.reload();")
        time.sleep(4)
        devtools.screenshot(args.output / "login.png")

        session = post_json(
            f"{args.base_url.rstrip('/')}/api/auth",
            {
                "action": "login",
                "email": args.email,
                "password": args.password,
            },
        )
        if not session.get("authenticated") or not session.get("access_token"):
            raise RuntimeError("Screenshot account could not log in")

        session_json = json.dumps(session, ensure_ascii=False)
        devtools.evaluate(
            "localStorage.setItem('gaokao_essay_session_v2', "
            f"{json.dumps(session_json, ensure_ascii=False)}); location.reload();"
        )
        for _ in range(30):
            time.sleep(0.5)
            if devtools.evaluate("Boolean(state.user)"):
                break
        else:
            raise RuntimeError("The authenticated application did not finish loading")

        if args.existing_only:
            for _ in range(30):
                time.sleep(0.5)
                if devtools.evaluate("state.essays.length > 0"):
                    break
            else:
                raise RuntimeError("No existing essay was found for screenshots")
            refreshed = devtools.evaluate(
                """
                (() => {
                  selectEssay(state.essays[0]);
                  el('resultCard').scrollIntoView({block: 'start', behavior: 'instant'});
                  return {
                    id: state.selectedEssay.id,
                    title: state.selectedEssay.title,
                    wordCount: state.selectedEssay.word_count,
                    essayCount: state.essays.length,
                  };
                })()
                """
            )
            time.sleep(1)
            devtools.screenshot(args.output / "result.png")
            devtools.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")
            time.sleep(1)
            devtools.screenshot(args.output / "history.png")
            print(json.dumps(refreshed, ensure_ascii=False))
            return

        devtools.evaluate(
            """
            (() => {
              el('topic').value = '阅读下面的材料，根据要求写作';
              el('material').value = '青年既要仰望星空，也要脚踏实地。面对时代机遇，应如何把个人理想融入社会发展？';
              el('genre').value = 'argumentative';
              el('targetWordCount').value = '800';
            })()
            """
        )
        devtools.screenshot(args.output / "home.png")

        generated = devtools.evaluate(
            """
            (async () => {
              await generateEssay();
              if (!state.selectedEssay?.essay) {
                throw new Error(el('generateError').textContent || 'generate failed');
              }
              return {
                id: state.selectedEssay.id || null,
                title: state.selectedEssay.title,
                saved: Boolean(state.selectedEssay.id),
                strategyVisible: !el('strategyCard').hidden,
                wordMeta: el('resultMeta').textContent,
                lengthRevision: state.selectedEssay.length_revision || null,
              };
            })()
            """,
            await_promise=True,
        )
        time.sleep(2)
        devtools.screenshot(args.output / "result.png")
        devtools.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")
        time.sleep(1)
        devtools.screenshot(args.output / "history.png")
        print(json.dumps(generated, ensure_ascii=False))
    finally:
        devtools.close()


if __name__ == "__main__":
    main()
