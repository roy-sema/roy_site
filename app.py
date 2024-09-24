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


from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# Dummy data for a list of products
products = [
    {'id': 1, 'name': 'Laptop', 'price': 999.99},
    {'id': 2, 'name': 'Smartphone', 'price': 499.99},
    {'id': 3, 'name': 'Headphones', 'price': 199.99}
]


# Home route
@app.route('/')
def home():
    return "<h1>Welcome to the Product Store!</h1>"


# List products route
@app.route('/products')
def list_products():
    return jsonify(products)


# Add product route
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        new_product = {
            'id': len(products) + 1,
            'name': request.form['name'],
            'price': float(request.form['price'])
        }
        products.append(new_product)
        return redirect(url_for('list_products'))

    return '''
        <form method="POST">
            Product Name: <input type="text" name="name"><br>
            Price: <input type="text" name="price"><br>
            <input type="submit" value="Add Product">
        </form>
    '''


# Get a single product by ID
@app.route('/product/<int:product_id>')
def get_product(product_id):
    product = next((p for p in products if p['id'] == product_id), None)
    if product:
        return jsonify(product)
    return '<h3>Product not found</h3>', 404


# Delete product route
@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    global products
    products = [p for p in products if p['id'] != product_id]
    return redirect(url_for('list_products'))


# Error handling for 404
@app.errorhandler(404)
def page_not_found(e):
    return "<h1>404 - Page Not Found</h1>", 404


if __name__ == '__main__':
    app.run(debug=True)
