@echo off
setlocal

cd /d C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios

if not exist logs (
    mkdir logs
)

C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios\.venv\Scripts\python.exe -m scripts.run_daily_extracts --config C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios\config\products.xlsx --output-root C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios\data\daily_runs >> C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios\logs\daily_extracts.log 2>&1

endlocal
