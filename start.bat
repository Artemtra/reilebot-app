cd /d "C:\Users\artyo\OneDrive\Documents\_podgotovka\PracticTgBot"
start "REILEBOT BOT" cmd /k "title BOT && python -m app.main"
timeout /t 3 /nobreak >nul
start "REILEBOT NGROK API" cmd /k "title NGROK API && ngrok http 8000"