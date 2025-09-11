from flask import Flask, request, jsonify, send_file, render_template
import io
import math

app = Flask(__name__)

notes = []
calc_history = []

# Funzioni sicure disponibili per la calcolatrice
safe_math = {k: getattr(math, k) for k in dir(math) if not k.startswith("__")}
safe_math.update({"abs": abs, "round": round, "pow": pow})

@app.route("/")
def index():
    return render_template("dashboard.html", notes=notes, calc_history=calc_history)

@app.route("/add_note", methods=["POST"])
def add_note():
    note = request.form.get("note")
    if note:
        notes.append(note)
    return jsonify({"status": "ok", "notes": notes})

@app.route("/download_notes", methods=["GET"])
def download_notes():
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
        calc_history.append(f"{expr} = {result}")
        return jsonify({"result": result, "history": calc_history})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
