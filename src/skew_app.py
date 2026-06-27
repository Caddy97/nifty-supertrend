from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from skew_analysis import analyze_skew

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)

@app.route("/")
def index():
    return render_template("skew_chart.html")

@app.route("/api/skew")
def api_skew():
    strikes_param = request.args.get("strikes", "23500,23700,23900,24000,24100,24300,24500")
    strikes = [int(s) for s in strikes_param.split(",")]
    option_type = request.args.get("type", "CE")
    days = int(request.args.get("days", 10))
    rows = analyze_skew(strikes, option_type, days)
    return jsonify(rows)

if __name__ == "__main__":
    app.run(debug=False, port=5003)
