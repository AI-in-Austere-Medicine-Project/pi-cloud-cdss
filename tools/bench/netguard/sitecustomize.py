# D1: log every non-loopback socket connection attempt made by Python in the
# benchmark processes. Logging only; nothing is blocked. NETGUARD_LOG names the file.
import os, socket, sys, time, json
_LOG = os.environ.get("NETGUARD_LOG")
if _LOG:
    def _note(kind, addr):
        try:
            host = addr[0] if isinstance(addr, tuple) else str(addr)
            if isinstance(addr, (str, bytes)) or host in ("localhost", "::1") or str(host).startswith("127.") or str(host).startswith("/"):
                return
            with open(_LOG, "a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pid": os.getpid(),
                                    "argv": " ".join(sys.argv)[:120], "kind": kind, "addr": str(addr)[:120]}) + "\n")
        except Exception:
            pass
    _c, _cx, _gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    def connect(self, addr): _note("connect", addr); return _c(self, addr)
    def connect_ex(self, addr): _note("connect_ex", addr); return _cx(self, addr)
    def getaddrinfo(host, *a, **k): _note("getaddrinfo", (host,)); return _gai(host, *a, **k)
    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
