#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MERLIN MEMORY KIT - shared config loader.
Reads kit.config.json (next to this file, or path in MMK_CONFIG env).
No secrets here: everything is local URLs + file lists. By Merlin the Owl, MIT.
"""
import json, os

# Windows consoles default to cp1252 and choke on emoji that appear in real memory files.
# Every kit script inherits this, so headings print correctly on any platform.
try:
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_CFG = os.environ.get("MMK_CONFIG") or os.path.join(_HERE, "..", "kit.config.json")

def load():
    cfg = json.load(open(_CFG, encoding="utf-8"))
    ws = cfg.get("workspace_dir", ".")
    if not os.path.isabs(ws):
        ws = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(_CFG)), ws))
    cfg["workspace_dir"] = ws
    return cfg
