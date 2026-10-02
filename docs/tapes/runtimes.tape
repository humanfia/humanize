# The runtimes page of `/settings`: the machines a flow's environments go on, what there is
# to do with one, and the form a docker daemon is added on.
#
# The hosts it walks over were written down by `stage.py` at reserved-invalid names, and
# nothing here reaches any of them: a machine is only asked what it has when it is added,
# corrected or checked, and this tape does none of those.

Output "/out/runtimes.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 560
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 400ms

# Every machine saved, under a heading per backend, with what brings one in on the buttons
# under them: adding an ssh host, adding a docker daemon, and importing the hosts an ssh
# config names.
Type "/settings runtimes" Enter
Wait+Screen /Import ~\/.ssh\/config/
Sleep 1400ms
Screenshot "/out/runtimes.png"
Sleep 400ms

# Enter opens what there is to do with the one under the cursor, taking it away last.
Enter
Wait+Screen /check host resources/
Sleep 1400ms
Escape
Sleep 700ms

# And `Add a docker host`, the second button, is one form: where the daemon is, picked from a
# list, the name written in for you, and what it may hand out last, over the row that asks
# the daemon.
Tab
Right
Sleep 500ms
Enter
Wait+Screen /endpoint/
Sleep 1400ms
Screenshot "/out/docker-form.png"
Sleep 400ms
