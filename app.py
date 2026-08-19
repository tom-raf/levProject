"""Dashboard shell: GET / serves the blueprint-styled page recreating
design/design_handoff_dashboard/'s mockup. Live/Simulated SSE routes are
wired in by tickets #10-#11 -- this ticket (#9) is the static shell only."""

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
