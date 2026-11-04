"""Send one command to the QGIS MCP plugin socket. Usage:
qgis_call.py <command> [json-params]   |   qgis_call.py exec <file.py>"""
import json, os, socket, struct, sys
def call(cmd, **params):
    b = json.dumps({"type": cmd, "params": params}).encode()
    with socket.create_connection(("127.0.0.1", 9876), timeout=600) as s:
        s.sendall(struct.pack(">I", len(b)) + b)
        n = struct.unpack(">I", s.recv(4, socket.MSG_WAITALL))[0]
        buf = b""
        while len(buf) < n: buf += s.recv(n - len(buf))
    return json.loads(buf)
if sys.argv[1] == "exec":
    # Scripts run inside QGIS, where __file__ is unset: tell them where the repo is
    root = os.path.dirname(os.path.abspath(sys.argv[2]))
    r = call("execute_code", code=f"ROOT = {root!r}\n" + open(sys.argv[2]).read(), timeout=300)
    res = r.get("result", r)
    print(res.get("stdout", ""), res.get("stderr", ""), {k: v for k, v in res.items() if k not in ("stdout", "stderr")} if isinstance(res, dict) else "", r.get("message", ""))
else:
    print(json.dumps(call(sys.argv[1], **(json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})), indent=1)[:3000])
