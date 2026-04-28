@echo off
echo Preparing to push project to GitHub...

REM Initialize Git if not already initialized
if not exist ".git" (
    echo Initializing Git repository...
    git init
)

REM Handle the nested ECCV2022-RIFE git folder
REM This will merge it into your main repository for simplicity
if exist "ECCV2022-RIFE\.git" (
    echo Found nested .git folder in ECCV2022-RIFE.
    echo Stripping nested history to include it as a regular folder...
    rmdir /s /q "ECCV2022-RIFE\.git"
)

echo Adding files to Git...
git add .

echo Committing files...
git commit -m "Final Polish: Dynamic Map Selection, High-Res Frames, and Custom Video Scrubber"

echo Setting branch to main...
git branch -M main

echo Adding remote origin...
git remote add origin https://github.com/anmolpanchal017/ai-wms-video-interpolation.git

echo Pushing to GitHub...
echo NOTE: You might be prompted for your GitHub credentials.
git push -u origin main

echo.
echo ======================================================
echo Done! If there were no errors, your code is now on GitHub.
echo Check it at: https://github.com/anmolpanchal017/ai-wms-video-interpolation
echo ======================================================
pause
