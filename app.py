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
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = str(Path(__file__).resolve().parent / "fitnexora.db")

# Professional UI polish: hide radio dots in the main navigation and use pill tabs.
st.markdown("""
<style>
.stRadio [role="radiogroup"] { gap: .55rem !important; flex-wrap: wrap !important; }
.stRadio [role="radiogroup"] label {
  background: #121d2f !important; border: 1px solid #2b3b52 !important;
  border-radius: 12px !important; padding: .62rem .9rem !important;
  margin: 0 !important; transition: all .15s ease !important;
}
.stRadio [role="radiogroup"] label:hover { border-color: #2dd4bf !important; background: #17283a !important; }
.stRadio [role="radiogroup"] label > div:first-child { display: none !important; }
.stRadio input[type="radio"], .stRadio [data-baseweb="radio"] { display:none !important; }
.stRadio [role="radiogroup"] label p { font-weight: 650 !important; font-size: .92rem !important; }
.stRadio [role="radiogroup"] label:has(input:checked) {
  background: linear-gradient(135deg,#145e59,#1b756c) !important;
  border-color: #5eead4 !important; color: #f0fdfa !important;
}
.stButton > button, .stFormSubmitButton > button {
  border-radius: 10px !important; border: 1px solid #34465e !important;
  font-weight: 650 !important; transition: all .15s ease !important;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
  border-color: #2dd4bf !important; color: #ccfbf1 !important; transform: translateY(-1px);
}
div[data-testid="stExpander"] { border: 1px solid #2b3b52 !important; border-radius: 12px !important; }
.muscle-info-card { background: linear-gradient(145deg,#111d30,#0c1422); border:1px solid #2b3b52; border-radius:16px; padding:22px; }
</style>
""", unsafe_allow_html=True)


# ----------------------------- EXACT EXERCISE MEDIA MATCHING -----------------------------
# Never use a fuzzy/closest movement animation: e.g. incline press must not show a flat press.
EXERCISE_NAME_ALIASES = {
    "incline dumbbell press": ["incline dumbbell bench press", "incline bench press with dumbbells"],
    "flat dumbbell press": ["flat dumbbell bench press", "dumbbell bench press"],
    "bench press": ["barbell bench press", "barbell bench press medium grip"],
    "assisted pull up": ["assisted pull-up", "assisted pull up machine", "machine assisted pull up"],
    "pull up": ["pull-up", "pullups", "pull ups"],
    "push up": ["push-up", "pushups", "push ups", "standard push up"],
    "chest supported row": ["chest supported dumbbell row", "chest supported machine row"],
    "chest fly machine": ["machine chest fly", "pec deck fly", "lever seated fly"],
    "seated cable fly": ["cable seated fly", "seated cable chest fly"],
    "dumbbell shoulder press": ["seated dumbbell shoulder press", "dumbbell seated shoulder press", "standing dumbbell shoulder press"],
    "dumbbell curl": ["dumbbell biceps curl", "alternating dumbbell curl", "alternate dumbbell curl"],
    "hammer curl": ["dumbbell hammer curl", "hammer curls"],
    "cable triceps pushdown": ["triceps pushdown", "triceps pressdown", "cable triceps pressdown"],
    "triceps pushdown": ["cable triceps pushdown", "triceps pressdown", "cable triceps pressdown"],
    "goblet squat": ["dumbbell goblet squat", "kettlebell goblet squat"],
    "standing calf raise": ["bodyweight standing calf raise", "standing calf raises"],
    "lat pulldown": ["cable lat pulldown", "lat pull down", "lat pulldown wide grip"],
    "seated cable row": ["cable seated row", "seated row cable", "seated cable rows"],
    "cable face pull": ["face pull", "rope face pull", "cable face pulls"],
    "hip thrust": ["barbell hip thrust", "bodyweight hip thrust", "dumbbell hip thrust"],
    "romanian deadlift": ["dumbbell romanian deadlift", "barbell romanian deadlift", "romanian deadlift with dumbbells", "romanian deadlift with barbell"],
    "reverse lunge": ["bodyweight reverse lunge", "dumbbell reverse lunge", "reverse lunges"],
    "back extension": ["hyperextension", "roman chair back extension", "back extensions"],
    "reverse pec deck": ["reverse pec deck fly", "rear delt machine fly", "lever reverse fly"],
    "leg extension": ["lever leg extension", "leg extensions"],
    "dumbbell lateral raise": ["dumbbell side lateral raise", "side lateral raise with dumbbells"],
    "barbell curl": ["barbell biceps curl", "ez bar curl"],
    "dead bug": ["dead bug exercise", "dead bug alternating arm and leg extension"],
    "plank": ["front plank", "forearm plank", "elbow plank"],
    "squat": ["bodyweight squat", "air squat", "body weight squat"],
}

def normalize_exercise_title(value):
    import re
    value = str(value or "").lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    words = value.split()
    plural_map = {"pushups":"pushup", "pullups":"pullup", "curls":"curl", "raises":"raise", "rows":"row", "squats":"squat", "lunges":"lunge", "extensions":"extension", "dumbbells":"dumbbell", "barbells":"barbell"}
    words = [plural_map.get(w, w) for w in words]
    return " ".join(words)

def exercise_title_aliases(name):
    normalized = normalize_exercise_title(name)
    aliases = {normalized}
    for alias in EXERCISE_NAME_ALIASES.get(normalized, []):
        aliases.add(normalize_exercise_title(alias))
    return aliases

def find_exact_exercise_row(name, rows):
    """Return only an exact name/explicit alias match; never return a fuzzy closest exercise."""
    aliases = exercise_title_aliases(name)
    exact = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        candidates = [row.get("name"), row.get("title"), row.get("exercise_name"), row.get("exerciseName")]
        row_aliases = row.get("aliases", [])
        if isinstance(row_aliases, str):
            candidates.extend(part.strip() for part in row_aliases.split(","))
        elif isinstance(row_aliases, list):
            candidates.extend(row_aliases)
        normalized_candidates = {normalize_exercise_title(v) for v in candidates if v}
        if normalized_candidates & aliases:
            exact.append(row)
    if not exact:
        return None
    # Prefer an exact canonical name, then a row with a direct animation URL.
    canonical = normalize_exercise_title(name)
    exact.sort(key=lambda row: (
        0 if normalize_exercise_title(row.get("name") or row.get("title") or "") == canonical else 1,
        0 if (row.get("gif_url") or row.get("gifUrl") or row.get("video_url") or row.get("videoUrl") or row.get("video") or row.get("videos")) else 1,
    ))
    return exact[0]

def exercise_media_url(row):
    if not isinstance(row, dict):
        return None
    media = row.get("gif_url") or row.get("gifUrl") or row.get("animation_url") or row.get("video_url") or row.get("videoUrl") or row.get("video")
    videos = row.get("videos", {})
    if isinstance(videos, dict):
        media = media or videos.get("male") or videos.get("female") or videos.get("url")
    if not isinstance(media, str) or not media.strip():
        return None
    media = media.strip()
    if media.startswith(("https://", "http://")):
        return media
    # Relative GIF paths are used by the hasaneyldrm ExerciseDB mirror.
    if media.startswith(("videos/", "images/", "./videos/", "./images/")):
        return "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/" + media.lstrip("./")
    return None

@st.cache_data(ttl=21600, show_spinner=False)
def search_youtube_video_id(exercise_name):
    """Find a YouTube result only when its title includes the exercise's key terms."""
    import requests, re, json, html
    from urllib.parse import quote_plus
    query = f"{exercise_name} exercise proper form tutorial"
    try:
        response = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query}, timeout=8,
            headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"},
        )
        response.raise_for_status()
        page = response.text
        blocks = re.split(r'"videoRenderer"\s*:\s*\{', page)[1:]
        target_words = normalize_exercise_title(exercise_name).split()
        generic = {"the", "a", "and", "with", "exercise", "proper", "form", "tutorial", "how", "to", "do"}
        required = [w for w in target_words if w not in generic]
        # Require the actual movement and modifiers (incline/flat, dumbbell/barbell, etc.) in the result title.
        for block in blocks[:18]:
            vid = re.search(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', block[:12000])
            title_match = re.search(r'"title"\s*:\s*\{"runs"\s*:\s*\[\{"text"\s*:\s*"((?:\\.|[^"\\])*)"', block[:12000])
            if not vid or not title_match:
                continue
            raw_title = title_match.group(1)
            try:
                title = json.loads('"' + raw_title + '"')
            except Exception:
                title = html.unescape(raw_title.replace('\\"','"'))
            title_norm = normalize_exercise_title(title)
            title_words = set(title_norm.split())
            # Common abbreviations on exercise channels.
            if "dumbbell" in required and ("db" in title_words):
                title_words.add("dumbbell")
            if "barbell" in required and "bb" in title_words:
                title_words.add("barbell")
            if required and all(word in title_words for word in required):
                return vid.group(1), title
    except Exception:
        return None
    return None

def youtube_search_url(exercise_name):
    from urllib.parse import quote_plus
    return "https://www.youtube.com/results?search_query=" + quote_plus(f"{exercise_name} exercise proper form tutorial")

def show_youtube_fallback(exercise_name, height=480):
    """Embed a verified title-matched YouTube result when possible; otherwise show an in-app search player plus link."""
    import streamlit.components.v1 as components
    result = search_youtube_video_id(exercise_name)
    if result:
        video_id, video_title = result
        st.video(f"https://www.youtube.com/watch?v={video_id}")
        st.caption(f"YouTube fallback · matched title: {video_title}")
    else:
        from urllib.parse import quote_plus
        query = quote_plus(f"{exercise_name} exercise proper form tutorial")
        # Search-list embeds are not supported by every YouTube/browser configuration; provide a direct search link too.
        components.iframe(f"https://www.youtube.com/embed?listType=search&list={query}", height=height, scrolling=False)
        st.markdown(f"[Open exact exercise search on YouTube ↗]({youtube_search_url(exercise_name)})")


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
        # Backward-compatible migration for existing local databases.
        profile_columns = {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)").fetchall()}
        if "supplement_preference" not in profile_columns:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN supplement_preference TEXT NOT NULL DEFAULT 'No supplement'")
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
            "SELECT age, height_cm, weight_kg, sex, activity_level, nutrition_goal, diet_preference, allergies, supplement_preference "
            "FROM user_profiles WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
    if not row:
        return None
    return {
        "age": row[0], "height_cm": row[1], "weight_kg": row[2], "sex": row[3],
        "activity_level": row[4], "nutrition_goal": row[5],
        "diet_preference": row[6], "allergies": row[7],
        "supplement_preference": row[8] if len(row) > 8 and row[8] else "No supplement",
    }

def save_profile(username, profile):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO user_profiles
            (username, age, height_cm, weight_kg, sex, activity_level, nutrition_goal, diet_preference, allergies, supplement_preference, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                age=excluded.age, height_cm=excluded.height_cm, weight_kg=excluded.weight_kg,
                sex=excluded.sex, activity_level=excluded.activity_level, nutrition_goal=excluded.nutrition_goal,
                diet_preference=excluded.diet_preference, allergies=excluded.allergies,
                supplement_preference=excluded.supplement_preference, updated_at=excluded.updated_at
            """,
            (username, int(profile["age"]), float(profile["height_cm"]), float(profile["weight_kg"]),
             profile["sex"], profile["activity_level"], profile["nutrition_goal"],
             profile["diet_preference"], profile.get("allergies", "").strip(),
             profile.get("supplement_preference", "No supplement"), datetime.now().isoformat(timespec="seconds")),
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
    protein = round(1.5 * weight)
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
    # Soy chunks / Nutrela are measured dry; hydration changes cooked weight, not total protein.
    "Soy chunks (dry, Nutrela-style)": {"kcal":345,"protein":52,"carbs":33,"fat":0.5,"fiber":13,"calcium":350,"iron":20,"potassium":1500,"magnesium":250,"zinc":3.5,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":300,"sodium":20},
    "Pea-rice protein powder": {"kcal":390,"protein":78,"carbs":8,"fat":6,"fiber":3,"calcium":150,"iron":8,"potassium":250,"magnesium":80,"zinc":3,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":0,"sodium":450},
    "Whey protein powder": {"kcal":400,"protein":80,"carbs":8,"fat":6,"fiber":0,"calcium":500,"iron":1,"potassium":500,"magnesium":80,"zinc":3,"vitamin_c":0,"vitamin_a":0,"b12":2,"folate":0,"sodium":350},
    "Soy protein powder": {"kcal":370,"protein":80,"carbs":8,"fat":3,"fiber":3,"calcium":200,"iron":12,"potassium":800,"magnesium":200,"zinc":4,"vitamin_c":0,"vitamin_a":0,"b12":0,"folate":200,"sodium":500},
}
MICRO_LABELS = {
    "fiber":"Fiber (g)", "calcium":"Calcium (mg)", "iron":"Iron (mg)",
    "potassium":"Potassium (mg)", "magnesium":"Magnesium (mg)", "zinc":"Zinc (mg)",
    "vitamin_c":"Vitamin C (mg)", "vitamin_a":"Vitamin A (µg RAE)",
    "b12":"Vitamin B12 (µg)", "folate":"Folate (µg)", "sodium":"Sodium (mg)",
}

def _allergy_terms(profile):
    raw = str(profile.get("allergies", "") or "").lower()
    terms = {part.strip() for part in raw.replace(";", ",").replace("/", ",").split(",") if part.strip()}
    # Treat a declared soy allergy as a group exclusion; tofu-only avoidance does not automatically imply soy allergy.
    soy_allergy = any(term in {"soy", "soya", "soybean", "soybeans"} or "soy allergy" in term or "soya allergy" in term for term in terms)
    return terms, soy_allergy

def _food_is_excluded(food, profile):
    terms, soy_allergy = _allergy_terms(profile)
    name = food.lower()
    aliases = {
        "tofu": ["tofu"], "soy": ["soy", "soya", "soybean", "soybeans", "nutrela", "soy chunks", "soy protein", "soy milk"],
        "dairy": ["milk", "curd", "paneer", "whey", "yogurt", "yoghurt"],
        "milk": ["milk", "curd", "paneer", "whey", "yogurt", "yoghurt"],
        "lactose": ["milk", "curd", "paneer", "whey", "yogurt", "yoghurt"],
        "peanut": ["peanut"], "peanuts": ["peanut"], "gluten": ["roti", "wheat", "oats"],
        "egg": ["egg"], "eggs": ["egg"], "almond": ["almond"], "almonds": ["almond"],
    }
    if soy_allergy and any(x in name for x in aliases["soy"]):
        return True
    if profile.get("diet_preference") == "Vegan" and any(x in name for x in ["milk", "curd", "paneer", "whey", "egg", "chicken"]):
        return True
    for term in terms:
        normalized = term.replace(" allergy", "").strip()
        if normalized in aliases and any(alias in name for alias in aliases[normalized]):
            return True
        if normalized and normalized in name:
            return True
    return False

def _choose_safe_food(candidates, profile):
    for food, amount, unit in candidates:
        if food in FOOD_NUTRIENTS and not _food_is_excluded(food, profile):
            return (food, amount, unit)
    return None

def build_detailed_meals(profile):
    """Build meals from allowed foods only; all listed amounts are approximate edible portions."""
    pref = profile["diet_preference"]
    supplement = profile.get("supplement_preference", "No supplement")
    if pref == "Vegan":
        base = [
            ("Breakfast", [("Oats (dry)",60,"g"),("Fortified soy milk",250,"ml"),("Banana",100,"g"),("Chia seeds",10,"g")]),
            ("Lunch", [("Cooked rice",180,"g"),("Dal (cooked)",180,"g"),("Soy chunks (dry, Nutrela-style)",30,"g"),("Mixed vegetables (cooked)",150,"g")]),
            ("Snack", [("Apple",150,"g"),("Roasted chana",35,"g"),("Almonds",10,"g")]),
            ("Dinner", [("Whole-wheat roti (cooked)",120,"g"),("Soy chunks (dry, Nutrela-style)",30,"g"),("Dal (cooked)",100,"g"),("Mixed vegetables (cooked)",200,"g")]),
        ]
    elif pref == "Vegetarian":
        base = [
            ("Breakfast", [("Oats (dry)",60,"g"),("Milk",250,"ml"),("Banana",100,"g"),("Chia seeds",10,"g")]),
            ("Lunch", [("Cooked rice",180,"g"),("Dal (cooked)",180,"g"),("Paneer",80,"g"),("Mixed vegetables (cooked)",150,"g")]),
            ("Snack", [("Curd (plain)",200,"g"),("Apple",150,"g"),("Roasted chana",25,"g")]),
            ("Dinner", [("Whole-wheat roti (cooked)",120,"g"),("Paneer",80,"g"),("Dal (cooked)",100,"g"),("Mixed vegetables (cooked)",150,"g")]),
        ]
    else:
        base = [
            ("Breakfast", [("Oats (dry)",60,"g"),("Milk",250,"ml"),("Banana",100,"g"),("Egg (whole)",100,"g")]),
            ("Lunch", [("Cooked rice",180,"g"),("Chicken breast (cooked)",130,"g"),("Dal (cooked)",100,"g"),("Mixed vegetables (cooked)",150,"g")]),
            ("Snack", [("Curd (plain)",200,"g"),("Apple",150,"g"),("Almonds",10,"g")]),
            ("Dinner", [("Whole-wheat roti (cooked)",120,"g"),("Chicken breast (cooked)",100,"g"),("Mixed vegetables (cooked)",200,"g")]),
        ]

    # Filter every candidate. If a preferred protein is excluded, substitute a safe food; never silently keep an allergen.
    fallback_proteins = {
        "Vegan": [("Dal (cooked)",150,"g"),("Roasted chana",40,"g"),("Cooked rice",150,"g")],
        "Vegetarian": [("Dal (cooked)",150,"g"),("Roasted chana",40,"g"),("Egg (whole)",100,"g")],
        "Non-vegetarian": [("Dal (cooked)",150,"g"),("Roasted chana",40,"g"),("Chicken breast (cooked)",100,"g"),("Egg (whole)",100,"g")],
    }
    safe_meals=[]
    for meal_name, items in base:
        safe=[]
        for item in items:
            if not _food_is_excluded(item[0], profile):
                safe.append(item)
            else:
                # Replace a removed protein with the first suitable, non-excluded alternative.
                if any(token in item[0].lower() for token in ["tofu", "soy", "nutrela", "paneer", "chicken", "egg", "whey"]):
                    replacement = _choose_safe_food(fallback_proteins[pref], profile)
                    if replacement and replacement[0] not in [x[0] for x in safe]:
                        safe.append(replacement)
        safe_meals.append((meal_name, safe))

    if supplement != "No supplement":
        supplement_food = {
            "Whey protein": ("Whey protein powder",25,"g"),
            "Plant-based pea-rice protein": ("Pea-rice protein powder",25,"g"),
            "Soy protein": ("Soy protein powder",25,"g"),
        }.get(supplement)
        if supplement_food and not _food_is_excluded(supplement_food[0], profile):
            for i, (meal_name, items) in enumerate(safe_meals):
                if meal_name == "Snack":
                    items.append(supplement_food)
                    break

    estimate = nutrition_estimate(profile) if int(profile["age"]) >= 18 else None
    scale = max(0.8, min(1.25, estimate["calories"] / 2200)) if estimate else 1.0
    detailed=[]
    for meal_name, items in safe_meals:
        rows=[]
        for food, amount, unit in items:
            if food not in FOOD_NUTRIENTS or _food_is_excluded(food, profile):
                continue
            amount = round(amount * scale / 5) * 5
            factor = amount / 100
            n=FOOD_NUTRIENTS[food]
            row={"Food":food,"Amount":f"{amount} {unit}"}
            row.update({k:round(n[k]*factor,1) for k in ["kcal","protein","carbs","fat"]})
            row.update({k:round(n[k]*factor,1) for k in MICRO_LABELS})
            rows.append(row)
        detailed.append((meal_name, rows))
    return detailed

def make_meal_ideas(profile):
    preference = profile["diet_preference"]
    if preference == "Vegetarian":
        protein_foods = "dal, rajma/chole, paneer/curd if tolerated, roasted chana, and other suitable legumes"
    elif preference == "Vegan":
        protein_foods = "dal, rajma/chole, roasted chana, beans, and soy chunks (Nutrela) only if soy is tolerated"
    else:
        protein_foods = "eggs, chicken/fish if eaten, dal, beans, curd, and other tolerated protein foods"
    allergies = str(profile.get("allergies", "") or "").strip()
    allergy_note = f"Allergy/avoid list applied: {allergies}. Always verify packaged-food labels and cross-contamination warnings." if allergies else "No allergies entered; still check food labels and personal tolerance."
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
    .stApp { background: radial-gradient(ellipse at top left, #14213d 0%, #0b1020 46%, #080d19 100%); color: #eef2ff; }
    [data-testid="stSidebar"] { background: #0d1527; border-right: 1px solid rgba(148,163,184,.15); }
    .hero {
        padding: 1.65rem 1.8rem; border-radius: 22px;
        background: linear-gradient(120deg, rgba(20,184,166,.18), rgba(30,41,75,.92) 48%, rgba(15,23,42,.96));
        border: 1px solid rgba(94,234,212,.22); margin-bottom: 1.1rem;
        box-shadow: 0 14px 40px rgba(0,0,0,.18);
    }
    .hero h1 { margin: 0; font-size: 2.35rem; letter-spacing: -.04em; }
    .hero p { color: #cbd5e1; margin: .4rem 0 0 0; }
    div[data-testid="stMetric"] { background: rgba(18,26,46,.9); padding: 1rem; border-radius: 16px; border: 1px solid rgba(148,163,184,.16); }
    div[data-testid="stRadio"] > div[role="radiogroup"] { gap: .55rem; flex-wrap: wrap; align-items: stretch; }
    div[data-testid="stRadio"] > div[role="radiogroup"] label {
        background: rgba(20,30,49,.86); border: 1px solid rgba(148,163,184,.20);
        border-radius: 12px; padding: .66rem 1rem; transition: all .18s ease;
        min-height: 44px; justify-content: center; box-shadow: 0 4px 14px rgba(0,0,0,.10); margin-bottom: .25rem;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label > div:first-child { display: none !important; }
    div[data-testid="stRadio"] > div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(120deg, #0f766e, #115e59); border-color: rgba(94,234,212,.8);
        box-shadow: 0 5px 18px rgba(20,184,166,.16); color: #ffffff;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label p { font-weight: 650; margin: 0; }
    .muscle-card { background: linear-gradient(145deg, rgba(22,34,55,.98), rgba(12,19,34,.98)); border: 1px solid rgba(94,234,212,.22); border-radius: 20px; padding: 1.15rem; min-height: 100%; box-shadow: 0 16px 36px rgba(0,0,0,.18); }
    .muscle-card h3 { margin: .1rem 0 .45rem 0; font-size: 1.18rem; letter-spacing: -.02em; }
    .muscle-sub { color: #9ca3af; font-size: .88rem; margin-bottom: .55rem; }
    .muscle-card svg { width: 100%; max-height: 410px !important; }
    div[data-testid="stButton"] button[kind="secondary"] { background: rgba(18,29,48,.92); border-color: rgba(148,163,184,.25); color: #e2e8f0; }
    div[data-testid="stButton"] button[kind="primary"] { background: linear-gradient(120deg,#0f766e,#0d9488); border-color: #5eead4; color: #fff; }
    .section-kicker { text-transform: uppercase; letter-spacing: .12em; color: #5eead4; font-size: .74rem; font-weight: 800; }
    .demo-frame { background: #101827; border: 1px solid rgba(148,163,184,.18); border-radius: 16px; padding: 10px; }
    div.stButton > button, div.stFormSubmitButton > button, a[data-testid="stLinkButton"] {
        border-radius: 999px !important; border: 1px solid rgba(94,234,212,.35); font-weight: 650;
        min-height: 42px; padding-left: 16px; padding-right: 16px;
        transition: transform .15s ease, border-color .15s ease, background .15s ease;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover { transform: translateY(-1px); border-color: #5eead4; }
    [data-testid="stTabs"] button[role="tab"] { border-radius: 10px 10px 0 0; }
    .small-muted { color: #9ca3af; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------- SIDEBAR -----------------------------

with st.sidebar:
    st.markdown("# FITNEXORA")
    st.caption("Your personal fitness companion · Studio UI v2")
    st.divider()

    username = st.session_state["authenticated_user"]
    st.caption(f"Logged in as **{username}**")
    if st.button("Log out", width="stretch"):
        st.session_state["authenticated_user"] = None
        st.rerun()

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

# Professional pill-tab navigation. Real buttons replace the old radio controls,
# so no circular radio dots are rendered anywhere in the main navigation.
page_options = [
    "Dashboard", "Workout Planner", "Exercise Library", "Muscle Studio", "Nutrition Plan",
    "Nutrition Tracker", "AI Posture Coach", "Progress", "App Info",
]
if "active_page" not in st.session_state or st.session_state["active_page"] not in page_options:
    st.session_state["active_page"] = "Dashboard"
nav_rows = [page_options[:5], page_options[5:]]
for row_index, nav_row in enumerate(nav_rows):
    nav_cols = st.columns(len(nav_row), gap="small")
    for nav_col, nav_label in zip(nav_cols, nav_row):
        with nav_col:
            active = st.session_state["active_page"] == nav_label
            if st.button(
                nav_label,
                key=f"pill_nav_{nav_label.lower().replace(' ', '_')}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ) and not active:
                st.session_state["active_page"] = nav_label
                st.rerun()
page = st.session_state["active_page"]
st.markdown("<div style='height:1px;background:linear-gradient(90deg,rgba(45,212,191,.65),rgba(148,163,184,.08));margin:.35rem 0 1.2rem 0'></div>", unsafe_allow_html=True)

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


# ----------------------------- EXERCISE LIBRARY -----------------------------

elif page == "Exercise Library":
    import re
    import difflib
    import requests

    st.markdown("## 🎬 Exercise Library")
    st.write("Explore an exercise by muscle group. Every selection includes a form guide, common mistakes, equipment notes and a demonstration fallback.")
    st.info("Use a manageable load and controlled movement. Stop if you feel pain, dizziness or unusual symptoms. Video demonstrations are educational, not medical advice.")

    exercise_guides = {
        "Lat Pulldown": ("Back / lats", "Sit with thighs secured, grip the bar a little wider than shoulder width, pull toward the upper chest while driving elbows down, then return slowly.", "Avoid swinging, pulling behind the neck, or turning it into a heavy lean-back row.", "Gym cable machine", "Back"),
        "Seated Cable Row": ("Back", "Sit tall, brace your trunk, pull the handle toward the lower ribs, and return with control.", "Avoid jerking the torso or rounding the lower back.", "Cable row machine", "Back"),
        "Chest-Supported Row": ("Back", "Keep your chest against the pad, pull elbows toward hips, pause briefly, and lower with control.", "Avoid shrugging or lifting your chest away from the pad.", "Supported row machine or incline bench", "Back"),
        "Pull-up": ("Back / biceps", "Start from a controlled hang, pull upward by driving elbows down, and lower under control.", "Avoid swinging; use assistance if needed.", "Pull-up bar", "Back"),
        "Assisted Pull-up": ("Back / biceps", "Set assistance appropriately, brace your trunk, pull smoothly, and lower slowly.", "Avoid bouncing off the platform.", "Assisted pull-up machine", "Back"),
        "Bench Press": ("Chest / triceps", "Keep feet planted and shoulder blades comfortably set; lower the bar under control and press without bouncing.", "Use safety supports or a spotter for challenging loads.", "Bench and barbell", "Chest"),
        "Flat Dumbbell Press": ("Chest / triceps", "Keep wrists stacked over elbows, lower dumbbells under control, and press smoothly.", "Avoid dropping the weights too deep for your shoulder comfort.", "Bench and dumbbells", "Chest"),
        "Incline Dumbbell Press": ("Upper chest / triceps", "Set a modest bench incline, keep feet stable, lower dumbbells beside the upper chest, and press smoothly.", "Avoid excessive arching or an extremely steep bench angle.", "Incline bench and dumbbells", "Chest"),
        "Chest Fly Machine": ("Chest", "Set handles around mid-chest, keep a soft elbow bend, bring arms together slowly, and return with control.", "Avoid overstretching the shoulders.", "Pec-deck machine", "Chest"),
        "Seated Cable Fly": ("Chest", "Stand stable, keep a soft elbow bend, bring handles together in a controlled arc, and return slowly.", "Avoid momentum or overstretching.", "Cable machine", "Chest"),
        "Dumbbell Shoulder Press": ("Shoulders / triceps", "Brace your core, press from shoulder level in a comfortable path, and lower slowly.", "Avoid over-arching your lower back.", "Dumbbells", "Shoulders"),
        "Dumbbell Lateral Raise": ("Side shoulders", "Use light weights, raise arms out to the sides to around shoulder height, and lower slowly.", "Avoid swinging or shrugging heavily.", "Dumbbells", "Shoulders"),
        "Cable Face Pull": ("Rear shoulders / upper back", "Set the rope around face height, pull toward the face with elbows out, and control the return.", "Avoid leaning back to move the weight.", "Cable machine with rope", "Shoulders"),
        "Reverse Pec Deck": ("Rear shoulders", "Face the pad, hold handles with soft elbows, move arms outward, and return slowly.", "Avoid swinging or shrugging.", "Reverse pec-deck machine", "Shoulders"),
        "Barbell Curl": ("Biceps", "Stand tall, keep elbows near your sides, curl without swinging, and lower slowly.", "Avoid hip momentum.", "Barbell or EZ bar", "Arms"),
        "Dumbbell Curl": ("Biceps", "Keep upper arms steady, curl through a comfortable range, and lower under control.", "Avoid swinging or rushing the lowering phase.", "Dumbbells", "Arms"),
        "Hammer Curl": ("Biceps / forearms", "Keep palms facing each other, elbows near your sides, and curl without moving your torso.", "Avoid swinging or bending the wrists.", "Dumbbells", "Arms"),
        "Cable Triceps Pushdown": ("Triceps", "Keep elbows near your sides, extend the elbows to push the handle down, then return slowly.", "Avoid rocking your torso.", "Cable machine", "Arms"),
        "Squat": ("Quads / glutes", "Set feet comfortably, brace your trunk, sit between your hips, and stand by pushing through the whole foot.", "Avoid forcing depth or letting pain continue.", "Bodyweight or squat rack", "Legs"),
        "Goblet Squat": ("Quads / glutes", "Hold one dumbbell close to your chest, squat under control, and stand smoothly.", "Avoid letting the weight drift away from your chest.", "Dumbbell or kettlebell", "Legs"),
        "Leg Press": ("Quads / glutes", "Set feet comfortably, lower only as far as your pelvis stays supported, and press without snapping knees straight.", "Do not let the pelvis curl off the pad or forcefully lock knees.", "Leg press machine", "Legs"),
        "Leg Extension": ("Quads", "Align the machine pivot with your knee, extend smoothly, pause briefly, and lower slowly.", "Avoid swinging or forcing a painful range.", "Leg extension machine", "Legs"),
        "Seated Leg Curl": ("Hamstrings", "Align the machine pivot with your knee, curl smoothly, and return slowly.", "Avoid lifting your hips or using momentum.", "Seated leg curl machine", "Legs"),
        "Romanian Deadlift": ("Hamstrings / glutes", "Keep a soft knee bend, push hips backward, keep the weight close to your legs, and stand smoothly.", "Avoid rounding your back or lowering beyond your mobility.", "Dumbbells or barbell", "Legs"),
        "Hip Thrust": ("Glutes", "Rest upper back on a stable bench, drive through your feet, and finish with hips extended without over-arching.", "Avoid hyperextending the lower back.", "Bench and padded weight", "Legs"),
        "Reverse Lunge": ("Glutes / legs", "Step one foot back, lower under control, keep the front foot planted, and return to standing.", "Avoid losing balance or forcing depth that causes pain.", "Bodyweight or dumbbells", "Legs"),
        "Standing Calf Raise": ("Calves", "Rise onto the balls of your feet, pause, and lower slowly through a comfortable range.", "Avoid bouncing.", "Calf raise machine or stable step", "Legs"),
        "Push-up": ("Chest / shoulders / triceps", "Place hands just wider than shoulders, keep head-to-heel alignment, lower chest between hands, then press up while maintaining a firm trunk.", "Avoid sagging hips, flaring elbows excessively, or shortening the range to count reps.", "Floor; incline option", "Bodyweight"),
        "Plank": ("Core", "Place elbows under shoulders, keep a straight line from head to heels, brace your abdomen, and breathe steadily.", "Avoid dropping hips or holding your breath.", "Mat", "Bodyweight"),
        "Dead Bug": ("Core", "Lie on your back with arms up and knees bent; extend opposite arm and leg slowly while keeping your trunk controlled.", "Avoid letting your lower back arch away from the floor.", "Mat", "Bodyweight"),
    }

    def build_fallback_guide(exercise_name):
        """Create movement-specific cues for exercises without a hand-written entry."""
        n = exercise_name.lower()
        if any(k in n for k in ("squat", "split squat", "hack squat")):
            return ("Quads / glutes", "Set feet in a stable stance, brace your abdomen, bend hips and knees together, keep knees tracking in the direction of your toes, then stand by pushing through the whole foot.", "Avoid heels lifting, knees collapsing inward, bouncing at the bottom or forcing depth that causes pain.", "Bodyweight or the listed resistance", "Legs")
        if any(k in n for k in ("lunge", "step-up")):
            return ("Legs / glutes", "Stand tall and brace your trunk. Step into a stable stance, lower under control while keeping the front foot planted, then push through that foot to return. For step-ups, place the whole foot on a stable platform.", "Avoid wobbling, pushing off excessively with the trailing leg, or letting the front knee collapse inward.", "Bodyweight or dumbbells; stable step if needed", "Legs")
        if any(k in n for k in ("deadlift", "romanian deadlift", "good morning")):
            return ("Hamstrings / glutes / back", "Keep a soft knee bend, push your hips backward, keep the load close to your legs and your spine neutral, then drive hips forward to stand tall.", "Avoid rounding the back, turning it into a squat, drifting the load away from your legs or lowering beyond comfortable mobility.", "Dumbbells, barbell or suitable backpack", "Legs")
        if any(k in n for k in ("row", "pulldown", "pull-up", "pullup")):
            return ("Back / biceps", "Brace your trunk and keep shoulders controlled. Pull by driving elbows toward your sides, pause briefly without shrugging, then return slowly to the start.", "Avoid jerking, swinging, shrugging toward the ears or leaning back to move the load.", "Use the equipment named in the exercise", "Back")
        if any(k in n for k in ("press", "push-up", "pushup", "dip")):
            return ("Chest / shoulders / triceps", "Set a stable stance and brace your trunk. Keep wrists aligned with forearms, lower under control through a comfortable range, then press smoothly without bouncing.", "Avoid flared elbows, sagging hips during push-ups, over-arching the back or forcing a painful range. Use a spotter for challenging barbell presses.", "Use the equipment named in the exercise", "Chest")
        if any(k in n for k in ("fly", "snow angel", "y-t raise", "rear delt")):
            return ("Chest / shoulders / upper back", "Keep a slight bend in your elbows, move through a controlled arc, keep shoulders away from your ears and return slowly to the start.", "Avoid swinging, shrugging, locking the elbows or stretching the shoulders into discomfort.", "Use the equipment named in the exercise", "Shoulders")
        if any(k in n for k in ("curl",)):
            return ("Biceps / forearms", "Keep your upper arms close to your sides, wrists neutral and torso still. Curl smoothly, squeeze briefly, then lower slowly.", "Avoid swinging your hips, shrugging or bending the wrists to finish a rep.", "Dumbbells, barbell or backpack as appropriate", "Arms")
        if any(k in n for k in ("triceps", "kickback", "extension")):
            return ("Triceps", "Stabilize your upper arms and trunk. Move mainly at the elbow through a comfortable range, then return slowly without letting the shoulders take over.", "Avoid flaring the elbows excessively, arching the back or using momentum.", "Use the equipment named in the exercise", "Arms")
        if any(k in n for k in ("raise", "shoulder", "arnold")):
            return ("Shoulders", "Brace your abdomen, keep the neck relaxed and raise or press in a smooth path that feels comfortable for your shoulders. Lower under control.", "Avoid swinging, shrugging heavily or over-arching the lower back.", "Dumbbells or the listed equipment", "Shoulders")
        if any(k in n for k in ("bridge", "hip thrust")):
            return ("Glutes / hamstrings", "Keep feet planted, brace your abdomen and drive through your feet to lift your hips. Finish with hips extended while keeping ribs down, then lower slowly.", "Avoid pushing through the lower back, flaring ribs or letting knees collapse inward.", "Mat; stable bench or load if specified", "Legs")
        if any(k in n for k in ("plank", "dead bug", "bird dog", "prone")):
            return ("Core / trunk stability", "Keep your ribs and pelvis controlled, brace gently, breathe throughout and move slowly while maintaining a stable trunk.", "Avoid holding your breath, letting the lower back sag or arch, or rushing repetitions.", "Mat", "Bodyweight")
        if "calf" in n:
            return ("Calves", "Stand securely, rise through the balls of your feet, pause briefly at the top and lower slowly through a comfortable range.", "Avoid bouncing or letting ankles roll outward.", "Bodyweight or calf-raise equipment", "Legs")
        return ("Movement-specific muscles", "Start with a stable setup, brace your trunk, move through a comfortable range and control both the lifting and lowering phases. Keep breathing and make each repetition deliberate.", "Avoid momentum, painful range of motion, loss of balance or increasing the load before technique is consistent.", "Depends on the exercise", "Other")

    all_planned_exercises = set()
    for equipment_plans in EXERCISES.values():
        for workout_items in equipment_plans.values():
            for item in workout_items:
                all_planned_exercises.add(item[0])
    for name in sorted(all_planned_exercises):
        if name not in exercise_guides:
            exercise_guides[name] = build_fallback_guide(name)

    category_order = ["Back", "Chest", "Shoulders", "Arms", "Legs", "Bodyweight", "Other"]
    category_names = [cat for cat in category_order if any(v[4] == cat for v in exercise_guides.values())]
    category_tabs = st.tabs(category_names)

    @st.cache_data(ttl=3600, show_spinner=False)
    def load_video_exercise_database():
        """Load video metadata from the public API, with a static GitHub fallback.

        The public demo API can rate-limit requests. The raw dataset fallback avoids
        making the Exercise Library depend on that demo endpoint being available.
        """
        headers = {"User-Agent": "FITNEXORA/1.0 exercise-library"}
        sources = [
            "https://exercise-database.zenithfits.com/api/v1/exercises?limit=500",
            "https://raw.githubusercontent.com/amiinwani/free-exercise-db-with-videos/main/data/exercises.json",
            # Broad GIF catalogue used when a specific movement is absent from the MP4 catalogue.
            "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/data/exercises.json",
        ]
        errors = []
        combined_rows = []
        seen = set()
        for source in sources:
            try:
                response = requests.get(source, timeout=18, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    rows = payload.get("data", payload.get("exercises", []))
                else:
                    rows = payload
                if isinstance(rows, list) and rows:
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        # Keep entries from each source; deduplicate by normalized name + media URL.
                        media = row.get("gif_url") or row.get("video_url") or row.get("videoUrl")
                        videos = row.get("videos", {})
                        if isinstance(videos, dict):
                            media = media or videos.get("male") or videos.get("female")
                        key = (str(row.get("name", "")).strip().lower(), str(media or ""))
                        if key not in seen:
                            seen.add(key)
                            combined_rows.append(row)
                else:
                    errors.append(f"{source}: response contained no exercise rows")
            except Exception as exc:
                errors.append(f"{source}: {exc}")
        if combined_rows:
            return combined_rows
        raise RuntimeError(" | ".join(errors))

    def normalize_exercise_name(value):
        value = value.lower().replace("&", " and ")
        value = re.sub(r"[^a-z0-9]+", " ", value)
        replacements = {"dumbbell": "", "barbell": "", "machine": "", "cable": "", "flat": "", "standing": "", "seated": "", "exercise": ""}
        words = [replacements.get(word, word) for word in value.split()]
        return " ".join(word for word in words if word).strip()

    with st.spinner("Loading exercise video catalogue..."):
        try:
            video_catalogue = load_video_exercise_database()
            video_catalogue_error = None
        except Exception as exc:
            video_catalogue = []
            video_catalogue_error = str(exc)

    if not video_catalogue:
        # Python-side requests may be blocked even when the browser can reach GitHub.
        # The selected exercise panel below also tries a browser-side animation fallback.
        st.caption("Connecting to the exercise animation library… trying an in-browser fallback if the server catalogue is unavailable.")

    for tab, category in zip(category_tabs, category_names):
        with tab:
            category_exercises = sorted(name for name, details in exercise_guides.items() if details[4] == category)
            if not category_exercises:
                st.caption("No exercises in this category yet.")
                continue
            chosen_exercise = st.selectbox(
                f"Choose a {category.lower()} exercise", category_exercises,
                key=f"exercise_library_{category.lower().replace(' ', '_')}"
            )
            muscle_group, instructions, mistakes, equipment_needed, _ = exercise_guides[chosen_exercise]
            st.markdown(f"### {chosen_exercise}")
            st.caption("Selected movement · review the setup before starting your set")
            left, right = st.columns([1, 1.05], gap="large")
            with left:
                st.markdown(f"**Main muscles:** {muscle_group}")
                st.markdown(f"**Equipment:** {equipment_needed}")
                st.markdown("**How to perform it**")
                st.write(instructions)
                st.markdown("**Common mistakes to avoid**")
                st.write(mistakes)
                st.markdown("**Quick technique checklist**")
                st.write("1. Set up safely and adjust the equipment.\n2. Use a comfortable, controlled range.\n3. Keep breathing; don't rush reps.\n4. Stop if you feel pain, dizziness, or unusual symptoms.")
            with right:
                st.markdown("**YouTube video demonstration**")
                st.caption(f"Video search is tailored to: {chosen_exercise}")
                show_youtube_fallback(chosen_exercise, height=560)


# ----------------------------- PERSONALIZED NUTRITION PLAN -----------------------------

elif page == "Muscle Studio":
    import json
    import re
    import difflib
    import requests
    import streamlit.components.v1 as components

    st.markdown("""
    <div class="hero">
      <h1>Muscle Studio</h1>
      <p>Choose one or more muscles on the front and back body map. Select Next to build a focused exercise list with sets, reps, technique cues and an inline movement demo.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin:.3rem 0 1.2rem 0">
      <span style="padding:7px 12px;border-radius:999px;background:#123b3b;border:1px solid #2dd4bf;color:#99f6e4;font-size:13px">01 · Select muscles</span>
      <span style="padding:7px 12px;border-radius:999px;background:#172338;border:1px solid #334155;color:#cbd5e1;font-size:13px">02 · Choose exercises</span>
      <span style="padding:7px 12px;border-radius:999px;background:#172338;border:1px solid #334155;color:#cbd5e1;font-size:13px">03 · Learn the movement</span>
    </div>
    """, unsafe_allow_html=True)

    # Muscle choices are grouped by visible front/back anatomy. Multiple selections are supported.
    front_muscles = ["Chest", "Front shoulders", "Biceps", "Forearms", "Abs / core", "Quadriceps", "Calves"]
    back_muscles = ["Traps", "Lats / upper back", "Rear shoulders", "Triceps", "Lower back", "Glutes", "Hamstrings", "Calves"]
    muscle_descriptions = {
        "Chest": "Pectorals · pushing movements", "Front shoulders": "Anterior deltoids · overhead pressing",
        "Biceps": "Elbow flexors · pulling and curls", "Forearms": "Grip and wrist control",
        "Abs / core": "Trunk stability and abdominal control", "Quadriceps": "Front thigh · knee extension",
        "Calves": "Lower leg · ankle plantar flexion", "Lats / upper back": "Back width and rowing strength",
        "Rear shoulders": "Posterior deltoids · upper-back control", "Traps": "Upper back · shoulder elevation and scapular control", "Triceps": "Back of upper arm · elbow extension",
        "Lower back": "Spinal erectors · trunk endurance", "Glutes": "Hip extension and stability",
        "Hamstrings": "Back thigh · hip extension and knee flexion",
    }

    # Real clickable anatomy component. Sync the current template and anatomy art so an older
    # muscle_map_component folder is upgraded instead of silently keeping the old stick figure.
    import shutil
    project_dir = Path(__file__).resolve().parent
    component_dir = project_dir / "muscle_map_component"
    component_dir.mkdir(parents=True, exist_ok=True)
    component_index = component_dir / "index.html"
    component_template = project_dir / "muscle_map_component_template.html"
    anatomy_source = project_dir / "assets" / "muscle_anatomy.png"
    current_component = component_index.read_text(encoding="utf-8") if component_index.exists() else ""
    template_text = component_template.read_text(encoding="utf-8") if component_template.exists() else ""
    # Upgrade stale local component files by comparing the complete HTML, not a marker alone.
    if component_template.exists() and current_component != template_text:
        shutil.copy2(component_template, component_index)
    if anatomy_source.exists():
        anatomy_target = component_dir / "anatomy.png"
        source_hash = __import__("hashlib").sha256(anatomy_source.read_bytes()).hexdigest()
        target_hash = __import__("hashlib").sha256(anatomy_target.read_bytes()).hexdigest() if anatomy_target.exists() else None
        if target_hash != source_hash:
            shutil.copy2(anatomy_source, anatomy_target)
    if not component_index.exists():
        st.error("The interactive body map template is missing. Extract the complete FITNEXORA update ZIP, including muscle_map_component_template.html and assets/muscle_anatomy.png.")
        st.stop()
    # Bump component identity so Streamlit/browser cannot keep showing the old stick-figure iframe.
    body_map_component = components.declare_component(
        "fitnexora_interactive_muscle_map_v6_exact_user_art",
        path=str(component_dir),
    )
    if "muscle_targets_selected" not in st.session_state:
        st.session_state["muscle_targets_selected"] = []
    map_value = body_map_component(
        selected=st.session_state["muscle_targets_selected"],
        key="fitnexora_interactive_body_map",
        default=None,
    )
    if isinstance(map_value, list):
        valid_muscles = {
            "Chest", "Front shoulders", "Biceps", "Forearms", "Abs / core",
            "Quadriceps", "Calves", "Lats / upper back", "Rear shoulders", "Traps",
            "Triceps", "Lower back", "Glutes", "Hamstrings",
        }
        cleaned = list(dict.fromkeys(m for m in map_value if m in valid_muscles))
        if cleaned != st.session_state["muscle_targets_selected"]:
            st.session_state["muscle_targets_selected"] = cleaned

    selected_muscles = list(dict.fromkeys(st.session_state.get("muscle_targets_selected", [])))
    if selected_muscles:
        st.markdown(
            "<div style='background:rgba(15,118,110,.16);border:1px solid rgba(94,234,212,.35);"
            "border-radius:14px;padding:12px 16px;margin:.7rem 0'>"
            "<div style='color:#5eead4;font-size:.75rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase'>"
            f"Selected targets · {len(selected_muscles)}</div><div style='color:#f1f5f9;font-weight:650;margin-top:5px'>"
            + "  ·  ".join(selected_muscles) + "</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Click the actual muscle regions on the front/back body map. You can select several areas.")

    clear_col, next_col = st.columns([1, 2], gap="medium")
    with clear_col:
        if st.button("Clear selected muscles", key="muscle_studio_clear", use_container_width=True):
            st.session_state["muscle_targets_selected"] = []
            st.session_state["muscle_studio_show_results"] = False
            st.rerun()
    with next_col:
        if st.button("Next · Show matching exercises", type="primary", use_container_width=True, key="muscle_studio_next"):
            if not selected_muscles:
                st.warning("Click at least one muscle region on the body map first.")
            else:
                st.session_state["muscle_studio_targets"] = selected_muscles
                st.session_state["muscle_studio_show_results"] = True

    # Recommendation library: movement name, sets/reps, equipment, instructions, common mistakes, target groups.
    movement_bank = [
      {"name":"Incline Dumbbell Press","targets":["Chest","Front shoulders"],"sets":"3 sets × 8–12 reps","equipment":"Incline bench + dumbbells","how":"Set the bench to a modest incline. Plant your feet, draw shoulder blades gently back, lower the dumbbells beside the upper chest, then press up smoothly.","mistakes":"Avoid bouncing, flaring elbows straight out, or arching your lower back excessively."},
      {"name":"Push-up","targets":["Chest","Front shoulders","Triceps","Abs / core"],"sets":"3 sets × 6–12 reps","equipment":"Floor or elevated bench","how":"Place hands just wider than shoulders. Brace your abdomen and keep head, hips and heels aligned. Lower chest under control, then press away.","mistakes":"Avoid sagging hips, flared elbows, half reps or holding your breath."},
      {"name":"Dumbbell Shoulder Press","targets":["Front shoulders","Triceps"],"sets":"3 sets × 8–12 reps","equipment":"Dumbbells + bench (optional)","how":"Start with weights around shoulder height. Brace your trunk, press overhead without forcing the range, then lower slowly.","mistakes":"Avoid over-arching your back, shrugging hard or locking out painfully."},
      {"name":"Dumbbell Curl","targets":["Biceps","Forearms"],"sets":"3 sets × 10–15 reps","equipment":"Dumbbells","how":"Keep upper arms close to your sides, wrists neutral and torso still. Curl smoothly, then lower for about two seconds.","mistakes":"Avoid swinging the hips, lifting elbows forward or bending the wrists."},
      {"name":"Hammer Curl","targets":["Biceps","Forearms"],"sets":"2–3 sets × 10–15 reps","equipment":"Dumbbells","how":"Hold dumbbells with palms facing each other. Keep elbows near your ribs and curl without rotating the wrists.","mistakes":"Avoid swinging or letting shoulders take over."},
      {"name":"Plank","targets":["Abs / core","Lower back"],"sets":"3 sets × 20–45 sec","equipment":"Mat","how":"Place elbows under shoulders, extend legs and keep a straight line from head to heels. Brace gently and breathe steadily.","mistakes":"Avoid dropping hips, lifting hips too high or holding your breath."},
      {"name":"Dead Bug","targets":["Abs / core","Lower back"],"sets":"3 sets × 8–12 per side","equipment":"Mat","how":"Lie on your back with arms up and knees bent. Slowly extend opposite arm and leg while keeping your lower back gently anchored.","mistakes":"Avoid arching your back or rushing the movement."},
      {"name":"Leg Extension","targets":["Quadriceps"],"sets":"3 sets × 10–15 reps","equipment":"Leg-extension machine","how":"Align the machine pivot with your knee. Extend smoothly, pause briefly at the top, then lower under control.","mistakes":"Avoid swinging the weight or forcing a painful knee range."},
      {"name":"Goblet Squat","targets":["Quadriceps","Glutes"],"sets":"3 sets × 8–12 reps","equipment":"Dumbbell or kettlebell","how":"Hold the weight close to your chest. Brace your trunk, sit between your hips with knees tracking over toes, then stand through the whole foot.","mistakes":"Avoid heels lifting, knees collapsing inward or forcing depth."},
      {"name":"Standing Calf Raise","targets":["Calves"],"sets":"3 sets × 12–20 reps","equipment":"Stable floor or step","how":"Hold a stable support, rise onto the balls of your feet, pause at the top and lower slowly through a comfortable range.","mistakes":"Avoid bouncing or letting ankles roll outward."},
      {"name":"Lat Pulldown","targets":["Lats / upper back","Biceps"],"sets":"3 sets × 8–12 reps","equipment":"Cable lat-pulldown machine","how":"Secure your thighs, keep chest tall and pull the bar toward your upper chest by driving elbows down. Return slowly.","mistakes":"Avoid swinging, pulling behind the neck or leaning far back."},
      {"name":"Seated Cable Row","targets":["Lats / upper back","Rear shoulders","Biceps"],"sets":"3 sets × 8–12 reps","equipment":"Cable row machine","how":"Sit tall and brace your trunk. Pull the handle toward your lower ribs, pause without shrugging, then extend your arms under control.","mistakes":"Avoid jerking the torso or rounding your lower back."},
      {"name":"Cable Face Pull","targets":["Rear shoulders","Lats / upper back"],"sets":"3 sets × 12–15 reps","equipment":"Cable + rope attachment","how":"Set the rope around face height. Pull toward your face with elbows out, keep shoulders down and return slowly.","mistakes":"Avoid leaning back to move the load or shrugging."},
      {"name":"Triceps Pushdown","targets":["Triceps"],"sets":"3 sets × 10–15 reps","equipment":"Cable machine + handle","how":"Keep elbows close to your sides. Extend your elbows to push down, pause, then return slowly without moving your upper arms much.","mistakes":"Avoid rocking your torso or flaring your elbows."},
      {"name":"Hip Thrust","targets":["Glutes","Hamstrings"],"sets":"3 sets × 8–12 reps","equipment":"Stable bench + optional load","how":"Support your upper back on a stable bench, plant feet and drive through them to lift your hips. Finish with ribs down, then lower slowly.","mistakes":"Avoid over-arching the lower back or letting knees collapse inward."},
      {"name":"Romanian Deadlift","targets":["Hamstrings","Glutes","Lower back"],"sets":"3 sets × 8–12 reps","equipment":"Dumbbells or barbell","how":"Keep a soft knee bend, push hips backward and keep the load close to your legs. Stop when hamstrings stretch while your back stays neutral, then stand tall.","mistakes":"Avoid rounding your back, lowering beyond your mobility or drifting the load forward."},
      {"name":"Reverse Lunge","targets":["Glutes","Quadriceps"],"sets":"3 sets × 8–10 per side","equipment":"Bodyweight or dumbbells","how":"Step one foot back, lower under control with the front foot planted, then push through the front foot to return to standing.","mistakes":"Avoid losing balance or letting the front knee collapse inward."},
      {"name":"Back Extension","targets":["Lower back","Glutes","Hamstrings"],"sets":"2–3 sets × 10–15 reps","equipment":"Back-extension bench (if available)","how":"Keep your spine neutral, hinge at the hips and raise your torso until it aligns with your legs. Move smoothly and stop before overextending.","mistakes":"Avoid hyperextending the spine or swinging."},
      {"name":"Reverse Pec Deck","targets":["Rear shoulders","Lats / upper back"],"sets":"3 sets × 12–15 reps","equipment":"Reverse pec-deck machine","how":"Face the pad, keep elbows softly bent and move arms outward. Pause briefly, then return slowly.","mistakes":"Avoid shrugging or using momentum."},
      {"name":"Dumbbell Shrug","targets":["Traps"],"sets":"3 sets × 12–15 reps","equipment":"Pair of dumbbells","how":"Stand tall with dumbbells by your sides. Keep arms straight, lift shoulders vertically toward your ears, pause briefly, then lower slowly. Keep your neck neutral.","mistakes":"Avoid rolling the shoulders, jerking the weights, or jutting your head forward."},
      {"name":"Barbell Shrug","targets":["Traps"],"sets":"3 sets × 8–12 reps","equipment":"Barbell and plates","how":"Hold the bar in front of your thighs with a stable stance. Elevate your shoulders straight upward, pause at the top, then lower under control without bending your elbows.","mistakes":"Avoid shoulder circles, bouncing, or using excessive weight that shortens the range."},
      {"name":"Farmer’s Carry","targets":["Traps","Forearms","Abs / core"],"sets":"3 rounds × 20–40 metres","equipment":"Heavy dumbbells or kettlebells","how":"Pick up two weights, stand tall with shoulders level and ribs stacked over hips, then walk with short controlled steps while breathing steadily.","mistakes":"Avoid leaning to one side, shrugging unevenly, or taking rushed steps."},
      {"name":"Cable Shrug","targets":["Traps"],"sets":"3 sets × 12–15 reps","equipment":"Low cable + straight bar or handles","how":"Stand tall facing the low cable with arms straight. Elevate your shoulders vertically, pause for a second, then lower slowly while keeping your neck neutral.","mistakes":"Avoid rolling your shoulders, bending your elbows, or using momentum."},
      {"name":"Incline Y Raise","targets":["Traps","Rear shoulders"],"sets":"2–3 sets × 10–15 reps","equipment":"Incline bench + light dumbbells","how":"Lie chest-down on a low incline bench. With thumbs pointing upward, raise your arms diagonally into a Y shape without shrugging hard, then lower slowly. Use very light weights.","mistakes":"Avoid swinging, lifting too heavy, or arching your lower back."},
      {"name":"Rack Pull","targets":["Traps","Lats / upper back","Glutes","Hamstrings"],"sets":"3 sets × 5–8 reps","equipment":"Barbell + rack safety pins","how":"Set the bar just below knee height. Brace your trunk, keep the bar close and stand by driving through your feet and hips. Lower under control. Use only if you can maintain a neutral spine.","mistakes":"Avoid rounding your back, jerking the bar, or loading more than you can control."},
    ]

    if st.session_state.get("muscle_studio_show_results") and st.session_state.get("muscle_studio_targets"):
        targets = st.session_state["muscle_studio_targets"]
        st.markdown("---")
        st.markdown("## Your targeted exercise plan")
        st.caption("Suggested starting volume for general fitness. Adjust load and reps to your experience; stop if you feel sharp pain or dizziness.")
        st.markdown("**Target muscles:** " + " · ".join(targets))
        matches = [item for item in movement_bank if set(item["targets"]).intersection(targets)]
        # Prefer a useful, varied selection while keeping the page manageable.
        selected_exercises = matches if "Traps" in targets else matches[:8]
        if not selected_exercises:
            st.info("No exercises matched those targets yet. Try selecting another muscle group.")
        else:
            try:
                @st.cache_data(ttl=3600, show_spinner=False)
                def load_studio_catalogue():
                    headers = {"User-Agent": "FITNEXORA/1.0 exercise-library"}
                    sources = [
                      "https://exercise-database.zenithfits.com/api/v1/exercises?limit=500",
                      "https://raw.githubusercontent.com/amiinwani/free-exercise-db-with-videos/main/data/exercises.json",
                      "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/data/exercises.json",
                    ]
                    all_rows = []
                    for source in sources:
                        try:
                            response = requests.get(source, timeout=10, headers=headers)
                            response.raise_for_status()
                            payload = response.json()
                            rows = payload.get("data", payload.get("exercises", [])) if isinstance(payload, dict) else payload
                            if isinstance(rows, list):
                                all_rows.extend(row for row in rows if isinstance(row, dict))
                        except Exception:
                            pass
                    return all_rows
                studio_catalogue = load_studio_catalogue()
            except Exception:
                studio_catalogue = []

            for index, exercise in enumerate(selected_exercises):
                with st.container(border=True):
                    st.markdown(f"### {index + 1:02d} · {exercise['name']}")
                    a, b, c = st.columns([1, 1, 1.3], gap="medium")
                    a.markdown(f"**Sets & reps**\\n\\n{exercise['sets']}")
                    b.markdown(f"**Equipment**\\n\\n{exercise['equipment']}")
                    c.markdown("**Target muscles**\\n\\n" + " · ".join(exercise["targets"]))
                    with st.expander("More info · Correct posture & movement demo", expanded=False):
                        st.markdown("#### How to perform it")
                        st.write(exercise["how"])
                        st.markdown("#### Common mistakes to avoid")
                        st.write(exercise["mistakes"])
                        st.markdown("#### YouTube movement demonstration")
                        st.caption(f"Search focused on the exact movement: {exercise['name']}")
                        show_youtube_fallback(exercise["name"], height=560)
        st.caption("Training note: this is a general starting plan, not an individualized medical or rehabilitation prescription.")
        if st.button("Change selected muscles", key="muscle_studio_change"):
            st.session_state["muscle_studio_show_results"] = False
            st.rerun()

elif page == "Nutrition Plan":
    st.markdown("## 🥗 Personalized Nutrition Plan")
    st.write("Enter your profile details to create a practical meal structure. Your profile and plan are stored only under your logged-in username in this local app database.")
    existing = load_profile(username) or {
        "age": 25, "height_cm": 170.0, "weight_kg": 70.0, "sex": "Prefer not to say",
        "activity_level": "Moderately active", "nutrition_goal": "Maintain",
        "diet_preference": "Non-vegetarian", "allergies": "", "supplement_preference": "No supplement",
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
        allergies = st.text_input("Allergies / foods to avoid (comma-separated)", value=existing.get("allergies", ""), placeholder="e.g. tofu, peanuts, dairy, soy allergy")
        if diet_preference == "Vegan":
            supplement_options = ["No supplement", "Plant-based pea-rice protein", "Soy protein"]
        elif diet_preference == "Vegetarian":
            supplement_options = ["No supplement", "Whey protein", "Plant-based pea-rice protein", "Soy protein"]
        else:
            supplement_options = ["No supplement", "Whey protein", "Plant-based pea-rice protein", "Soy protein"]
        saved_supplement = existing.get("supplement_preference", "No supplement")
        if saved_supplement not in supplement_options:
            saved_supplement = "No supplement"
        supplement_preference = st.selectbox("Protein supplement preference", supplement_options, index=supplement_options.index(saved_supplement), help="Supplements are optional. Choose one only if it fits your diet and allergies.")
        profile_submitted = st.form_submit_button("Save profile & build my plan", width="stretch")
    if profile_submitted:
        profile_to_save = {
            "age": age, "height_cm": height_cm, "weight_kg": weight_kg, "sex": sex,
            "activity_level": activity_level, "nutrition_goal": nutrition_goal,
            "diet_preference": diet_preference, "allergies": allergies,
            "supplement_preference": supplement_preference,
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
            st.warning("Because you're under 18, this app won't prescribe calorie or protein targets. Focus on regular balanced meals and enough food for growth and activity; discuss individual needs and supplements with a parent/guardian and a qualified healthcare professional or registered dietitian.")
        else:
            estimate = nutrition_estimate(saved_profile)
            if estimate:
                m1, m2, m3 = st.columns(3)
                m1.metric("Rough daily energy estimate", f"{estimate['calories']:,} kcal")
                m2.metric("Protein guide (1.5 g/kg)", f"{estimate['protein']} g/day")
                m3.metric("Maintenance estimate", f"{estimate['maintenance']:,} kcal")
                st.caption(f"Protein guide uses 1.5 g per kg body weight. Approximate macros: carbohydrates {estimate['carbs']} g, fats {estimate['fat']} g, protein {estimate['protein']} g. These are estimates, not exact requirements; individual needs vary.")
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
        st.caption(f"Supplement preference: {saved_profile.get('supplement_preference', 'No supplement')}. Supplement use is optional; food-first is fine.")
        if saved_profile["diet_preference"] == "Vegan":
            st.info("Vegan plans exclude dairy, eggs and whey. Soy chunks (often sold as Nutrela) can be a useful protein food if soy is tolerated. If you have a confirmed soy allergy, enter 'soy allergy' so soy chunks, soy milk and soy protein are excluded.")
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
        "Use your webcam for experimental, real-time pose landmarks, basic rep counting, "
        "and simple movement cues for squats and push-ups."
    )
    st.info(
        "Camera permission is required. Use a well-lit space and keep your full body in view. "
        "This is an educational aid, not a medical assessment or a substitute for a qualified coach. "
        "Angle estimates can be inaccurate if joints are hidden or the camera angle is unsuitable."
    )

    posture_exercise = st.selectbox(
        "Choose exercise",
        ["Squat", "Push-up"],
        key="posture_exercise_choice",
        help="For best results, position the camera at your side so the shoulder, hip, knee/elbow and ankle/wrist are visible.",
    )
    st.caption(
        "Squat: keep shoulder, hip, knee and ankle visible. Push-up: keep shoulder, elbow, wrist, hip and ankle visible. "
        "Use a side view, place the camera steadily, and stop if you feel pain or dizziness."
    )

    try:
        import cv2 as posture_cv2
        import mediapipe as posture_mp
        from streamlit_webrtc import VideoProcessorBase as PostureVideoProcessorBase
        from streamlit_webrtc import webrtc_streamer

        def make_posture_processor(cv2_module, mp_module, base_class, exercise_name):
            """Create a video processor that keeps rep state for one live stream."""
            class PostureProcessor(base_class):
                def __init__(self):
                    self.pose = mp_module.solutions.pose.Pose(
                        static_image_mode=False,
                        model_complexity=1,
                        smooth_landmarks=True,
                        enable_segmentation=False,
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5,
                    )
                    self.stage = "up"
                    self.reps = 0
                    self.last_feedback = "Move into the camera frame"
                    self.last_angle = None

                @staticmethod
                def angle(a, b, c):
                    import math
                    import numpy as np
                    a = np.array(a, dtype=float)
                    b = np.array(b, dtype=float)
                    c = np.array(c, dtype=float)
                    radians = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
                    degrees = abs(radians * 180.0 / math.pi)
                    return 360.0 - degrees if degrees > 180.0 else degrees

                def recv(self, frame):
                    image = frame.to_ndarray(format="bgr24")
                    height, width = image.shape[:2]
                    rgb = cv2_module.cvtColor(image, cv2_module.COLOR_BGR2RGB)
                    result = self.pose.process(rgb)
                    feedback = "Keep your body visible in the frame"
                    angle = None

                    if result.pose_landmarks:
                        landmarks = result.pose_landmarks.landmark
                        ids = mp_module.solutions.pose.PoseLandmark

                        def point(name):
                            lm = landmarks[getattr(ids, name).value]
                            return (lm.x * width, lm.y * height), lm.visibility

                        mp_module.solutions.drawing_utils.draw_landmarks(
                            image,
                            result.pose_landmarks,
                            mp_module.solutions.pose.POSE_CONNECTIONS,
                        )

                        if exercise_name == "Squat":
                            hip, hv = point("LEFT_HIP")
                            knee, kv = point("LEFT_KNEE")
                            ankle, av = point("LEFT_ANKLE")
                            if min(hv, kv, av) > 0.45:
                                angle = self.angle(hip, knee, ankle)
                                if angle < 100:
                                    self.stage = "down"
                                    feedback = "Good depth detected — drive up with control"
                                elif angle > 160:
                                    if self.stage == "down":
                                        self.reps += 1
                                    self.stage = "up"
                                    feedback = "Stand tall; begin the next rep when ready"
                                else:
                                    feedback = "Move smoothly; keep your knees tracking with your toes"
                            else:
                                feedback = "Turn sideways and keep hip, knee and ankle visible"
                        else:
                            # Select whichever side is most visible; the far arm is often occluded in a side view.
                            side_candidates = []
                            for side in ("LEFT", "RIGHT"):
                                shoulder_pt, sv = point(f"{side}_SHOULDER")
                                elbow_pt, ev = point(f"{side}_ELBOW")
                                wrist_pt, wv = point(f"{side}_WRIST")
                                hip_pt, hv = point(f"{side}_HIP")
                                ankle_pt, av = point(f"{side}_ANKLE")
                                visibility_score = min(sv, ev, wv, hv, av)
                                side_candidates.append((visibility_score, shoulder_pt, elbow_pt, wrist_pt, hip_pt, ankle_pt))
                            visibility_score, shoulder, elbow, wrist, hip, ankle = max(side_candidates, key=lambda item: item[0])
                            if visibility_score > 0.35:
                                angle = self.angle(shoulder, elbow, wrist)
                                body_angle = self.angle(shoulder, hip, ankle)
                                # Wider thresholds tolerate normal camera and landmark variation.
                                # Rep counting is not blocked by a slightly imperfect body-line estimate.
                                if angle < 105:
                                    self.stage = "down"
                                    feedback = "Good bottom position; press up while keeping your trunk braced"
                                elif angle > 145:
                                    if self.stage == "down":
                                        self.reps += 1
                                    self.stage = "up"
                                    feedback = "Top position detected; lower with control for the next rep"
                                elif body_angle < 150:
                                    feedback = "Keep your body in a straighter line from shoulder to ankle"
                                else:
                                    feedback = "Move through a comfortable, controlled range"
                            else:
                                feedback = "Use a side view; keep shoulder, elbow, wrist, hip and ankle visible"

                    self.last_feedback = feedback
                    self.last_angle = angle
                    cv2_module.rectangle(image, (10, 10), (min(width - 10, 430), 104), (15, 24, 43), -1)
                    cv2_module.putText(image, f"{exercise_name} reps: {self.reps}", (22, 40), cv2_module.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2_module.putText(image, f"Stage: {self.stage}", (22, 68), cv2_module.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    cv2_module.putText(image, feedback[:48], (22, 92), cv2_module.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)
                    return frame.from_ndarray(image, format="bgr24")

            return PostureProcessor

        processor_factory = make_posture_processor(
            posture_cv2, posture_mp, PostureVideoProcessorBase, posture_exercise
        )
        webrtc_streamer(
    key=f"fitnexora-posture-{posture_exercise.lower().replace('-', '')}",
    video_processor_factory=processor_factory,
    media_stream_constraints={
        "video": True,
        "audio": False
    },
    rtc_configuration={
        "iceServers": [
            {
                "urls": [
                    "stun:stun.l.google.com:19302"
                ]
            }
        ]
    },
    async_processing=True,
)
        st.caption(
            "Rep counts and feedback are approximate. The current prototype uses simple 2D joint-angle thresholds; "
            "it does not determine injury risk or guarantee correct form."
        )

    except ImportError as exc:
        st.error(
            "Posture Coach dependencies are missing. Add the packages listed in "
            "posture_requirements.txt to your existing requirements.txt, then redeploy."
        )
        st.code("streamlit-webrtc\nmediapipe\nopencv-python-headless\nav")
        st.caption(f"Dependency detail: {exc}")
    except Exception as exc:
        st.error("The posture coach could not start. Check browser camera permissions and the deployment logs.")
        st.caption(f"Technical detail: {type(exc).__name__}: {exc}")


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


elif page == "App Info":
    st.markdown("""
    <div class="hero">
      <h1>About FITNEXORA</h1>
      <p>A personal fitness and nutrition companion built as a student portfolio project.</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="muscle-info-card">
      <div style="color:#5eead4;font-weight:800;letter-spacing:.12em;text-transform:uppercase;font-size:12px">Created by</div>
      <h2 style="margin:.45rem 0 0">Pratyush Singh Yadav</h2>
      <p style="color:#b6c4d7;margin:.35rem 0 1rem">B.Tech Student · St. Thomas' College of Engineering & Technology, Kolkata</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("### Connect with me")
    link_col1, link_col2 = st.columns(2, gap="medium")
    with link_col1:
        st.link_button(
            "LinkedIn profile",
            "https://www.linkedin.com/in/pratyush-singh-yadav/",
            use_container_width=True,
        )
    with link_col2:
        st.link_button(
            "GitHub profile",
            "https://github.com/Pratyush0110",
            use_container_width=True,
        )

st.markdown("---")
st.caption("FITNEXORA · Portfolio project · Workout templates are educational and should be adapted to individual needs.")
