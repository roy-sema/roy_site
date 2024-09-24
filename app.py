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


# Dummy Python script

import random

# Function to generate a random list of numbers
def generate_random_numbers(count, start=1, end=100):
    random_numbers = [random.randint(start, end) for _ in range(count)]
    return random_numbers

# Function to calculate the average of a list
def calculate_average(numbers):
    if len(numbers) == 0:
        return 0
    return sum(numbers) / len(numbers)

# Function to find the maximum and minimum number in a list
def find_min_max(numbers):
    if not numbers:
        return None, None
    return min(numbers), max(numbers)

# Dummy function to check if a number is even or odd
def is_even(number):
    return number % 2 == 0

# Function to print whether each number is even or odd
def print_even_odd(numbers):
    for num in numbers:
        if is_even(num):
            print(f"{num} is even")
        else:
            print(f"{num} is odd")
