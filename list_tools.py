#!/usr/bin/env python3
import httpx
import json

def parse_sse_event(line_buffer):
    event = {}
    for line in line_buffer:
        if not line.strip():
            continue
        if line.startswith("event:"):
            event["event"] = line[6:].strip()
        elif line.startswith("data:"):
            event["data"] = line[5:].strip()
    return event if "data" in event else None

def call_mcp(client, method, params=None, id=1):
    payload = {
        "jsonrpc": "2.0",
        "id": id,
        "method": method,
        "params": params or {}
    }
    with client.stream("POST", "http://172.10.0.25:8000/mcp", json=payload, timeout=60) as response:
        print(f"响应状态码：{response.status_code}")
        if response.status_code != 200:
            print(f"响应内容：{response.text}")
            return None
        line_buffer = []
        for line in response.iter_lines():
            if not line:
                if line_buffer:
                    event = parse_sse_event(line_buffer)
                    if event and event.get("event") == "message":
                        return json.loads(event["data"])
                    line_buffer = []
            else:
                line_buffer.append(line)
    return None

def main():
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json"
    }
    with httpx.Client(headers=headers, timeout=60) as client:
        # 初始化
        print("初始化...")
        init_resp = call_mcp(
            client,
            "initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            },
            id=1
        )
        print(f"初始化响应：{json.dumps(init_resp, indent=2, ensure_ascii=False)}")
        
        # 发送initialized通知
        client.post(
            "http://172.10.0.25:8000/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            },
            timeout=10
        )
        
        # 列出工具
        print("\n列出工具...")
        tools_resp = call_mcp(client, "list_tools", params={}, id=2)
        print(f"工具列表：{json.dumps(tools_resp, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    main()
