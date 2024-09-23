from os import environ

import pdfkit
import redis

from flask import Flask, make_response, render_template, session
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
   return None 
