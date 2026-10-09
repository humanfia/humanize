"""A run read as it happens: who is working, what it has cost, and where it has got to.

What a frontend makes of the records a host sends while a run goes: the graph of who handed to
whom and how long each has been at it (`monitor`), what the run has spent as the agents' own
logs say it (`tally`), the run as one frontend follows it from those records (`following`), and
the bounded view of it a side question is asked with (`btw`).

Written once here rather than in each way in: the terminal interface and the web interface draw
the same run, and two copies of what a turn costs or of who is working would be two answers that
could come apart.
"""
