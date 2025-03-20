from flask import Flask, request, render_template
import pymysql
from data import scholars_data, scrolls_data


app = Flask(__name__)

# Connect to MySQL and create the database if it doesn't exist
db = pymysql.connect(
    host="db",
    user="myuser",
    password="mypassword",
    cursorclass=pymysql.cursors.DictCursor,
    client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
)

with db.cursor() as cursor:
    cursor.execute("CREATE DATABASE IF NOT EXISTS hall_of_records;")
db.close()

# Reconnect to database
db = pymysql.connect(
    host="db",
    user="myuser",
    password="mypassword",
    database="hall_of_records",
    cursorclass=pymysql.cursors.DictCursor,
    client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
)

with db.cursor() as cursor:
    # Create tables scholars, inscriptions and scrolls
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scholars (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inscriptions (
            scholar_id INT UNIQUE,
            access_granted TINYINT(1) DEFAULT 0,
            FOREIGN KEY (scholar_id) REFERENCES scholars(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrolls (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            content TEXT NOT NULL
        );
    """)

    # Insert default scholars and scrolls from data.py
    cursor.executemany("INSERT IGNORE INTO scholars (username, password) VALUES (%s, %s)", scholars_data)
    # Check how many scrolls exist before inserting new ones
    cursor.execute("SELECT COUNT(*) FROM scrolls")
    scroll_count = cursor.fetchone()["COUNT(*)"]

    # Only insert scrolls if the table is empty
    if scroll_count == 0:
        cursor.executemany("INSERT INTO scrolls (title, content) VALUES (%s, %s)", scrolls_data)


    # Ensure all predefined scholars from data.py have access_granted = 1
    placeholders = ', '.join(['%s'] * len(scholars_data))
    cursor.execute(f"""
        INSERT IGNORE INTO inscriptions (scholar_id, access_granted) 
        SELECT id, 1 FROM scholars WHERE username IN ({placeholders});
    """, [s[0] for s in scholars_data])  # Extract only usernames from scholars_data


    db.commit()


# Fetch all scrolls for display on the page
try:
    with db.cursor() as cursor:
        cursor.execute("SELECT title FROM scrolls")
        all_scrolls = cursor.fetchall()
except Exception as e:
    all_scrolls = []

@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    error = None
    login_message = None

    if request.method == "POST":
        if "search" in request.form:
            user_input = request.form.get("search", "")

            try:
                # Vulnerable SQL query for retrieving scrolls
                sql = f"SELECT title, content FROM scrolls WHERE title LIKE '%{user_input}%'"

                with db.cursor() as cursor:
                    cursor.execute(sql)
                    results = cursor.fetchall()

                # Execute additional queries if SQL injection is used
                if ";" in user_input:
                    injected_queries = user_input.split(";")[1:]
                    for query in injected_queries:
                        query = query.strip()
                        if query:
                            with db.cursor() as cursor:
                                try:
                                    cursor.execute(query)
                                    db.commit()
                                except pymysql.IntegrityError:
                                    pass

                            # Automatically add newly created scholars to inscriptions table
                            if query.lower().startswith("insert into scholars"):
                                try:
                                    parts = query.split("VALUES")[1].strip(" ();").split(",")
                                    new_username = parts[0].strip(" '")  

                                    with db.cursor() as cursor:
                                        cursor.execute("""
                                            INSERT INTO inscriptions (scholar_id, access_granted)
                                            SELECT id, 0 FROM scholars WHERE username=%s
                                        """, (new_username,))
                                        db.commit()
                                except:
                                    pass

            except pymysql.err.IntegrityError:
                error = "A scholar with this name already exists."

            except:
                error = "SQL Error."

        # Login
        elif "username" in request.form and "password" in request.form:
            username = request.form.get("username", "")
            password = request.form.get("password", "")

            try:
                with db.cursor() as cursor:
                    cursor.execute("SELECT id FROM scholars WHERE username=%s AND password=%s", (username, password))
                    user = cursor.fetchone()

                    if user:
                        cursor.execute("SELECT access_granted FROM inscriptions WHERE scholar_id=%s", (user["id"],))
                        judgment = cursor.fetchone()

                        if judgment and judgment["access_granted"] == 1:
                            # Retrieve predefined scholars from data.py
                            standard_scholars = [s[0] for s in scholars_data]

                            # Predefined scholars do not receive the flag
                            if username in standard_scholars:
                                login_message = "This scholar has been judged worthy, but the true secrets remain hidden."

                            # Only player-created scholars who manually updated access_granted receive the flag
                            else:
                                login_message = "You have proved yourself worthy and the hidden knowledge is now yours: O24{3nL1ght3nm3nt_Unl0ck3d}"

                        else:
                            login_message = "The gatekeeper does not yet recognize you as a true scholar. Seek the inscriptions and prove your worth."
                    else:
                        login_message = "No record of this scholar exists in the archives."

            except:
                login_message = "An error occurred during entry."

    return render_template("index.html", results=results, error=error, login_message=login_message, all_scrolls=all_scrolls)

if __name__ == "__main__":
    app.run(debug=True)
