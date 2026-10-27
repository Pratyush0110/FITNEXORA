import sqlite3
import hashlib
import hmac
import secrets
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# ------------------------------------------------------------
# FITNEXORA - Personalized Fitness & Nutrition Platform
# Beginner-friendly Streamlit portfolio project
# Note: workout recommendations are rule-based, not a trained ML model.
# ------------------------------------------------------------

st.set_page_config(
    page_title="FITNEXORA",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = str(Path(__file__).resolve().parent / "fitnexora.db")


# ----------------------------- DATABASE -----------------------------

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Create clean, predictable tables for this version of FITNEXORA."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workout_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT 'Guest',
                name TEXT NOT NULL DEFAULT 'Workout Plan',
                experience TEXT NOT NULL DEFAULT 'Beginner',
                created_at TEXT NOT NULL DEFAULT '',
                training_days INTEGER NOT NULL DEFAULT 4,
                equipment TEXT NOT NULL DEFAULT 'Gym',
                goal TEXT NOT NULL DEFAULT 'Muscle Gain',
                plan_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nutrition_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT 'Guest',
                log_date TEXT NOT NULL DEFAULT '',
                calories INTEGER NOT NULL DEFAULT 0,
                protein REAL NOT NULL DEFAULT 0,
                carbs REAL NOT NULL DEFAULT 0,
                fats REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                age INTEGER NOT NULL DEFAULT 25,
                height_cm REAL NOT NULL DEFAULT 170,
                weight_kg REAL NOT NULL DEFAULT 70,
                sex TEXT NOT NULL DEFAULT 'Prefer not to say',
                activity_level TEXT NOT NULL DEFAULT 'Moderately active',
                nutrition_goal TEXT NOT NULL DEFAULT 'Maintain',
                diet_preference TEXT NOT NULL DEFAULT 'Non-vegetarian',
                allergies TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()


init_db()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()


def create_user(username, password):
    username = username.strip()
    if len(username) < 3:
        return False, "Username must contain at least 3 characters."
    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    salt = secrets.token_hex(16)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, salt, hash_password(password, salt), datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        return True, "Account created. You can now log in."
    except sqlite3.IntegrityError:
        return False, "That username already exists. Please choose another."


def verify_user(username, password):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, salt, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    if not row:
        return None
    candidate = hash_password(password, row[1])
    return row[0] if hmac.compare_digest(candidate, row[2]) else None


# Authentication gate: each account only loads data associated with its own username.
if "authenticated_user" not in st.session_state:
    st.session_state["authenticated_user"] = None

if not st.session_state["authenticated_user"]:
    st.markdown("<div class='hero'><h1>💪 FITNEXORA</h1><p>Your personal fitness companion. Create an account or log in to keep your data separate.</p></div>", unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Login", "Create account"])
    with login_tab:
        with st.form("login_form"):
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_submit = st.form_submit_button("Login", width="stretch")
        if login_submit:
            logged_in = verify_user(login_username, login_password)
            if logged_in:
                st.session_state["authenticated_user"] = logged_in
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    with signup_tab:
        with st.form("signup_form"):
            signup_username = st.text_input("Choose username", key="signup_username")
            signup_password = st.text_input("Create password (8+ characters)", type="password", key="signup_password")
            signup_confirm = st.text_input("Confirm password", type="password", key="signup_confirm")
            signup_submit = st.form_submit_button("Create account", width="stretch")
        if signup_submit:
            if signup_password != signup_confirm:
                st.error("Passwords do not match.")
            else:
                ok, message = create_user(signup_username, signup_password)
                if ok:
                    st.success(message)
                else:
                    st.error(message)
    st.info("Each user's workout plans and nutrition logs are separated by their account. Use a unique password and do not share it.")
    st.stop()


def save_plan(username, training_days, equipment, goal, plan, experience="Beginner"):
    import json

    created_at = datetime.now().isoformat(timespec="seconds")
    plan_json = json.dumps(plan)
    plan_name = f"{goal} Workout Plan"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO workout_plans
            (username, name, experience, created_at, training_days, equipment, goal, plan_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username or "Guest",
                plan_name,
                experience or "Beginner",
                created_at,
                int(training_days),
                equipment,
                goal,
                plan_json,
            ),
        )
        conn.commit()


def load_plans(username):
    import json

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, training_days, equipment, goal, plan_json
            FROM workout_plans
            WHERE username = ?
            ORDER BY id DESC
            """,
            (username,),
        ).fetchall()

    results = []
    for row in rows:
        try:
            plan = json.loads(row[5])
        except (TypeError, ValueError):
            plan = []
        results.append(
            {
                "id": row[0],
                "created_at": row[1],
                "training_days": row[2],
                "equipment": row[3],
                "goal": row[4],
                "plan": plan,
            }
        )
    return results


def save_nutrition(username, log_date, calories, protein, carbs, fats, notes):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO nutrition_logs
            (username, log_date, calories, protein, carbs, fats, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                log_date.isoformat(),
                int(calories),
                float(protein),
                float(carbs),
                float(fats),
                notes.strip(),
            ),
        )
        conn.commit()


def load_nutrition(username):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT log_date, calories, protein, carbs, fats, notes
            FROM nutrition_logs
            WHERE username = ?
            ORDER BY log_date DESC, id DESC
            """,
            (username,),
        ).fetchall()

    return pd.DataFrame(
        rows,
        columns=["Date", "Calories", "Protein (g)", "Carbs (g)", "Fats (g)", "Notes"],
    )


# ----------------------------- USER PROFILE / NUTRITION -----------------------------

def load_profile(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT age, height_cm, weight_kg, sex, activity_level, nutrition_goal, diet_preference, allergies "
            "FROM user_profiles WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
    if not row:
        return None
    return {
        "age": row[0], "height_cm": row[1], "weight_kg": row[2], "sex": row[3],
        "activity_level": row[4], "nutrition_goal": row[5],
        "diet_preference": row[6], "allergies": row[7],
    }

def save_profile(username, profile):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO user_profiles
            (username, age, height_cm, weight_kg, sex, activity_level, nutrition_goal, diet_preference, allergies, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                age=excluded.age, height_cm=excluded.height_cm, weight_kg=excluded.weight_kg,
                sex=excluded.sex, activity_level=excluded.activity_level, nutrition_goal=excluded.nutrition_goal,
                diet_preference=excluded.diet_preference, allergies=excluded.allergies, updated_at=excluded.updated_at
            """,
            (username, int(profile["age"]), float(profile["height_cm"]), float(profile["weight_kg"]),
             profile["sex"], profile["activity_level"], profile["nutrition_goal"],
             profile["diet_preference"], profile["allergies"].strip(), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()

def nutrition_estimate(profile):
    """Adult-only rough energy estimate; avoid prescribing calorie targets to minors."""
    age = int(profile["age"])
    if age < 18:
        return None
    weight = float(profile["weight_kg"])
    height = float(profile["height_cm"])
    sex = profile["sex"]
    # Mifflin-St Jeor estimate; sex selection is optional and clearly approximate.
    if sex == "Male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    elif sex == "Female":
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 78
    activity = {
        "Mostly sitting": 1.2, "Lightly active": 1.375,
        "Moderately active": 1.55, "Very active": 1.725,
    }.get(profile["activity_level"], 1.55)
    maintenance = round(bmr * activity / 50) * 50
    goal = profile["nutrition_goal"]
    if goal == "Muscle gain":
        calories = maintenance + 200
    elif goal == "Fat loss":
        calories = max(maintenance - 250, round(bmr))
    else:
        calories = maintenance
    protein = round(1.4 * weight)
    fat = round(0.8 * weight)
    carbs = max(0, round((calories - protein * 4 - fat * 9) / 4))
    return {"maintenance": maintenance, "calories": calories, "protein": protein, "carbs": carbs, "fat": fat}

# Approximate nutrition per 100 g edible portion (milk/yogurt use ml ~= g).
# Values are rounded estimates; brand, variety, cooking and water loss change them.
FOOD_NUTRIENTS = {
    "Oats (dry)": {"kcal":389,"protein":16.9,"carbs":66.3,"fat":6.9,"fiber":10.6,"calcium":54,"iron":4.7,"potassium":429,"magnesium":177,"zinc":3.97,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":56,"sodium":2},
    "Milk": {"kcal":61,"protein":3.2,"carbs":4.8,"fat":3.3,"fiber":0,"calcium":113,"iron":0.03,"potassium":132,"magnesium":10,"zinc":0.4,"vitamin_c":0,"vitamin_a":46,"b12":0.45,"folate":5,"sodium":43},
    "Banana": {"kcal":89,"protein":1.1,"carbs":22.8,"fat":0.3,"fiber":2.6,"calcium":5,"iron":0.26,"potassium":358,"magnesium":27,"zinc":0.15,"vitamin_c":8.7,"vitamin_a":3,"b12":0,"folate":20,"sodium":1},
    "Chia seeds": {"kcal":486,"protein":16.5,"carbs":42.1,"fat":30.7,"fiber":34.4,"calcium":631,"iron":7.7,"potassium":407,"magnesium":335,"zinc":4.6,"vitamin_c":1.6,"vitamin_a":0,"b12":0,"folate":49,"sodium":16},
    "Egg (whole)": {"kcal":143,"protein":12.6,"carbs":0.7,"fat":9.5,"fiber":0,"calcium":56,"iron":1.75,"potassium":138,"magnesium":12,"zinc":1.3,"vitamin_c":0,"vitamin_a":160,"b12":0.89,"folate":47,"sodium":142},
    "Whole-wheat roti (cooked)": {"kcal":297,"protein":9.8,"carbs":55.7,"fat":7.5,"fiber":8.0,"calcium":25,"iron":2.5,"potassium":250,"magnesium":82,"zinc":1.8,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":40,"sodium":400},
    "Cooked rice": {"kcal":130,"protein":2.7,"carbs":28.2,"fat":0.3,"fiber":0.4,"calcium":10,"iron":0.2,"potassium":35,"magnesium":12,"zinc":0.5,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":3,"sodium":1},
    "Chicken breast (cooked)": {"kcal":165,"protein":31,"carbs":0,"fat":3.6,"fiber":0,"calcium":15,"iron":1.0,"potassium":256,"magnesium":29,"zinc":1.0,"vitamin_c":0,"vitamin_a":6,"b12":0.34,"folate":4,"sodium":74},
    "Dal (cooked)": {"kcal":116,"protein":9,"carbs":20.1,"fat":0.4,"fiber":7.9,"calcium":19,"iron":3.3,"potassium":369,"magnesium":36,"zinc":1.3,"vitamin_c":1.5,"vitamin_a":2,"b12":0,"folate":181,"sodium":2},
    "Paneer": {"kcal":265,"protein":18.3,"carbs":1.2,"fat":20.8,"fiber":0,"calcium":208,"iron":0.2,"potassium":138,"magnesium":8,"zinc":2.7,"vitamin_c":0,"vitamin_a":210,"b12":0.7,"folate":20,"sodium":22},
    "Tofu": {"kcal":76,"protein":8.1,"carbs":1.9,"fat":4.8,"fiber":0.3,"calcium":350,"iron":5.4,"potassium":121,"magnesium":30,"zinc":0.8,"vitamin_c":0.1,"vitamin_a":0,"b12":0,"folate":15,"sodium":7},
    "Curd (plain)": {"kcal":61,"protein":3.5,"carbs":4.7,"fat":3.3,"fiber":0,"calcium":121,"iron":0.05,"potassium":155,"magnesium":12,"zinc":0.6,"vitamin_c":0.5,"vitamin_a":27,"b12":0.37,"folate":7,"sodium":46},
    "Apple": {"kcal":52,"protein":0.3,"carbs":13.8,"fat":0.2,"fiber":2.4,"calcium":6,"iron":0.12,"potassium":107,"magnesium":5,"zinc":0.04,"vitamin_c":4.6,"vitamin_a":3,"b12":0,"folate":3,"sodium":1},
    "Roasted chana": {"kcal":369,"protein":22,"carbs":58,"fat":6,"fiber":17,"calcium":105,"iron":4.3,"potassium":718,"magnesium":115,"zinc":3.4,"vitamin_c":0,"vitamin_a":3,"b12":0,"folate":437,"sodium":24},
    "Mixed vegetables (cooked)": {"kcal":65,"protein":2.5,"carbs":12,"fat":0.7,"fiber":4,"calcium":35,"iron":1.1,"potassium":280,"magnesium":22,"zinc":0.4,"vitamin_c":20,"vitamin_a":250,"b12":0,"folate":35,"sodium":35},
    "Almonds": {"kcal":579,"protein":21.2,"carbs":21.6,"fat":49.9,"fiber":12.5,"calcium":269,"iron":3.7,"potassium":733,"magnesium":270,"zinc":3.1,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":44,"sodium":1},
    "Fortified soy milk": {"kcal":43,"protein":3.3,"carbs":4,"fat":2.1,"fiber":0.6,"calcium":120,"iron":0.6,"potassium":120,"magnesium":15,"zinc":0.3,"vitamin_c":0,"vitamin_a":50,"b12":0.4,"folate":18,"sodium":40},
}
MICRO_LABELS = {
    "fiber":"Fiber (g)", "calcium":"Calcium (mg)", "iron":"Iron (mg)",
    "potassium":"Potassium (mg)", "magnesium":"Magnesium (mg)", "zinc":"Zinc (mg)",
    "vitamin_c":"Vitamin C (mg)", "vitamin_a":"Vitamin A (µg RAE)",
    "b12":"Vitamin B12 (µg)", "folate":"Folate (µg)", "sodium":"Sodium (mg)",
}

def build_detailed_meals(profile):
    """Return ingredient-level portions and approximate macro/micronutrient totals."""
    pref = profile["diet_preference"]
    if pref == "Vegan":
        breakfast = [("Oats (dry)",60,"g"),("Fortified soy milk",250,"ml"),("Banana",100,"g"),("Chia seeds",10,"g")]
        lunch = [("Cooked rice",180,"g"),("Dal (cooked)",180,"g"),("Tofu",120,"g"),("Mixed vegetables (cooked)",150,"g")]
        snack = [("Apple",150,"g"),("Roasted chana",35,"g"),("Almonds",10,"g")]
        dinner = [("Whole-wheat roti (cooked)",120,"g"),("Tofu",150,"g"),("Mixed vegetables (cooked)",200,"g")]
    elif pref == "Vegetarian":
        breakfast = [("Oats (dry)",60,"g"),("Milk",250,"ml"),("Banana",100,"g"),("Chia seeds",10,"g")]
        lunch = [("Cooked rice",180,"g"),("Dal (cooked)",180,"g"),("Paneer",80,"g"),("Mixed vegetables (cooked)",150,"g")]
        snack = [("Curd (plain)",200,"g"),("Apple",150,"g"),("Roasted chana",25,"g")]
        dinner = [("Whole-wheat roti (cooked)",120,"g"),("Paneer",80,"g"),("Dal (cooked)",100,"g"),("Mixed vegetables (cooked)",150,"g")]
    else:
        breakfast = [("Oats (dry)",60,"g"),("Milk",250,"ml"),("Banana",100,"g"),("Egg (whole)",100,"g")]
        lunch = [("Cooked rice",180,"g"),("Chicken breast (cooked)",130,"g"),("Dal (cooked)",100,"g"),("Mixed vegetables (cooked)",150,"g")]
        snack = [("Curd (plain)",200,"g"),("Apple",150,"g"),("Almonds",10,"g")]
        dinner = [("Whole-wheat roti (cooked)",120,"g"),("Chicken breast (cooked)",100,"g"),("Mixed vegetables (cooked)",200,"g")]

    meals = [("Breakfast", breakfast), ("Lunch", lunch), ("Snack", snack), ("Dinner", dinner)]
    # Adult portions are scaled modestly to the estimated energy target. For minors, do not scale down.
    estimate = nutrition_estimate(profile) if int(profile["age"]) >= 18 else None
    scale = max(0.8, min(1.25, estimate["calories"] / 2200)) if estimate else 1.0
    detailed = []
    for meal_name, items in meals:
        rows=[]
        for food, amount, unit in items:
            amount = round(amount * scale / 5) * 5
            factor = amount / 100
            n = FOOD_NUTRIENTS[food]
            row = {"Food":food,"Amount":f"{amount} {unit}"}
            row.update({k: round(n[k]*factor, 1) for k in ["kcal","protein","carbs","fat"]})
            row.update({k: round(n[k]*factor, 1) for k in MICRO_LABELS})
            rows.append(row)
        detailed.append((meal_name, rows))
    return detailed


def make_meal_ideas(profile):
    preference = profile["diet_preference"]
    if preference == "Vegetarian":
        protein_foods = "dal, rajma/chole, paneer, curd, tofu, soy chunks"
    elif preference == "Vegan":
        protein_foods = "dal, rajma/chole, tofu, soy chunks, beans, nuts and seeds"
    else:
        protein_foods = "eggs, chicken/fish if eaten, dal, beans, curd, paneer or tofu"
    allergy_note = f"Allergy/avoid list to respect: {profile['allergies']}" if profile.get("allergies", "").strip() else "No allergies entered; still check food labels and personal tolerance."
    return protein_foods, build_detailed_meals(profile), allergy_note


# ----------------------------- WORKOUT LIBRARY -----------------------------

# Every split label used below exists in each equipment library.
# This prevents KeyError errors such as EXERCISES[equipment]["Push"].
EXERCISES = {
    "Gym": {
        "Full Body A": [
            ("Leg Press", "Quads, glutes", "3 x 8-12"),
            ("Flat Chest Press Machine", "Middle chest emphasis, triceps", "3 x 8-12"),
            ("Lat Pulldown", "Back, biceps", "3 x 8-12"),
            ("Seated Leg Curl", "Hamstrings", "2 x 10-15"),
            ("Dumbbell Lateral Raise", "Shoulders", "2 x 12-15"),
            ("Plank", "Core", "3 x 30-45 sec"),
        ],
        "Full Body B": [
            ("Goblet Squat", "Quads, glutes", "3 x 8-12"),
            ("Seated Cable Row", "Back, biceps", "3 x 8-12"),
            ("Incline Chest Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Cable Face Pull", "Rear shoulders, upper back", "2 x 12-15"),
            ("Dead Bug", "Core", "3 x 10 per side"),
        ],
        "Full Body C": [
            ("Hack Squat", "Quads, glutes", "3 x 8-12"),
            ("Decline Chest Press or Assisted Dips", "Lower chest emphasis, triceps", "3 x 8-12"),
            ("Machine Chest Fly", "Middle chest emphasis", "2 x 10-15"),
            ("Chest-Supported Row", "Back", "3 x 8-12"),
            ("Hip Thrust", "Glutes", "3 x 8-12"),
            ("Dumbbell Curl", "Biceps", "2 x 10-15"),
            ("Cable Triceps Pushdown", "Triceps", "2 x 10-15"),
        ],
        "Upper A": [
            ("Bench Press", "Chest, triceps", "3 x 6-10"),
            ("Lat Pulldown", "Back, biceps", "3 x 8-12"),
            ("Seated Cable Row", "Back", "3 x 8-12"),
            ("Dumbbell Shoulder Press", "Shoulders, triceps", "3 x 8-12"),
            ("Dumbbell Curl", "Biceps", "2 x 10-15"),
            ("Cable Triceps Pushdown", "Triceps", "2 x 10-15"),
        ],
        "Lower A - Quads": [
            ("Squat or Hack Squat", "Quads, glutes", "3 x 6-10"),
            ("Leg Press", "Quads", "3 x 10-12"),
            ("Leg Extension", "Quads", "2 x 12-15"),
            ("Seated Leg Curl", "Hamstrings", "3 x 10-15"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
            ("Plank", "Core", "3 x 30-45 sec"),
        ],
        "Upper B": [
            ("Incline Dumbbell Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Decline Chest Press or Assisted Dips", "Lower chest emphasis, triceps", "2 x 8-12"),
            ("Chest-Supported Row", "Back, biceps", "3 x 8-12"),
            ("Assisted Pull-up", "Back, biceps", "3 x 6-10"),
            ("Dumbbell Lateral Raise", "Side shoulders", "3 x 12-15"),
            ("Reverse Pec Deck", "Rear shoulders", "2 x 12-15"),
            ("Hammer Curl", "Biceps, forearms", "2 x 10-15"),
        ],
        "Lower B - Hamstrings & Glutes": [
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Hip Thrust", "Glutes", "3 x 8-12"),
            ("Reverse Lunge", "Glutes, legs", "3 x 8-10 per side"),
            ("Lying Leg Curl", "Hamstrings", "3 x 10-15"),
            ("Seated Calf Raise", "Calves", "3 x 12-20"),
            ("Dead Bug", "Core", "3 x 10 per side"),
        ],
        "Push A": [
            ("Flat Bench Press", "Middle chest (sternal fibres), triceps", "3 x 6-10"),
            ("Incline Dumbbell Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Cable Chest Fly", "Middle chest; controlled horizontal adduction", "2 x 10-15"),
            ("Dumbbell Shoulder Press", "Front shoulders, triceps", "3 x 8-12"),
            ("Cable Lateral Raise", "Side shoulders", "3 x 12-15"),
            ("Cable Triceps Pushdown", "Triceps", "3 x 10-15"),
        ],
        "Pull A": [
            ("Lat Pulldown", "Lats, biceps", "3 x 8-12"),
            ("Seated Cable Row", "Mid-back", "3 x 8-12"),
            ("Chest-Supported Row", "Upper back", "2 x 8-12"),
            ("Reverse Pec Deck", "Rear shoulders", "2 x 12-15"),
            ("Dumbbell Curl", "Biceps", "3 x 10-15"),
        ],
        "Legs A - Quads": [
            ("Hack Squat", "Quads, glutes", "3 x 6-10"),
            ("Leg Press", "Quads", "3 x 10-12"),
            ("Leg Extension", "Quads", "2 x 12-15"),
            ("Seated Leg Curl", "Hamstrings", "2 x 10-15"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
        ],
        "Push B": [
            ("Incline Chest Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Decline Chest Press or Assisted Dips", "Lower chest (sternal/costal emphasis), triceps", "3 x 8-12"),
            ("High-to-low Cable Fly", "Lower chest emphasis", "2 x 10-15"),
            ("Machine Shoulder Press", "Front shoulders, triceps", "3 x 8-12"),
            ("Dumbbell Lateral Raise", "Side shoulders", "3 x 12-15"),
            ("Overhead Cable Triceps Extension", "Triceps", "3 x 10-15"),
        ],
        "Pull B": [
            ("Assisted Pull-up", "Lats, biceps", "3 x 6-10"),
            ("One-arm Cable Row", "Back", "3 x 8-12 per side"),
            ("Cable Face Pull", "Rear shoulders, upper back", "3 x 12-15"),
            ("Straight-arm Pulldown", "Lats", "2 x 12-15"),
            ("Hammer Curl", "Biceps, forearms", "3 x 10-15"),
        ],
        "Legs B - Hamstrings & Glutes": [
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Hip Thrust", "Glutes", "3 x 8-12"),
            ("Reverse Lunge", "Glutes, legs", "3 x 8-10 per side"),
            ("Lying Leg Curl", "Hamstrings", "3 x 10-15"),
            ("Seated Calf Raise", "Calves", "3 x 12-20"),
        ],
    },
    "Dumbbells": {
        "Full Body A": [
            ("Goblet Squat", "Quads, glutes", "3 x 8-12"),
            ("Dumbbell Floor Press", "Chest, triceps", "3 x 8-12"),
            ("One-arm Dumbbell Row", "Back, biceps", "3 x 8-12 per side"),
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Dumbbell Lateral Raise", "Shoulders", "2 x 12-15"),
            ("Plank", "Core", "3 x 30-45 sec"),
        ],
        "Full Body B": [
            ("Reverse Lunge", "Quads, glutes", "3 x 8-10 per side"),
            ("Dumbbell Shoulder Press", "Shoulders, triceps", "3 x 8-12"),
            ("Dumbbell Row", "Back, biceps", "3 x 8-12"),
            ("Incline Dumbbell Press (if bench available)", "Upper chest emphasis, triceps", "3 x 8-12"),
            ("Dumbbell Curl", "Biceps", "2 x 10-15"),
            ("Dead Bug", "Core", "3 x 10 per side"),
        ],
        "Full Body C": [
            ("Dumbbell Split Squat", "Quads, glutes", "3 x 8-10 per side"),
            ("Dumbbell Floor Press", "Chest, triceps", "3 x 8-12"),
            ("Renegade Row", "Back, core", "3 x 8 per side"),
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Hammer Curl", "Biceps, forearms", "2 x 10-15"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
        ],
        "Upper A": [
            ("Dumbbell Floor Press", "Chest, triceps", "3 x 8-12"),
            ("One-arm Dumbbell Row", "Back, biceps", "3 x 8-12 per side"),
            ("Dumbbell Shoulder Press", "Shoulders", "3 x 8-12"),
            ("Dumbbell Lateral Raise", "Side shoulders", "2 x 12-15"),
            ("Dumbbell Curl", "Biceps", "2 x 10-15"),
            ("Overhead Dumbbell Triceps Extension", "Triceps", "2 x 10-15"),
        ],
        "Lower A - Quads": [
            ("Goblet Squat", "Quads, glutes", "3 x 8-12"),
            ("Dumbbell Split Squat", "Quads, glutes", "3 x 8-10 per side"),
            ("Reverse Lunge", "Legs, glutes", "2 x 10 per side"),
            ("Dumbbell Romanian Deadlift", "Hamstrings", "2 x 10-12"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
            ("Plank", "Core", "3 x 30-45 sec"),
        ],
        "Upper B": [
            ("Incline Dumbbell Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Decline Dumbbell Press (if decline bench available; otherwise flat press)", "Lower or middle chest emphasis, triceps", "2 x 8-12"),
            ("Chest-supported Dumbbell Row", "Back", "3 x 8-12"),
            ("Dumbbell Pullover", "Lats, chest", "2 x 10-12"),
            ("Rear Delt Fly", "Rear shoulders", "3 x 12-15"),
            ("Hammer Curl", "Biceps, forearms", "2 x 10-15"),
            ("Dumbbell Kickback", "Triceps", "2 x 12-15"),
        ],
        "Lower B - Hamstrings & Glutes": [
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Dumbbell Glute Bridge", "Glutes", "3 x 10-15"),
            ("Step-up", "Glutes, quads", "3 x 8-10 per side"),
            ("Single-leg Romanian Deadlift", "Hamstrings, balance", "2 x 8-10 per side"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
            ("Dead Bug", "Core", "3 x 10 per side"),
        ],
        "Push A": [
            ("Flat Dumbbell Bench Press (or Floor Press)", "Middle chest emphasis, triceps", "3 x 8-12"),
            ("Incline Dumbbell Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Dumbbell Squeeze Press", "Middle chest emphasis, triceps", "2 x 10-15"),
            ("Dumbbell Shoulder Press", "Front shoulders, triceps", "3 x 8-12"),
            ("Dumbbell Lateral Raise", "Side shoulders", "3 x 12-15"),
            ("Overhead Dumbbell Triceps Extension", "Triceps", "3 x 10-15"),
        ],
        "Pull A": [
            ("One-arm Dumbbell Row", "Back, biceps", "3 x 8-12 per side"),
            ("Chest-supported Dumbbell Row", "Upper back", "3 x 8-12"),
            ("Rear Delt Fly", "Rear shoulders", "3 x 12-15"),
            ("Dumbbell Curl", "Biceps", "3 x 10-15"),
            ("Hammer Curl", "Biceps, forearms", "2 x 10-15"),
        ],
        "Legs A - Quads": [
            ("Goblet Squat", "Quads, glutes", "3 x 8-12"),
            ("Dumbbell Split Squat", "Quads, glutes", "3 x 8-10 per side"),
            ("Step-up", "Quads, glutes", "2 x 10 per side"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
        ],
        "Push B": [
            ("Incline Dumbbell Press", "Upper chest (clavicular fibres), triceps", "3 x 8-12"),
            ("Decline Dumbbell Press (if decline bench available)", "Lower chest emphasis, triceps", "3 x 8-12"),
            ("Flat Dumbbell Fly or Floor Fly", "Middle chest emphasis", "2 x 10-15"),
            ("Arnold Press", "Shoulders", "3 x 8-12"),
            ("Dumbbell Lateral Raise", "Side shoulders", "3 x 12-15"),
            ("Dumbbell Kickback", "Triceps", "3 x 10-15"),
        ],
        "Pull B": [
            ("Dumbbell Pullover", "Lats, chest", "3 x 10-12"),
            ("Renegade Row", "Back, core", "3 x 8 per side"),
            ("Rear Delt Fly", "Rear shoulders", "3 x 12-15"),
            ("Concentration Curl", "Biceps", "3 x 10-15"),
            ("Hammer Curl", "Biceps, forearms", "2 x 10-15"),
        ],
        "Legs B - Hamstrings & Glutes": [
            ("Dumbbell Romanian Deadlift", "Hamstrings, glutes", "3 x 8-12"),
            ("Dumbbell Glute Bridge", "Glutes", "3 x 10-15"),
            ("Single-leg Romanian Deadlift", "Hamstrings, balance", "3 x 8-10 per side"),
            ("Step-up", "Glutes, legs", "2 x 10 per side"),
            ("Standing Calf Raise", "Calves", "3 x 12-20"),
        ],
    },
    "Bodyweight": {
        "Full Body A": [
            ("Bodyweight Squat", "Quads, glutes", "3 x 10-15"),
            ("Incline Push-up", "Chest, triceps", "3 x 8-15"),
            ("Backpack Row", "Back, biceps", "3 x 10-15"),
            ("Glute Bridge", "Glutes", "3 x 12-20"),
            ("Calf Raise", "Calves", "3 x 15-20"),
            ("Plank", "Core", "3 x 20-45 sec"),
        ],
        "Full Body B": [
            ("Reverse Lunge", "Quads, glutes", "3 x 8-12 per side"),
            ("Push-up", "Chest, triceps", "3 x 6-15"),
            ("Backpack Romanian Deadlift", "Hamstrings, glutes", "3 x 10-15"),
            ("Pike Push-up", "Shoulders, triceps", "3 x 6-12"),
            ("Bird Dog", "Core, stability", "3 x 10 per side"),
            ("Calf Raise", "Calves", "3 x 15-20"),
        ],
        "Full Body C": [
            ("Split Squat", "Quads, glutes", "3 x 8-12 per side"),
            ("Forward-lean Push-up or Parallel-bar Dip (if safe and available)", "Lower chest emphasis, triceps", "3 x 6-12"),
            ("Close-grip Push-up", "Chest, triceps", "2 x 6-12"),
            ("Backpack Row", "Back, biceps", "3 x 10-15"),
            ("Single-leg Glute Bridge", "Glutes", "3 x 8-12 per side"),
            ("Prone Y-T Raises", "Upper back, shoulders", "2 x 10-12"),
            ("Dead Bug", "Core", "3 x 10 per side"),
        ],
        "Upper A": [
            ("Push-up", "Chest, triceps", "3 x 6-15"),
            ("Backpack Row", "Back, biceps", "3 x 10-15"),
            ("Pike Push-up", "Shoulders", "3 x 6-12"),
            ("Prone Y-T Raises", "Rear shoulders, upper back", "2 x 10-12"),
            ("Close-grip Push-up", "Triceps", "2 x 6-12"),
        ],
        "Lower A - Quads": [
            ("Bodyweight Squat", "Quads, glutes", "3 x 10-15"),
            ("Split Squat", "Quads, glutes", "3 x 8-12 per side"),
            ("Reverse Lunge", "Quads, glutes", "2 x 10 per side"),
            ("Calf Raise", "Calves", "3 x 15-20"),
            ("Plank", "Core", "3 x 20-45 sec"),
        ],
        "Upper B": [
            ("Decline Push-up (feet elevated)", "Upper chest emphasis, shoulders, triceps", "3 x 6-12"),
            ("Forward-lean Push-up or Parallel-bar Dip (if safe and available)", "Lower chest emphasis, triceps", "2 x 6-12"),
            ("Backpack Row", "Back, biceps", "3 x 10-15"),
            ("Pike Push-up", "Shoulders", "3 x 6-12"),
            ("Prone Reverse Snow Angel", "Upper back, rear shoulders", "3 x 10-15"),
            ("Backpack Curl", "Biceps", "2 x 10-15"),
        ],
        "Lower B - Hamstrings & Glutes": [
            ("Backpack Romanian Deadlift", "Hamstrings, glutes", "3 x 10-15"),
            ("Single-leg Glute Bridge", "Glutes", "3 x 8-12 per side"),
            ("Hamstring Walkout", "Hamstrings, glutes", "3 x 6-10"),
            ("Reverse Lunge", "Glutes, legs", "2 x 10 per side"),
            ("Calf Raise", "Calves", "3 x 15-20"),
            ("Dead Bug", "Core", "3 x 10 per side"),
        ],
        "Push A": [
            ("Standard Push-up", "Middle chest emphasis, triceps", "3 x 6-15"),
            ("Incline Push-up", "Lower difficulty; chest overall with shoulder-friendly angle", "3 x 8-15"),
            ("Pike Push-up", "Shoulders, triceps", "3 x 6-12"),
            ("Close-grip Push-up", "Triceps", "2 x 6-12"),
        ],
        "Pull A": [
            ("Backpack Row", "Back, biceps", "3 x 10-15"),
            ("Prone Y-T Raises", "Upper back, rear shoulders", "3 x 10-12"),
            ("Backpack Curl", "Biceps", "3 x 10-15"),
            ("Reverse Snow Angel", "Upper back", "2 x 10-15"),
        ],
        "Legs A - Quads": [
            ("Bodyweight Squat", "Quads, glutes", "3 x 10-15"),
            ("Split Squat", "Quads, glutes", "3 x 8-12 per side"),
            ("Reverse Lunge", "Quads, glutes", "2 x 10 per side"),
            ("Calf Raise", "Calves", "3 x 15-20"),
        ],
        "Push B": [
            ("Decline Push-up (feet elevated)", "Upper chest emphasis, shoulders, triceps", "3 x 6-12"),
            ("Pike Push-up", "Shoulders, triceps", "3 x 6-12"),
            ("Forward-lean Push-up or Parallel-bar Dip (only if safe and available)", "Lower chest emphasis, triceps", "3 x 6-12"),
            ("Standard Push-up", "Middle chest emphasis", "2 x 8-15"),
            ("Close-grip Push-up", "Triceps", "2 x 6-12"),
        ],
        "Pull B": [
            ("Backpack Row", "Back, biceps", "3 x 10-15"),
            ("Prone Reverse Snow Angel", "Upper back, rear shoulders", "3 x 10-15"),
            ("Backpack Curl", "Biceps", "3 x 10-15"),
            ("Bird Dog", "Core, stability", "2 x 10 per side"),
        ],
        "Legs B - Hamstrings & Glutes": [
            ("Backpack Romanian Deadlift", "Hamstrings, glutes", "3 x 10-15"),
            ("Hamstring Walkout", "Hamstrings, glutes", "3 x 6-10"),
            ("Single-leg Glute Bridge", "Glutes", "3 x 8-12 per side"),
            ("Calf Raise", "Calves", "3 x 15-20"),
        ],
    },
}


# ----------------------------- PLAN GENERATOR -----------------------------

SPLITS = {
    2: [
        ("Day 1", "Full Body A"),
        ("Day 2", "Full Body B"),
    ],
    3: [
        ("Day 1", "Full Body A"),
        ("Day 2", "Full Body B"),
        ("Day 3", "Full Body C"),
    ],
    4: [
        ("Monday", "Upper A"),
        ("Tuesday", "Lower A - Quads"),
        ("Thursday", "Upper B"),
        ("Friday", "Lower B - Hamstrings & Glutes"),
    ],
    5: [
        ("Monday", "Push A"),
        ("Tuesday", "Pull A"),
        ("Wednesday", "Legs A - Quads"),
        ("Friday", "Push B"),
        ("Saturday", "Pull B"),
        # Five training days: the lower-body posterior-chain session alternates
        # into the next week to keep recovery reasonable.
    ],
    6: [
        ("Monday", "Push A"),
        ("Tuesday", "Pull A"),
        ("Wednesday", "Legs A - Quads"),
        ("Thursday", "Push B"),
        ("Friday", "Pull B"),
        ("Saturday", "Legs B - Hamstrings & Glutes"),
    ],
}


def make_weekly_plan(training_days, equipment):
    """Create a consistent weekly split with validated exercise keys."""
    training_days = int(training_days)
    if training_days not in SPLITS:
        raise ValueError("Choose between 2 and 6 training days.")
    if equipment not in EXERCISES:
        raise ValueError(f"Unsupported equipment choice: {equipment}")

    plan = []
    for day_name, workout_type in SPLITS[training_days]:
        exercise_library = EXERCISES[equipment]
        # Guard against accidental missing keys so the app shows a useful error.
        if workout_type not in exercise_library:
            raise KeyError(
                f"Workout '{workout_type}' is missing from the '{equipment}' "
                f"exercise library. Available: {list(exercise_library.keys())}"
            )

        exercises = [
            {"name": name, "muscles": muscles, "sets_reps": sets_reps}
            for name, muscles, sets_reps in exercise_library[workout_type]
        ]
        plan.append(
            {
                "day": day_name,
                "type": workout_type,
                "exercises": exercises,
            }
        )

    # For 5 days, the second lower-body session rotates into the following week.
    if training_days == 5:
        plan.append(
            {
                "day": "Next week rotation",
                "type": "Legs B - Hamstrings & Glutes",
                "exercises": [
                    {"name": name, "muscles": muscles, "sets_reps": sets_reps}
                    for name, muscles, sets_reps in EXERCISES[equipment]["Legs B - Hamstrings & Glutes"]
                ],
            }
        )
    return plan


# ----------------------------- STYLE -----------------------------

st.markdown(
    """
    <style>
    .stApp { background: #0b1020; color: #eef2ff; }
    [data-testid="stSidebar"] { background: #11182b; }
    .hero {
        padding: 1.4rem 1.6rem;
        border-radius: 18px;
        background: linear-gradient(120deg, #182b4d, #18203a);
        border: 1px solid rgba(255,255,255,0.09);
        margin-bottom: 1rem;
    }
    .hero h1 { margin: 0; font-size: 2.2rem; }
    .hero p { color: #c7d2fe; margin-bottom: 0; }
    div[data-testid="stMetric"] {
        background: #121a2e; padding: 1rem; border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .small-muted { color: #9ca3af; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------- SIDEBAR -----------------------------

with st.sidebar:
    st.markdown("# 💪 FITNEXORA")
    st.caption("Your personal fitness companion")
    st.divider()

    username = st.session_state["authenticated_user"]
    st.caption(f"Logged in as **{username}**")
    if st.button("Log out", width="stretch"):
        st.session_state["authenticated_user"] = None
        st.rerun()

    page = st.radio(
        "Navigate",
        [
            "Dashboard",
            "Workout Planner",
            "Nutrition Plan",
            "Nutrition Tracker",
            "AI Posture Coach",
            "Progress",
        ],
        index=0,
    )

    st.divider()
    st.markdown("**Profile settings**")
    goal = st.selectbox(
        "Primary goal",
        ["Muscle Gain", "Fat Loss", "General Fitness", "Strength"],
    )
    experience = st.selectbox(
        "Experience level",
        ["Beginner", "Intermediate", "Advanced"],
    )
    st.caption("Tip: choose a level that matches your current training experience.")


# ----------------------------- SHARED HELPERS -----------------------------

def show_plan(plan):
    for workout in plan:
        st.markdown(f"### {workout['day']} — {workout['type']}")
        rows = []
        for idx, exercise in enumerate(workout["exercises"], start=1):
            rows.append(
                {
                    "#": idx,
                    "Exercise": exercise.get("name", "Exercise"),
                    "Target muscles": exercise.get("muscles", exercise.get("target_muscles", "Not specified")),
                    "Sets / reps": exercise.get("sets_reps", exercise.get("sets_reps_scheme", "Not specified")),
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def plan_training_day_count(plan):
    return sum(1 for item in plan if item.get("day") != "Next week rotation")


# ----------------------------- DASHBOARD -----------------------------

if page == "Dashboard":
    st.markdown(
        """
        <div class="hero">
            <h1>Welcome to FITNEXORA 👋</h1>
            <p>A simple fitness dashboard to plan workouts, track nutrition, and review progress.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    plans = load_plans(username)
    nutrition_df = load_nutrition(username)

    c1, c2, c3 = st.columns(3)
    c1.metric("Saved workout plans", len(plans))
    c2.metric("Nutrition logs", len(nutrition_df))
    c3.metric("Current goal", goal)

    st.subheader("Start here")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🏋️ Workout Planner")
        st.write("Generate a weekly split based on how many days you train and what equipment you have.")
        if st.button("Open Workout Planner", width="stretch"):
            st.session_state["requested_page"] = "Workout Planner"
            st.rerun()
    with col2:
        st.markdown("#### 🥗 Nutrition Tracker")
        st.write("Save daily calories and macronutrients in your local database.")
        if st.button("Open Nutrition Tracker", width="stretch"):
            st.session_state["requested_page"] = "Nutrition Tracker"
            st.rerun()

    if st.session_state.get("requested_page"):
        requested = st.session_state.pop("requested_page")
        st.info(f"Select **{requested}** from the sidebar to continue.")

    st.subheader("Your latest workout plan")
    if plans:
        latest = plans[0]
        st.caption(
            f"Saved {latest['created_at']} · {latest['training_days']} training days · "
            f"{latest['equipment']} · Goal: {latest['goal']}"
        )
        show_plan(latest["plan"])
    else:
        st.info("No saved plan yet. Open Workout Planner to create your first one.")


# ----------------------------- WORKOUT PLANNER -----------------------------

elif page == "Workout Planner":
    st.markdown("## 🏋️ Workout Planner")
    st.write("Create a balanced weekly routine. Push sessions include upper-, middle-, and lower-chest emphasis where equipment allows. The plan uses exercise templates, not a trained ML prediction.")

    with st.form("workout_form"):
        col1, col2 = st.columns(2)
        with col1:
            training_days = st.selectbox("Training days per week", [2, 3, 4, 5, 6], index=2)
            equipment = st.selectbox("Available equipment", ["Gym", "Dumbbells", "Bodyweight"])
        with col2:
            st.write(f"**Goal:** {goal}")
            st.write(f"**Experience:** {experience}")
            st.caption("Rest at least one day when needed. Choose loads that let you keep good form.")

        submitted = st.form_submit_button("Generate & Save My Plan", width="stretch")

    if submitted:
        try:
            generated_plan = make_weekly_plan(training_days, equipment)
            save_plan(username, training_days, equipment, goal, generated_plan, experience)
            st.session_state["current_plan"] = generated_plan
            st.session_state["current_plan_meta"] = {
                "training_days": training_days,
                "equipment": equipment,
                "goal": goal,
            }
            st.success("Workout plan generated and saved!")
        except (KeyError, ValueError) as exc:
            st.error(f"Could not generate this plan: {exc}")

    current_plan = st.session_state.get("current_plan")
    current_meta = st.session_state.get("current_plan_meta")
    if current_plan:
        st.subheader("Your generated plan")
        if current_meta:
            st.caption(
                f"{current_meta['training_days']} training days · {current_meta['equipment']} · "
                f"Goal: {current_meta['goal']}"
            )
        show_plan(current_plan)

        st.info(
            "Training guidance: warm up before lifting, use controlled technique, and stop if an exercise causes pain. "
            "Increase weights gradually only when you can complete the target reps with good form."
        )

    st.divider()
    st.subheader("Recent saved plans")
    saved = load_plans(username)
    if saved:
        for saved_plan in saved[:5]:
            with st.expander(
                f"{saved_plan['created_at']} — {saved_plan['training_days']} days — {saved_plan['equipment']}"
            ):
                show_plan(saved_plan["plan"])
    else:
        st.caption("Your saved plans will appear here.")


# ----------------------------- PERSONALIZED NUTRITION PLAN -----------------------------

elif page == "Nutrition Plan":
    st.markdown("## 🥗 Personalized Nutrition Plan")
    st.write("Enter your profile details to create a practical meal structure. Your profile and plan are stored only under your logged-in username in this local app database.")
    existing = load_profile(username) or {
        "age": 25, "height_cm": 170.0, "weight_kg": 70.0, "sex": "Prefer not to say",
        "activity_level": "Moderately active", "nutrition_goal": "Maintain",
        "diet_preference": "Non-vegetarian", "allergies": "",
    }
    with st.form("nutrition_profile_form"):
        a, b, c = st.columns(3)
        with a:
            age = st.number_input("Age (years)", min_value=10, max_value=100, value=int(existing["age"]), step=1)
            height_cm = st.number_input("Height (cm)", min_value=100.0, max_value=230.0, value=float(existing["height_cm"]), step=0.5)
        with b:
            weight_kg = st.number_input("Weight (kg)", min_value=20.0, max_value=300.0, value=float(existing["weight_kg"]), step=0.5)
            sex = st.selectbox("Sex used for estimate (optional)", ["Prefer not to say", "Male", "Female"], index=["Prefer not to say", "Male", "Female"].index(existing["sex"]))
        with c:
            activity_options = ["Mostly sitting", "Lightly active", "Moderately active", "Very active"]
            activity_level = st.selectbox("Daily activity", activity_options, index=activity_options.index(existing["activity_level"]))
            goal_options = ["Maintain", "Muscle gain", "Fat loss"]
            nutrition_goal = st.selectbox("Nutrition goal", goal_options, index=goal_options.index(existing["nutrition_goal"]))
        diet_options = ["Non-vegetarian", "Vegetarian", "Vegan"]
        diet_preference = st.selectbox("Diet preference", diet_options, index=diet_options.index(existing["diet_preference"]))
        allergies = st.text_input("Allergies / foods to avoid (optional)", value=existing["allergies"], placeholder="e.g. peanuts, lactose")
        profile_submitted = st.form_submit_button("Save profile & build my plan", width="stretch")
    if profile_submitted:
        profile_to_save = {
            "age": age, "height_cm": height_cm, "weight_kg": weight_kg, "sex": sex,
            "activity_level": activity_level, "nutrition_goal": nutrition_goal,
            "diet_preference": diet_preference, "allergies": allergies,
        }
        save_profile(username, profile_to_save)
        st.success("Profile saved! Your personalized nutrition suggestions are below.")
        existing = profile_to_save

    saved_profile = load_profile(username)
    if saved_profile:
        st.subheader("Your nutrition guide")
        protein_foods, meals, allergy_note = make_meal_ideas(saved_profile)
        st.caption(f"Profile: {saved_profile['age']} years · {saved_profile['height_cm']:.1f} cm · {saved_profile['weight_kg']:.1f} kg · {saved_profile['diet_preference']}")
        st.info("Use this as a flexible meal structure, not a medical prescription. Portion sizes depend on hunger, growth, training, culture, and health needs.")
        if int(saved_profile["age"]) < 18:
            st.warning("Because you're under 18, this app won't prescribe a calorie limit or weight-loss target. Focus on regular balanced meals, enough food for growth and activity, and discuss individual needs with a parent/guardian and a qualified healthcare professional or registered dietitian.")
        else:
            estimate = nutrition_estimate(saved_profile)
            if estimate:
                m1, m2, m3 = st.columns(3)
                m1.metric("Rough daily energy estimate", f"{estimate['calories']:,} kcal")
                m2.metric("Protein guide", f"{estimate['protein']} g/day")
                m3.metric("Maintenance estimate", f"{estimate['maintenance']:,} kcal")
                st.caption(f"Approximate macro starting point: carbohydrates {estimate['carbs']} g, fats {estimate['fat']} g, protein {estimate['protein']} g. These are estimates, not exact requirements.")
        st.markdown("### Detailed daily meal plan")
        st.caption("Ingredient weights are approximate edible portions. Oats are weighed dry; rice, dal, chicken and vegetables are weighed cooked; milk is measured in ml. Nutrition values are estimates and vary by brand, recipe and cooking method.")
        daily_totals = {k: 0.0 for k in ["kcal", "protein", "carbs", "fat", *MICRO_LABELS.keys()]}
        for meal_name, rows in meals:
            with st.expander(meal_name, expanded=True):
                df = pd.DataFrame(rows)
                display_cols = ["Food", "Amount", "kcal", "protein", "carbs", "fat"]
                st.dataframe(df[display_cols].rename(columns={"kcal":"Calories (kcal)","protein":"Protein (g)","carbs":"Carbs (g)","fat":"Fat (g)"}), hide_index=True, width="stretch")
                st.markdown("**Micronutrients per ingredient**")
                micro_df = df[["Food", "Amount", *MICRO_LABELS.keys()]].rename(columns=MICRO_LABELS)
                st.dataframe(micro_df, hide_index=True, width="stretch")
                for key in daily_totals:
                    daily_totals[key] += sum(float(r.get(key, 0)) for r in rows)
        st.markdown("### Approximate daily total")
        a,b,c,d = st.columns(4)
        a.metric("Calories", f"{daily_totals['kcal']:.0f} kcal")
        b.metric("Protein", f"{daily_totals['protein']:.1f} g")
        c.metric("Carbohydrates", f"{daily_totals['carbs']:.1f} g")
        d.metric("Fat", f"{daily_totals['fat']:.1f} g")
        micro_summary = pd.DataFrame([{"Nutrient": MICRO_LABELS[k], "Approx. daily total": round(daily_totals[k], 1)} for k in MICRO_LABELS])
        st.dataframe(micro_summary, hide_index=True, width="stretch")
        st.caption("Micronutrients shown are key examples (fiber, calcium, iron, potassium, magnesium, zinc, vitamins A/C/B12, folate and sodium), not every known micronutrient. Iodine, vitamin D, vitamin E, vitamin K and other nutrients may not be fully represented. Use food labels or a dietitian for precise needs.")
        st.markdown("**Protein-rich options:** " + protein_foods + ".")
        st.caption(allergy_note)
        st.markdown("### Simple daily habits")
        st.markdown("- Include a protein source and fruit/vegetables across the day.\n- Drink water regularly, especially around activity.\n- Include carbohydrate foods such as rice, roti, oats, potatoes or fruit to support energy.\n- Adjust meal size to appetite and activity; avoid skipping meals to compensate for eating more earlier.")
    else:
        st.info("Fill in your profile above and save it to generate your nutrition guide.")


# ----------------------------- NUTRITION TRACKER -----------------------------

elif page == "Nutrition Tracker":
    st.markdown("## 🥗 Nutrition Tracker")
    st.write("Log your daily nutrition. Values are estimates; use food labels or reliable nutrition data for accuracy.")

    with st.form("nutrition_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            log_date = st.date_input("Date", value=date.today())
            calories = st.number_input("Calories (kcal)", min_value=0, max_value=10000, value=2000, step=50)
        with col2:
            protein = st.number_input("Protein (g)", min_value=0.0, max_value=500.0, value=100.0, step=5.0)
            carbs = st.number_input("Carbs (g)", min_value=0.0, max_value=1000.0, value=250.0, step=5.0)
        with col3:
            fats = st.number_input("Fats (g)", min_value=0.0, max_value=500.0, value=65.0, step=5.0)
            notes = st.text_input("Notes (optional)", placeholder="Meals, training, or anything to remember")

        nutrition_submitted = st.form_submit_button("Save nutrition log", width="stretch")

    if nutrition_submitted:
        save_nutrition(username, log_date, calories, protein, carbs, fats, notes)
        st.success("Nutrition log saved!")

    nutrition_df = load_nutrition(username)
    if not nutrition_df.empty:
        st.subheader("Your nutrition history")
        st.dataframe(nutrition_df, hide_index=True, width="stretch")

        chart_df = nutrition_df.copy()
        chart_df["Date"] = pd.to_datetime(chart_df["Date"])
        chart_df = chart_df.sort_values("Date")
        st.plotly_chart(
            px.line(
                chart_df,
                x="Date",
                y="Calories",
                markers=True,
                title="Daily calorie log",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.line(
                chart_df,
                x="Date",
                y=["Protein (g)", "Carbs (g)", "Fats (g)"],
                markers=True,
                title="Daily macronutrient log",
            ),
            width="stretch",
        )
    else:
        st.info("No nutrition entries yet. Save a log above to start tracking.")


# ----------------------------- POSTURE COACH -----------------------------

elif page == "AI Posture Coach":
    st.markdown("## 📷 AI Posture Coach")
    st.write(
        "This section is a placeholder for the future webcam posture and repetition-counting feature."
    )
    st.warning(
        "Live pose detection is not enabled in this version. The app does not currently access your camera "
        "or claim to measure exercise form."
    )
    st.markdown("### Planned next steps")
    st.markdown(
        """
        - Add MediaPipe pose landmarks.
        - Calculate joint angles for selected exercises.
        - Add basic rep counting and feedback.
        - Test carefully; camera-based feedback is not a substitute for a qualified coach.
        """
    )


# ----------------------------- PROGRESS -----------------------------

elif page == "Progress":
    st.markdown("## 📈 Progress")
    plans = load_plans(username)
    nutrition_df = load_nutrition(username)

    c1, c2, c3 = st.columns(3)
    c1.metric("Workout plans saved", len(plans))
    c2.metric("Nutrition entries", len(nutrition_df))
    c3.metric(
        "Training days in latest plan",
        plan_training_day_count(plans[0]["plan"]) if plans else 0,
    )

    if plans:
        st.subheader("Workout plan history")
        history_rows = [
            {
                "Saved at": p["created_at"],
                "Training days": p["training_days"],
                "Equipment": p["equipment"],
                "Goal": p["goal"],
            }
            for p in plans
        ]
        st.dataframe(pd.DataFrame(history_rows), hide_index=True, width="stretch")
    else:
        st.info("Generate and save a workout plan to see it here.")

    if not nutrition_df.empty:
        st.subheader("Nutrition overview")
        nutrition_df["Date"] = pd.to_datetime(nutrition_df["Date"])
        st.plotly_chart(
            px.bar(
                nutrition_df.sort_values("Date"),
                x="Date",
                y="Protein (g)",
                title="Protein logged by date",
            ),
            width="stretch",
        )
    else:
        st.info("Save nutrition logs to see nutrition trends here.")

st.markdown("---")
st.caption("FITNEXORA · Portfolio project · Workout templates are educational and should be adapted to individual needs.")
