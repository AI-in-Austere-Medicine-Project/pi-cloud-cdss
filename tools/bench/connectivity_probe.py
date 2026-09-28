#!/usr/bin/env python3
"""D1 connectivity probe: one timestamped JSON line per call, appended to argv[2].
usage: connectivity_probe.py <phase> <out.jsonl>. Prints ONLINE/OFFLINE. Offline means every
check below fails; any single path out makes the probe ONLINE."""
import json, socket, subprocess, sys, time
EXTERNAL = ("enP8p1s0", "wlP1p1s0", "usb0", "usb1", "wwan0")
def sh(cmd, t=6):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=t).stdout.strip()
    except Exception as e: return f"ERR {type(e).__name__}"
r = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "phase": sys.argv[1]}
links = json.loads(sh(["ip", "-j", "link"]) or "[]")
r["links"] = {l["ifname"]: {"operstate": l.get("operstate"), "carrier": "LOWER_UP" in l.get("flags", [])}
              for l in links if l["ifname"] in EXTERNAL or l["ifname"].startswith(("wl", "ww", "en", "eth"))}
r["default_routes"] = [f'{d.get("gateway")} dev {d.get("dev")}' for d in json.loads(sh(["ip", "-j", "route", "show", "default"]) or "[]")
                       if "linkdown" not in d.get("flags", [])]
r["nmcli"] = sh(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "dev"]).splitlines()
r["wifi_radio"] = sh(["nmcli", "radio", "wifi"])
r["modems"] = sh(["mmcli", "-L"])
r["dns_api_openai"] = sh(["timeout", "4", "getent", "hosts", "api.openai.com"]) or "FAIL"
r["dns_api_anthropic"] = sh(["timeout", "4", "getent", "hosts", "api.anthropic.com"]) or "FAIL"
def tcp(host, port):
    try:
        socket.create_connection((host, port), timeout=3).close(); return "OK"
    except Exception as e: return f"FAIL {type(e).__name__}"
r["tcp"] = {f"{h}:{p}": tcp(h, p) for h, p in (("1.1.1.1", 443), ("8.8.8.8", 53), ("162.159.140.1", 443))}
r["ping_1.1.1.1"] = "OK" if " 0% packet loss" in sh(["ping", "-c1", "-W2", "1.1.1.1"]) else "FAIL"
paths = [n for n, v in r["links"].items() if v["carrier"]]
online = bool(paths or r["default_routes"] or "No modems were found" not in r["modems"]
              or r["dns_api_openai"] != "FAIL" or r["dns_api_anthropic"] != "FAIL"
              or any(v == "OK" for v in r["tcp"].values()) or r["ping_1.1.1.1"] == "OK")
r["external_links_with_carrier"] = paths
r["verdict"] = "ONLINE" if online else "OFFLINE"
with open(sys.argv[2], "a") as f: f.write(json.dumps(r) + "\n")
print(r["verdict"])
