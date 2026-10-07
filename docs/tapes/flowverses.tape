# `/flow`: out to its first screen, into the flowverses -- the indexes more flows are installed
# from -- and into humanize's own, to install one flow at the release asked for.
#
# Nothing reaches a network. The official index is the one `stage.py` wrote into this
# container, and the fetch the interface tries as it opens fails quietly. The release installed
# is the one whose checkout `stage.py` put where a fetch of it would have left it, so installing
# it copies a flow that never runs here.

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

# What `/flow` opens on: every flow ready to run here.
Type "/flow" Enter
Wait+Screen /Install more/
Sleep 1200ms

# Out a step, to the first screen: what is installed, and where more come from.
Left
Wait+Screen /indexes of flows/
Sleep 1200ms

# Into the flowverses: a card per index, how it stands and how much it lists.
Down
Enter
Wait+Screen /Add flowverse/
Sleep 1200ms

# Into `official`: each flow its index lists, at its newest release.
Enter
Wait+Screen /lists, at their newest/
Sleep 1600ms

# Into one flow: its releases, newest first. Enter installs the one under the cursor -- here
# the older, to show that what is installed is a version rather than whatever is newest.
# `aot` is the first flow listed, so the cursor is on it already.
Enter
Wait+Screen /Releases of aot/
Sleep 1200ms
Down
Sleep 600ms
Enter
Wait+Screen /aot 0\.1\.0 is installed/
Sleep 1600ms
Screenshot "/out/flowverses.png"
Sleep 400ms

# Back out, where the flow now says what is installed and that a newer release is listed.
Escape
Wait+Screen /↑ 0\.2\.0/
Sleep 2000ms
