# CyBot GUI

## Files
- `cybot_gui.py` — final annotated archaeology rover GUI
- `mock_cybot_server.py` — local TCP simulator for testing without the physical robot

## Run locally

Start the mock server:
```bash
python mock_cybot_server.py
```

In another terminal:
```bash
python cybot_gui.py
```

Use the GUI's mock/local connection option or connect to `127.0.0.1` on port `288`.

The GUI source retains the original project disclosure and attribution comments.
