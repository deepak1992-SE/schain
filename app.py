import os
import csv
import json
import re
import requests
from flask import Flask, render_template, request, jsonify, send_file
from io import StringIO, BytesIO

app = Flask(__name__)
validation_results = []

def normalize_ads_txt(ads_txt):
    return [re.sub(r"\s+", " ", line.strip().lower()) for line in ads_txt.splitlines()]

def validate_ads_txt(asi, sid, ads_txt_lines, logs):
    logs.append({"message": f"Validating ads.txt for ASI={asi}, SID={sid}...", "status": "success"})
    pattern = rf"{re.escape(asi.lower())}\s*,\s*{re.escape(str(sid))}"
    for line in ads_txt_lines:
        if re.search(pattern, line):
            logs.append({"message": f"Passed: SID {sid} found in app-ads.txt for ASI {asi}.", "status": "success"})
            return "Passed"
    logs.append({"message": f"Failed: SID {sid} not found under ASI {asi} in app-ads.txt.", "status": "error"})
    return "Failed"

def validate_sellers_json(asi, sid, logs):
    try:
        url = f"https://{asi}/sellers.json"
        logs.append({"message": f"Validating sellers.json for ASI={asi}, SID={sid}...", "status": "success"})
        response = requests.get(url, timeout=5)

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logs.append({"message": f"Failed to parse JSON from sellers.json for ASI {asi}: {e}", "status": "error"})
            return "", "", "Failed"

        for seller in data.get('sellers', []):
            if str(seller.get("seller_id")) == str(sid):
                name = seller.get("name", "")
                domain = seller.get("domain", "")
                logs.append({"message": f"Passed: SID {sid} found in sellers.json for ASI {asi}.", "status": "success"})
                return name, domain, "Passed"

        logs.append({"message": f"Failed: SID {sid} not found in sellers.json for ASI {asi}.", "status": "error"})
        return "", "", "Failed"

    except Exception as e:
        logs.append({"message": f"Error: Could not fetch sellers.json for ASI {asi}: {e}", "status": "error"})
        return "", "", "Failed"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    global validation_results
    validation_results = []
    logs = []

    schain_input = request.form.get("schain", "")
    ads_txt_url = request.form.get("ads_txt_url", "").strip()
    pubmatic_id = request.form.get("pubmatic_id", "").strip()
    pubmatic_json_url = request.form.get("pubmatic_json_url", "").strip()
    nodes = []

    try:
        schain_json = json.loads(schain_input)
        for node in schain_json.get("schain", []):
            asi = node.get("seller_url", "").strip()
            sid = str(node.get("seller_id", "")).strip()
            if asi and sid:
                nodes.append({"asi": asi, "sid": sid})
    except Exception as e:
        return jsonify({"status": "Failed", "logs": [{"message": f"Invalid sChain format: {str(e)}", "status": "error"}]})

    try:
        ads_response = requests.get(ads_txt_url, timeout=5)
        ads_txt_lines = normalize_ads_txt(ads_response.text)
        logs.append({"message": f"app-ads.txt fetched and normalized from {ads_txt_url}.", "status": "success"})
    except Exception as e:
        ads_txt_lines = []
        logs.append({"message": f"Error: Could not fetch or normalize app-ads.txt from {ads_txt_url}. {e}", "status": "error"})

    for node in nodes:
        asi = node["asi"]
        sid = node["sid"]

        ads_txt_status = validate_ads_txt(asi, sid, ads_txt_lines, logs)
        name, domain, sellers_json_status = validate_sellers_json(asi, sid, logs)

        validation_results.append({
            "asi": asi,
            "sid": sid,
            "name": name,
            "domain": domain,
            "ads_txt": ads_txt_status,
            "sellers_json": sellers_json_status
        })

    if pubmatic_id and pubmatic_json_url:
        validate_ads_txt("pubmatic.com", pubmatic_id, ads_txt_lines, logs)
        validate_sellers_json("pubmatic.com", pubmatic_id, logs)

    return jsonify({
        "status": "Passed",
        "logs": logs,
        "table": validation_results
    })

@app.route('/download')
def download_csv():
    global validation_results

    text_stream = StringIO()
    writer = csv.writer(text_stream)
    writer.writerow([
        "ASI (Domain)", "SID",
        "Seller Name", "Seller Domain",
        "Ads.txt Status", "Sellers.json Status"
    ])
    for row in validation_results:
        writer.writerow([
            row.get('asi', ''),
            row.get('sid', ''),
            row.get('name', ''),
            row.get('domain', ''),
            row.get('ads_txt', ''),
            row.get('sellers_json', '')
        ])

    byte_stream = BytesIO()
    byte_stream.write(text_stream.getvalue().encode('utf-8'))
    byte_stream.seek(0)

    return send_file(
        byte_stream,
        mimetype='text/csv',
        download_name='validation_results.csv',
        as_attachment=True
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
