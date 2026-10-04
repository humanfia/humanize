# The runtimes page of `/settings`: the machines a flow's environments go on, what there is
# to do with one, and the form a docker daemon is added on.
#
# The hosts it walks over were written down by `stage.py` at reserved-invalid names, and
# nothing here reaches any of them: a machine is only asked what it has when it is added,
# corrected or checked, and this tape does none of those.

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
# under them: adding one of any kind, and importing the hosts an ssh config names.
Type "/settings runtimes" Enter
Wait+Screen /Import ~\/.ssh\/config/
Sleep 1400ms
Screenshot "/out/runtimes.png"
Sleep 400ms

# Enter opens what there is to do with the one under the cursor, with taking it away a red
# button under it.
Enter
Wait+Screen /check host resources/
Sleep 1400ms
Escape
Sleep 700ms

# And `Add a runtime…`, the first button, drops the kinds; a docker host, the second, is one
# form: where the daemon is, picked from a list, the name written in for you, and what it
# may hand out last, with `Detect`, which asks the daemon, beside `Done`.
Tab
Sleep 500ms
Enter
Wait+Screen /docker swarm/
Sleep 1000ms
Down
Sleep 500ms
Enter
Wait+Screen /endpoint/
Sleep 1400ms
Screenshot "/out/docker-form.png"
Sleep 400ms
