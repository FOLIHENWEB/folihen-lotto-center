# Folihen Lotto Center

A small web app for entering and checking Ghana lottery draw results from a phone or computer, for all 19 games.

- **Add result:** pick the game, check the date and type the five numbers (machine numbers are optional).
- **This week:** the last 7 days of draws, showing which results are still missing.
- **Results:** every saved draw for a game, newest first, with any data warnings.
- **Settings:** connect the app to GitHub with a token (once per device).

## Where the results are kept

Results are saved to `results/draws.csv` in the private repository **FOLIHENWEB/lotto_ecosystem**. This app's own repository holds no results and no passwords. The GitHub token is kept only in the browser of each device that uses it.

On the PC, `tools/sync_master_data.bat` in lotto_ecosystem copies new results into the MASTER_DATA Word files in `Documents\MASTER_DATA` and uploads any results typed straight into Word. `tools/turn_on_auto_sync.bat` makes it run every 30 minutes.

## Checks the app makes before saving

- exactly 5 different numbers, each from 1 to 90
- the date is the right weekday for the game (asks you to confirm if not)
- the same game and date isn't already saved
- the same five numbers aren't already saved for another game that day, which is how copy-and-paste mistakes usually show up (asks you to confirm)

## Files

`index.html`, `styles.css` and `app.js` are the whole app. There is no build step, and GitHub Pages serves the files as they are.
