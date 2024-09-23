from os import environ

import pdfkit
import redis

from flask import Flask, make_response, render_template, session, jsonify, request, url_for
from flask_session import Session


class Config:
    SECRET_KEY = environ.get("SECRET_KEY")
    SESSION_TYPE = "redis"
    SESSION_REDIS = redis.from_url(environ.get("SESSION_REDIS"))


app = Flask(__name__)
app.config.from_object(Config)
Session(app)


@app.route("/")
def home():
    session["games_failed"] = 0
    return render_template("home.html")


@app.route("/game")
def game():
    return render_template(
        "space_invaders.html",
        games_failed=session["games_failed"],
    )


@app.route("/fail")
def fail():
    session["games_failed"] += 1
    return render_template(
        "player_fail.html",
        games_failed=session["games_failed"],
    )


@app.route("/success")
def success():
    session["games_failed"] = 0
    return render_template("player_success.html")


@app.route("/download-cv")
def cv():
    pdf = pdfkit.from_string(
        input=render_template("cv.html"),
        output_path=False,
        configuration=pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf"),
        options={"enable-local-file-access": ""},
    )
    response = make_response(pdf)
    response.headers.update({
        "Content-Type": "application/pdf",
        "Content-Disposition": "attachment; filename=roy_hanley_cv.pdf",
    })
    return response

# Dummy Data
users = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
    {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
]

@app.route('/')
def index():
    return render_template('index.html', title="Home", users=users)

@app.route('/about')
def about():
    return render_template('about.html', title="About Us")

@app.route('/user/<int:user_id>')
def get_user(user_id):
    user = next((user for user in users if user['id'] == user_id), None)
    if user:
        return render_template('user.html', user=user)
    else:
        return "User not found", 404

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        if name and email:
            new_user = {"id": len(users) + 1, "name": name, "email": email}
            users.append(new_user)
            return redirect(url_for('index'))
        else:
            return "Invalid input", 400
    return render_template('add_user.html')

@app.route('/api/users', methods=['GET'])
def api_get_users():
    return jsonify(users)

@app.route('/api/users/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    user = next((user for user in users if user['id'] == user_id), None)
    if user:
        return jsonify(user)
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/api/users', methods=['POST'])
def api_add_user():
    if not request.json or 'name' not in request.json or 'email' not in request.json:
        return jsonify({"error": "Invalid input"}), 400

    new_user = {
        "id": len(users) + 1,
        "name": request.json['name'],
        "email": request.json['email']
    }
    users.append(new_user)
    return jsonify(new_user), 201

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    user = next((user for user in users if user['id'] == user_id), None)
    if user:
        users.remove(user)
        return jsonify({"message": "User deleted"}), 200
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/contact')
def contact():
    return render_template('contact.html', title="Contact Us")

@app.route('/success')
def success():
    return "Success!"

# Dummy function for logging
def log_message(message):
    print(f"Log: {message}")

# Sample background job
def background_task():
    log_message("Starting background task...")
    # Simulate a task
    for i in range(5):
        log_message(f"Task iteration {i}")
    log_message("Background task finished")
