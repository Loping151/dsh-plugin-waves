#!/usr/bin/env python3
"""在真实浏览器里打开一张卡片, 检查渲染尺寸、字体与点击回传。"""

import argparse
import json
import sys
import urllib.request


def fetch_card(base: str, command: str) -> str:
    body = json.dumps({"command": command}).encode()
    req = urllib.request.Request(
        f"{base}/api/chat", data=body, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    for seg in data.get("segments") or []:
        if seg.get("type") == "html":
            return seg["url"]
    sys.exit(f"{command} 没有返回 HTML 卡片")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:9777")
    parser.add_argument("--command", default="ww深塔")
    parser.add_argument("--shot", default="/tmp/waves-card.png")
    args = parser.parse_args()

    url = args.base + fetch_card(args.base, args.command)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        messages = []
        page.expose_function("__wwCapture", lambda m: messages.append(m))
        page.add_init_script(
            "window.parent.postMessage = (m) => window.__wwCapture(JSON.stringify(m));"
        )
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(1500)

        size = page.evaluate(
            "() => { const el = document.querySelector('.container') || document.body;"
            " const r = el.getBoundingClientRect();"
            " return { w: Math.round(r.width), h: Math.round(el.scrollHeight) }; }"
        )
        clickable = page.locator("[data-ww-cmd]")
        count = clickable.count()
        font_ok = page.evaluate(
            "() => [...document.styleSheets].some(s => { try { return s.href && s.href.includes('fonts.css') }"
            " catch(e) { return false } }) || document.fonts.size > 0"
        )

        first_cmd = clickable.first.get_attribute("data-ww-cmd") if count else None
        if count:
            clickable.first.click()
            page.wait_for_timeout(400)

        page.screenshot(path=args.shot, full_page=False)
        browser.close()

    sizes = [m for m in messages if '"size"' in m]
    commands = [json.loads(m) for m in messages if '"command"' in m]
    print(f"卡片: {url}")
    print(f"渲染尺寸: {size['w']}x{size['h']}  字体已加载: {font_ok}")
    print(f"可点击角色: {count} 个, 首个命令: {first_cmd}")
    print(f"尺寸回传: {len(sizes)} 次")
    print(f"点击回传: {commands}")
    print(f"页面错误: {errors or '无'}")
    print(f"截图: {args.shot}")

    ok = count > 0 and commands and commands[0].get("command") == first_cmd and not errors
    print("\n结论:", "交互正常" if ok else "需检查")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
