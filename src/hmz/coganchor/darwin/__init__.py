"""Thin, dependency-free bindings to the macOS facilities coganchor relies on.

Only :mod:`seatbelt` (the paths and connections a process tree may reach), which is what a
fence is put up with on a Mac. Nothing is imported here, and :mod:`seatbelt` is importable on
any host, Linux included, to say that it is not available there.
"""
