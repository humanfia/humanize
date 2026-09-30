# The Accounts page of `/settings`: what there is to do with one account, and the form a new one is made on.
#
# The account this walks over was made by `stage.py` at a reserved-invalid endpoint with the
# words `not-a-real-token`. Nothing here signs in to anything, and no value is ever drawn.

Output "/out/accounts.gif"

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

# Every account there is, under a heading per CLI, with what is done about the list above it.
# The names of the variables each sets, and never a value: this is drawn where somebody can
# read it.
Type "/settings accounts" Enter
Wait+Screen /as local/
Sleep 1400ms

# Enter opens what there is to do with the one under the cursor -- four questions about one
# account, taking it away among them, rather than four letters to read off the bottom of the
# screen.
Enter
Wait+Screen /edit settings/
Sleep 1400ms
Screenshot "/out/account-does.png"
Sleep 400ms

Escape
Sleep 700ms

# And `Add an account`, the first button under the list, is one form: which CLI, which way
# in, a name written in for you, and what that way asks. Nothing is typed into it here.
Tab
Sleep 500ms
Enter
Wait+Screen /account name/
Sleep 1400ms
Screenshot "/out/account-form.png"
Sleep 400ms
