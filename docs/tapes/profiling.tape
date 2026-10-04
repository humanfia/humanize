# Whether a run of a flow is profiled as well as traced, said beside what it may spend.
#
# Nothing runs: the switch is written down with the rest of the flow's setup, and what it does
# is done by the next run of it. The programs in the trace beside it were invented by stage.py.

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 400ms

# The flow this directory is set up on, opened inside: its roles, then what a run of it may
# spend and whether it is profiled, one under the other.
Type "/flow local/twice" Enter
Wait+Screen /profiling/
Sleep 1400ms
Screenshot "/out/profiling.png"
Sleep 400ms

# A switch, as every `▾` row is: enter drops `on` and `off` under it, the one in force ticked.
# Esc takes neither, and leaves it as it was.
Down 2
Sleep 500ms
Enter
Wait+Screen /╭─ profiling/
Sleep 1600ms
Escape
Sleep 1200ms
