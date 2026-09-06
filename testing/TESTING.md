# Testing Notes

The project was tested incrementally rather than only at final integration.

## GUI / communication
- TCP connection and disconnection
- Command transmission
- Parsing movement and turn-completion messages
- Sensor-status display
- 180-degree scan handling
- 360-degree scan handling
- Object visualization
- Emergency-state handling
- Mock-server communication

## Rover / system
- Forward and reverse movement
- Turning
- Bump and cliff sensing
- Boundary / unsafe-ground response
- Ping and servo scanning
- Travel-mode behavior
- Survey-mode behavior
- Destination behavior
- End-to-end communication between rover and base station

`mock_cybot_server.py` supports GUI testing without requiring the physical CyBot.
