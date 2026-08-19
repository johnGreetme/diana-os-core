---
name: modbus-healthcheck
description: Modbus fieldbus diagnostic and telemetry check tool.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
    emoji: "⚡"
---

# Instructions

To inspect live Modbus coils and registers:

```bash
python diana_cli.py scada --read
```
