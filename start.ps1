# Activate venv and start the Flask app with custom database location
& .\.venv\Scripts\Activate.ps1

$env:DATABASE = "C:\Users\levyn\OneDrive\Ronit\ClientAppData\data.db"

Write-Host "Starting Flask app with database: $env:DATABASE" -ForegroundColor Green

python run.py
