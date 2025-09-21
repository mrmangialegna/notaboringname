from flask import Flask, request, jsonify, send_file, render_template, session, redirect, url_for
import io
import math
import os
import boto3
import json
from pymongo import MongoClient
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "supersecretkey")

# --- MongoDB ---
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/notesdb")
try:
    mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    # Test connection
    mongo_client.admin.command('ping')
    db = mongo_client.get_default_database()
    notes_collection = db["notes"]
    calc_collection = db["calc_history"]
    users_collection = db["users"]
    print("MongoDB connected successfully")
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    # Fallback to in-memory storage
    notes_collection = None
    calc_collection = None
    users_collection = None

# --- S3 ---
s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-west-2"))
bucket_name = os.getenv("S3_BUCKET", "cloning-app-storage")

# --- Safe math ---
safe_math = {k: getattr(math, k) for k in dir(math) if not k.startswith("__")}
safe_math.update({"abs": abs, "round": round, "pow": pow})

# --- Authentication decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper functions ---
def save_to_s3(key, data):
    s3.put_object(Bucket=bucket_name, Key=key, Body=json.dumps(data))

def load_from_s3(key):
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=key)
        return json.loads(obj["Body"].read().decode())
    except s3.exceptions.NoSuchKey:
        return []

def load_notes():
    if notes_collection:
        return list(notes_collection.find({}, {"_id": 0}))
    return []

def load_calc_history():
    if calc_collection:
        return list(calc_collection.find({}, {"_id": 0}))
    return []

def add_note(note, tags=[]):
    if notes_collection:
        notes_collection.insert_one({
            "note": note,
            "tags": tags,
            "created_at": datetime.utcnow().isoformat()
        })

def add_calc_entry(expr, result):
    if calc_collection:
        calc_collection.insert_one({
            "expression": expr,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        })

def add_user(username, password):
    if users_collection:
        users_collection.insert_one({"username": username, "password": password})

def verify_user(username, password):
    if users_collection:
        user = users_collection.find_one({"username": username})
        return user and user["password"] == password
    # Fallback for demo
    return username == "admin" and password == "admin"

# --- Routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if verify_user(username, password):
            session["username"] = username
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    notes = load_notes()
    calc_history = load_calc_history()
    return render_template("dashboard.html", notes=notes, calc_history=calc_history)

@app.route("/add_note", methods=["POST"])
@login_required
def add_note_route():
    note = request.form.get("note")
    tags = request.form.getlist("tags")
    if note:
        add_note(note, tags)
        save_to_s3("notes.json", load_notes())
    return jsonify({"status": "ok", "notes": load_notes()})

@app.route("/download_notes")
@login_required
def download_notes():
    notes = load_notes()
    save_to_s3("notes.json", notes)
    content = "\n".join([n["note"] for n in notes])
    return send_file(io.BytesIO(content.encode()), mimetype="text/plain", as_attachment=True, download_name="notes.txt")

@app.route("/calculate", methods=["POST"])
@login_required
def calculate():
    expr = request.form.get("expression")
    try:
        result = eval(expr, {"__builtins__": None}, safe_math)
        add_calc_entry(expr, result)
        save_to_s3("calc_history.json", load_calc_history())
        return jsonify({"result": result, "history": load_calc_history()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
