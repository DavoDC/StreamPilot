## C:\Users\David\GitHubRepos\StreamPilot

ADD ALL TO DOCS/IDEAS of things to fix , batch similar fixes together

- All logs should be separate , timestamped, like sbs dwl does . not all appended to one .log file
C:\Users\David\GitHubRepos\SBS_Download\data\logs

- Check "C:\Users\David\GitHubRepos\StreamPilot\data\logs\streampilot.log",  these are from running status.bat

- Every bat file should result in some kind of log, everything should be logged so can ask claude to scan

- status should be more robust , to OBS / SAB not be open .. maybe ..  is status script useful?  it does seem like a good way to test the program without actually sreaming anything its like a dry run test that just tests code/detection ,  ensure it is this, amnybe it could have better name?  think could be valuable

- bath scripts should stay open after fine. add-game closes right away. lets user look at output more closely, copy into claude 

- add game script output:
Make sure your game is running, then press any key to continue.

Press any key to continue . . .
=== StreamPilot: Add Game ===
Make sure your game is running, then press Enter...


Detected windows:
  [0] WindowsTerminal.exe | StreamPilot - Add Game | CASCADIA_HOSTING_WINDOW_CLASS
  [1] explorer.exe | setup - File Explorer | CabinetWClass
  [2] Notepad.exe | feedback542.txt - Notepad | Notepad
  [3] SystemSettings.exe | Settings | Windows.UI.Core.CoreWindow
  [4] GitHubDesktop.exe | GitHub Desktop | Chrome_WidgetWin_1
  [5] WindowsTerminal.exe | ✳ Claude Code | CASCADIA_HOSTING_WINDOW_CLASS
  [6] Marvel-Win64-Shipping.exe | Marvel Rivals   | UnrealWindow
  [7] steamwebhelper.exe | Steam | SDL_app
  [8] brave.exe | Quiet Your Mind: Terence McKenna [Black Screen/Brown&Rain So | Chrome_WidgetWin_1
  [9] ApplicationFrameHost.exe | Settings | ApplicationFrameWindow
  [10] TextInputHost.exe | Windows Input Experience | Windows.UI.Core.CoreWindow
  [11] explorer.exe | Program Manager | Progman

Enter number of game window: 6
obs_window: Marvel Rivals  :UnrealWindow:Marvel-Win64-Shipping.exe
Game name (for display): Marvel Rivals
No Twitch results found. Enter game ID manually.
Twitch game ID:

- Feedback = remove indentation from log 
- enter number of game window = replace with arrow to select.  don't show list twice tho.  show once but selectable. see rivalsvidmaker for example C:\Users\David\GitHubRepos\RivalsVidMaker

- "Game name (for display)": when i asked this , i didn't understand what diplsay for and i didn't know this would be used to search twithc

- Why is twich search for Marvel Rivals failing?  sould be easily/better/fuzzy 

- Where to get Game ids???

- in detected windows,  [6] Marvel-Win64-Shipping.exe | Marvel Rivals   | UnrealWindow , the 2nd column seems to match game name typically, this could be used to search automatically, but if that doesn't work then ask user, and IF that doesn't work, then do game ID, i.e. , try to do yourself first, automate , try yourself first then get user to confirm