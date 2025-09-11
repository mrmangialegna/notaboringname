from flask import Flask, request, jsonify, send_file, render_template
import io
import math
import os
import boto3
import json
from pymongo import MongoClient

app = Flask(__name__)

# --- Configurazione MongoDB ---
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/notesdb")
mongo_client = MongoClient(mongo_uri)
db = mongo_client.get_default_database()
notes_collection = db["notes"]
calc_collection = db["calc_history"]

# --- Configurazione S3 ---
s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-west-2"))
bucket_name = os.getenv("S3_BUCKET", "cloning-app-storage")
notes_file = "notes.json"
calc_file = "calc_history.json"

# --- Funzioni per S3 ---
def save_to_s3(key, data):
    s3.put_object(Bucket=bucket_name, Key=key, Body=json.dumps(data))

def load_from_s3(key):
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=key)
        return json.loads(obj["Body"].read().decode())
    except s3.exceptions.NoSuchKey:
        return []

# --- Funzioni sicure per la calcolatrice ---
safe_math = {k: getattr(math, k) for k in dir(math) if not k.startswith("__")}
safe_math.update({"abs": abs, "round": round, "pow": pow})

# --- Helper MongoDB ---
def load_notes():
    return [doc["note"] for doc in notes_collection.find()]

def load_calc_history():
    return [doc["entry"] for doc in calc_collection.find()]

def add_note_mongo(note):
    notes_collection.insert_one({"note": note})

def add_calc_entry(entry):
    calc_collection.insert_one({"entry": entry})

# --- Routes Flask ---
@app.route("/")
def index():
    notes = load_notes()
    calc_history = load_calc_history()
    return render_template("dashboard.html", notes=notes, calc_history=calc_history)

@app.route("/add_note", methods=["POST"])
def add_note():
    note = request.form.get("note")
    if note:
        add_note_mongo(note)
        notes = load_notes()
        save_to_s3(notes_file, notes)  # backup su S3
    return jsonify({"status": "ok", "notes": notes})

@app.route("/download_notes", methods=["GET"])
def download_notes():
    notes = load_notes()
    save_to_s3(notes_file, notes)  # aggiornamento backup S3
    content = "\n".join(notes)
    return send_file(
        io.BytesIO(content.encode()),
        mimetype="text/plain",
        as_attachment=True,
        download_name="notes.txt"
    )

@app.route("/calculate", methods=["POST"])
def calculate():
    expr = request.form.get("expression")
    try:
        result = eval(expr, {"__builtins__": None}, safe_math)
        entry = f"{expr} = {result}"
        add_calc_entry(entry)
        calc_history = load_calc_history()
        save_to_s3(calc_file, calc_history)  # backup su S3
        return jsonify({"result": result, "history": calc_history})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
