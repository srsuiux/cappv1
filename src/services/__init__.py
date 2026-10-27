"""The service layer: everything cappv1 does that isn't drawing a screen.

Both the terminal session (src/tui) and the web UI (src/web) call these
functions and nothing else; the engine (pipeline.py and friends) is only ever
reached from here. Functions take a Workspace, return plain data, and raise
ServiceError with a message a non-technical person can act on.
"""
