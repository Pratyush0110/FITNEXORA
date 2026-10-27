
# FITNEXORA

Personalized Fitness & Nutrition Platform

**[Live Demo](https://fitnexora-g9jyyucxifake73wbmnhkw.streamlit.app/)**

## Features
- User signup and login
- Personalized workout planning
- Nutrition tracking
- Meal plans with ingredient quantities and nutrition breakdown
- Progress tracking

## Tech Stack
Python, Streamlit, SQLite, Pandas, Plotly
# FITNEXORA — Personalized Fitness & Nutrition Platform

FITNEXORA is a Streamlit portfolio project for workout planning and nutrition tracking. It includes account signup/login, user-specific workout and nutrition data, workout templates, a nutrition tracker, and profile-based meal-plan suggestions with food quantities and nutrient estimates.

## Features

- Signup and login with hashed passwords
- Separate workout plans and nutrition logs by username
- Workout planner with exercise and target-muscle labels
- Nutrition tracker for daily food/nutrition records
- Profile-based meal-plan suggestions using age, height, weight, activity and goal inputs
- Calories, protein, carbohydrates, fat, fiber and selected micronutrient estimates
- Dashboard and progress visualizations

## Tech stack

- Python
- Streamlit
- SQLite
- Pandas
- Plotly

## Run locally

1. Install Python 3.10 or newer.
2. Clone or download this repository.
3. Create and activate a virtual environment.
4. Install dependencies and start Streamlit:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The SQLite database (`fitnexora.db`) is created locally next to `app.py`. Database files are excluded from Git so personal records are not uploaded.

## Deployment

For Streamlit Community Cloud, connect this GitHub repository and select `app.py` as the main file. Streamlit Cloud deployments may not provide durable local SQLite storage across all redeploys/restarts, so use a hosted database before relying on it for persistent real-user data.

## Important notes

- Workout recommendations currently use predefined rules/templates; this project does not claim to use a trained machine-learning model.
- Nutrition values are estimates and depend on the food data used. They should not be treated as medical advice.
- This is a portfolio/learning project. Do not commit real user data, database files, passwords, API keys, or secrets.
