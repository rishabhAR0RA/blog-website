import bleach
import datetime as dt
import smtplib
import ssl

from dotenv import load_dotenv
from flask import (
    abort,
    Flask,
    flash,
    Markup,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from flask_login import (
    current_user,
    login_required,
    login_user,
    LoginManager,
    logout_user,
    UserMixin,
)
from flask_sqlalchemy import SQLAlchemy
from forms import CreatePostForm, CommentForm, LoginForm, RegisterForm
from functools import wraps
from flask_gravatar import Gravatar
from models import db, BlogPost, Comment, User
from os import environ as env
from sqlalchemy import exists
from werkzeug.security import check_password_hash, generate_password_hash


load_dotenv()
CURRENT_YEAR = dt.datetime.now().year
DEVELOPER = "Rishabh Arora"
first_request = True

app = Flask(__name__)
app.config["SECRET_KEY"] = env["CKEDITOR_KEY"]  # Your token
ckeditor = CKEditor(app)
bootstrap = Bootstrap(app)  # For using bootstrap 5

# Initialize Gravatar
gravatar = Gravatar(
    app,
    size=40,
    rating="g",
    default="retro",
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None,
)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

##CONNECT TO DB
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blogs.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# These lines of code are initializing the Flask-Login extension and configuring it to work with the
# current Flask application.
login_manager = LoginManager()
login_manager.init_app(app=app)
login_manager.login_view = "login"

db.init_app(app)


@login_manager.user_loader
def user_loader(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized_handler():
    return (
        """
    <h1>Unauthorized</h1>
    You are unauthorized to use that url, please login
    """,
        401,
    )


# Protect Routes by making Decorators
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If user current user isnt authenticated or id is not 1 then return abort with 403 error
        if current_user.is_anonymous or current_user.id != 1:
            return abort(403)
        # Otherwise continue with the route function
        return f(*args, **kwargs)

    return decorated_function


# Creating the table for the first time
@app.before_request
def create_table():
    global first_request
    if first_request:
        db.create_all()
        first_request = False


@app.route("/")
def get_all_posts():
    posts = BlogPost.query.all()
    logged_in = bool(current_user.is_authenticated)
    user_id = current_user.id if current_user.is_authenticated else None

    return render_template(
        "index.html",
        year=CURRENT_YEAR,
        dev=DEVELOPER,
        all_posts=posts,
        logged_in=logged_in,
        user_id=user_id,
    )


@app.route("/login", methods=["GET", "POST"])
def user_login():
    form = LoginForm()

    if form.validate_on_submit():
        email = request.form.get("email")
        password = request.form.get("password")

        user = db.session.query(User).filter_by(email=email).first()

        if (
            user is not None
            and email == user.email
            and check_password_hash(user.password, password)
        ):
            login_user(user)
            logged_in = bool(current_user.is_authenticated)
            return redirect(url_for("get_all_posts"))
        else:
            flash(message="Invalid Username or password!")
            return redirect(url_for("user_login"))

    return render_template("login.html", year=CURRENT_YEAR, dev=DEVELOPER, form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("get_all_posts"))


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if user_exists := db.session.query(
            exists().where(User.email == email)
        ).scalar():
            flash(message="Provided email is already registered.")
            return redirect(url_for("register"))

        else:
            hashed_password = generate_password_hash(
                password=password, method="pbkdf2:sha256", salt_length=8
            )

            new_user = User(
                name=name, email=request.form.get("email"), password=hashed_password
            )

            db.session.add(new_user)
            db.session.commit()

            return redirect(url_for("user_login"))
    return render_template("register.html", year=CURRENT_YEAR, dev=DEVELOPER, form=form)


@app.route("/post/<int:index>", methods=["GET", "POST"])
def show_post(index):
    form = CommentForm()

    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash(message="Please login to post comment.")
        else:
            comment = request.form.get("comment")

            new_comment = Comment(
                text=request.form.get("comment"),
                author_id=current_user.id,
                post_id=index,
            )

            db.session.add(new_comment)
            db.session.commit()
        return redirect(url_for("show_post", index=index))

    logged_in = bool(current_user.is_authenticated)
    user_id = current_user.id if current_user.is_authenticated else None
    requested_post = None
    posts = BlogPost.query.all()

    post_comments = db.session.query(Comment).filter_by(post_id=index).first()

    for blog_post in posts:
        if blog_post.id == index:
            requested_post = blog_post
            requested_content = Markup(requested_post.body)

    return render_template(
        "post.html",
        year=CURRENT_YEAR,
        dev=DEVELOPER,
        post=requested_post,
        content=requested_content,
        logged_in=logged_in,
        user_id=user_id,
        form=form,
        comments=post_comments,
    )


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post = BlogPost.query.filter_by(id=post_id).first()

    db.session.delete(post)
    db.session.commit()

    return redirect(url_for("get_all_posts"))


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def new_post():
    if request.method == "POST":
        now = dt.datetime.now()
        formatted_date = now.strftime("%B %d, %Y")

        new_post = BlogPost(
            title=request.form.get("title"),
            subtitle=request.form.get("subtitle"),
            img_url=request.form.get("img_url"),
            body=request.form.get("body"),
            date=formatted_date,
            author_id=current_user.id,
        )

        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))

    form = CreatePostForm()
    return render_template(
        "make-post.html", year=CURRENT_YEAR, dev=DEVELOPER, form=form
    )


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    if request.method == "POST":
        post_to_update = BlogPost.query.get(post_id)
        post_to_update.title = request.form.get("title")
        post_to_update.subtitle = request.form.get("subtitle")
        post_to_update.img_url = request.form.get("img_url")
        post_to_update.body = request.form.get("body")

        db.session.commit()
        return redirect(url_for("show_post", index=post_id))

    post = BlogPost.query.filter_by(id=post_id).first()

    form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body,
    )
    return render_template(
        "make-post.html", year=CURRENT_YEAR, dev=DEVELOPER, form=form
    )


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method != "POST":
        return render_template("contact.html", year=CURRENT_YEAR, dev=DEVELOPER)
    user = request.form["username"]
    mail = request.form["email"]
    mobile = request.form["phone"]
    msg = request.form["message"]

    ctx = ssl.create_default_context()
    password = env["EMAIL_PASS"]  # Your app password goes here
    sender = "receivertest66@gmail.com"  # Your e-mail address
    receiver = f"{mail}"  # Recipient's address

    message = f"Subject: {user} Thanks for connecting with us."

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", port=465, context=ctx) as server:
            server.login(sender, password)
            server.sendmail(from_addr=sender, to_addrs=receiver, msg=message)

        # Email sent successfully
        flash(message=["Email sent successfully.", "success"])
    except Exception as e:
        # Email sending failed
        flash(message=["Failed to send email.", "error"])
        print(e)  # Print the error message for debugging purposes

    return redirect(url_for("contact"))


@app.route("/about")
def about():
    return render_template("about.html", year=CURRENT_YEAR, dev=DEVELOPER)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
