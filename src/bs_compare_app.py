from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from bs_vs_real_compare import build_comparison_data

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)

@app.route("/")
def index():
    return render_template("bs_compare.html")

@app.route("/api/compare")
def api_compare():
    strike = int(request.args.get("strike", 24000))
    option_type = request.args.get("type", "CE")
    days = int(request.args.get("days", 30))
    data = build_comparison_data(strike, option_type, days)
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=False, port=5002)
