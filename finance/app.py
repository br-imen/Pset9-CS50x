import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")
# db.execute("DROP TABLE purchase;")
# db.execute("CREATE TABLE purchase (user_id INT NOT NULL, symbol_company TEXT NOT NULL,operation TEXT NOT NULL, price_share NUMERIC NOT NULL, number_shares INT,  date DATE DEFAULT (datetime('now','localtime')), FOREIGN KEY (user_id) REFERENCES users(id) );")
# db.execute("DROP TABLE own;")
# db.execute("CREATE TABLE own (user_id INT NOT NULL, symbol_company TEXT NOT NULL, price_share NUMERIC NOT NULL, number_shares INT, FOREIGN KEY (user_id) REFERENCES users(id) );")
# db.execute("UPDATE users SET cash = 10000.0 WHERE id = ? ;", session['user_id'])


# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    dict_purchase = db.execute("SELECT number_shares, symbol_company from own where user_id = ?;", session['user_id'])
    total_stocks = float(0)
    list_stocks = []
    for row in dict_purchase:
        dict_company = {}
        dict_lookup = lookup(row['symbol_company'])
        dict_company['shares'] = int(row['number_shares'])
        dict_company['symbol'] = dict_lookup['symbol']
        dict_company['name'] = dict_lookup['name']
        dict_company['price'] = float(dict_lookup['price'])
        dict_company['total_shares'] = float(dict_company['shares'] * dict_company['price'])
        total_stocks = total_stocks + dict_company['total_shares']
        list_stocks.append(dict_company)

    current_cash = db.execute("SELECT cash FROM users WHERE id = ? ; ", session['user_id'])

    total = total_stocks + current_cash[0]['cash']

    return render_template("index.html", list=list_stocks, cash=usd(current_cash[0]['cash']), total=usd(total), total_stocks=usd(total_stocks))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # check if symbol exist and valid with lookup:
        symbol = request.form.get("symbol")
        dict_variable = lookup(symbol)
        if not symbol or dict_variable is None:
            return apology("unvalid symbol")

        # check if number of shares exist, is int and positive to be valid:
        try:
            shares = int(request.form.get("shares"))
        except Exception:
            return apology("unvalid integer value")

        if not shares or shares < 0:
            return apology("unvalid shares")

        # Select cash from user and the price of one share:
        cash = db.execute("SELECT cash FROM users")
        cash_user = cash[0]["cash"]
        price_share = dict_variable["price"]

        # check if he can efford the price of shares:
        if (shares * price_share) > cash_user:
            return apology("cannot afford the number of shares at the current price.")

        # if the user can buy shares we update his cash by substraction the price of shares-
        # from his acutal cash and insert the purchase data into tables purchase and own:
        cash_user = cash_user - (shares * price_share)
        db.execute("INSERT INTO purchase (user_id, symbol_company, price_share, operation, number_shares) VALUES (?,?,?,?,?);",
                session['user_id'], symbol.lower(), price_share, "bought", shares)

        # if he buying from a new company we will insert it in table own, if he had shares from the company we will update it:
        own = db.execute("SELECT symbol_company, number_shares FROM own where user_id = ? and symbol_company = ?",
                        session['user_id'], symbol.lower())

        if not own:
            db.execute("INSERT INTO own(user_id, symbol_company, price_share, number_shares) VALUES (?,?,?,?);",
                       session['user_id'], symbol.lower(), price_share, shares)
        else:
            actualshares = own[0]['number_shares']
            actualshares = actualshares + shares
            db.execute("UPDATE own SET number_shares = ? WHERE user_id = ? AND symbol_company = ?;",
                       actualshares, session['user_id'], symbol.lower())

        db.execute("UPDATE users SET cash = ? WHERE id = ?;",cash_user,session['user_id'])

        return index()

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    dict_history = db.execute(
        "SELECT symbol_company, price_share, number_shares, operation, date FROM purchase WHERE user_id = ? ;", session['user_id'])

    list_history = []

    for row in dict_history:
        dict_history = {}
        dict_history['number_shares'] = int(row['number_shares'])
        dict_history['symbol_company'] = row['symbol_company']
        dict_history['price_share'] = row['price_share']
        dict_history['operation'] = row['operation']
        dict_history['date'] = row['date']
        list_history.append(dict_history)

    return render_template("history.html", list=list_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        dict_symbol = lookup(symbol)
        if dict_symbol is None or not symbol:
            return apology("wrong stock's symbol")
        else:
            return render_template("quoted.html", name=dict_symbol["name"], price=usd(dict_symbol["price"]))
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        name = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not (name and password and confirmation):
            return apology("password and name is required")
        if not password == confirmation:
            return apology("passwords didn't match")

        name_check = db.execute("SELECT username FROM users WHERE username = ?", (name))
        if name_check:
            return apology("username exist")

        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username,hash) VALUES (?,?);", name,hash)
        print("succeed")
        return render_template("login.html")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        # check is stock's symbol selected:
        if not request.form.get("symbol"):
            return apology("stock's symbol is required")

        # check if there is shares in selected stock's symbol:
        listdict_shares = db.execute("SELECT number_shares FROM own WHERE user_id = ? and symbol_company = ? ;",
                                     session['user_id'], request.form.get("symbol").lower())
        shares_owned = listdict_shares[0]['number_shares']
        if not shares_owned:
            return apology("you don't own any shares")

        # check if number of shares exist, is int and positive to be valid:
        try:
            shares = int(request.form.get("shares"))
        except Exception:
            return apology("unvalid shares")

        if not shares or shares < 0 or shares > shares_owned:
            return apology("unvalid shares")

        # select price of one share:
        dict_sell = lookup(request.form.get("symbol"))
        price = dict_sell['price']
        symbol = dict_sell['symbol']

        # select cash:
        listdict_cash = db.execute("SELECT cash FROM users WHERE id = ?;", session['user_id'])
        cash = float(listdict_cash[0]['cash'])

        # update cash and shares_owned
        cash = cash + (price * shares)
        shares_owned = shares_owned - shares

        # update table own if number_shares > 0 and delete it if number_shares = 0 :
        if shares_owned > 0:

            db.execute("UPDATE own SET number_shares = ? WHERE user_id = ? and symbol_company = ?;",
                       shares_owned, session['user_id'], symbol.lower())
        else:
            db.execute("DELETE FROM own WHERE user_id = ? and symbol_company = ?", session['user_id'], symbol.lower())

        # update in table users , cash:
        db.execute("UPDATE users SET cash = ?  WHERE id = ?;", cash, session['user_id'])

        # insert into table sell:
        db.execute("INSERT INTO purchase (user_id, symbol_company, price_share, operation, number_shares) VALUES (?,?,?,?,?);",
                session['user_id'], symbol.lower(), price, "sold", shares)

        return index()

    else:
        # printing stock's symbol in select input html:
        symbols = db.execute("SELECT symbol_company FROM own WHERE user_id = ?;",session['user_id'])
        list = []
        for row in symbols:
           # if row['number_shares'] > 0 :
            # print(f"row['number_shares'] of display index.html from own table : {row['number_shares']}")
            list.append(row['symbol_company'])

        return render_template("sell.html", list=list)
