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
