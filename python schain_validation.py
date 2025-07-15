from flask import Flask, request, jsonify
import requests
import json
import re

app = Flask(__name__)

def fetch_file(url):
    """Fetch a file from the provided URL."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        if "application/json" in response.headers.get("Content-Type", ""):
            return response.json()
        return response.text
    except requests.RequestException as e:
        return f"Error fetching {url}: {e}"

def parse_schain(schain):
    """Parse sChain JSON."""
    if isinstance(schain, str):
        try:
            return json.loads(schain)
        except json.JSONDecodeError:
            return None
    return schain

def normalize_ads_txt(ads_txt):
    """Normalize app-ads.txt content."""
    return [re.sub(r"\s+", " ", line.strip().lower()) for line in ads_txt.splitlines()]

@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html>
    <body>
    <h1>sChain Validation Backend Ready!</h1>
    </body>
    </html>
    """

@app.route("/validate", methods=["POST"])
def validate():
    logs = []

    def log_message(message):
        """Helper function to log messages."""
        logs.append(message)

    try:
        # Parse sChain JSON
        schain = parse_schain(request.form.get("schain"))
        if not schain or not isinstance(schain, dict):
            log_message("Invalid sChain JSON format")
            return jsonify({"error": "Invalid sChain JSON format", "logs": logs})

        # Fetch Vuukle sellers.json
        sellers_json_url = request.form.get("sellers_json_url")
        sellers_json = fetch_file(sellers_json_url)
        if not sellers_json or "sellers" not in sellers_json:
            log_message("Invalid Vuukle sellers.json format or URL")
            return jsonify({"error": "Invalid Vuukle sellers.json format or URL", "logs": logs})
        sellers_json = sellers_json["sellers"]
        log_message("Fetched Vuukle sellers.json successfully.")

        # Fetch PubMatic sellers.json
        pubmatic_json_url = request.form.get("pubmatic_json_url")
        pubmatic_json = fetch_file(pubmatic_json_url)
        if not pubmatic_json or "sellers" not in pubmatic_json:
            log_message("Invalid PubMatic sellers.json format or URL")
            return jsonify({"error": "Invalid PubMatic sellers.json format or URL", "logs": logs})
        pubmatic_json = pubmatic_json["sellers"]
        log_message("Fetched PubMatic sellers.json successfully.")

        # Fetch and normalize app-ads.txt
        ads_txt_url = request.form.get("ads_txt_url")
        ads_txt = fetch_file(ads_txt_url)
        if not ads_txt:
            log_message("Failed to fetch app-ads.txt.")
            return jsonify({"error": "Failed to fetch app-ads.txt.", "logs": logs})
        normalized_ads_txt = normalize_ads_txt(ads_txt)
        log_message("Normalized app-ads.txt successfully.")

        # Validate PubMatic
        pubmatic_id = request.form.get("pubmatic_id")
        pubmatic_result = validate_pubmatic(pubmatic_id, pubmatic_json, normalized_ads_txt, logs)

        # Validate sChain nodes
        node_results = []
        for node in schain.get("nodes", []):
            result = validate_node(node, sellers_json, normalized_ads_txt, logs)
            node_results.append(result)

        return jsonify({
            "pubmatic_result": pubmatic_result,
            "node_results": node_results,
            "logs": logs
        })

    except Exception as e:
        log_message(f"Error occurred: {str(e)}")
        return jsonify({"error": str(e), "logs": logs})

def validate_pubmatic(pubmatic_id, pubmatic_json, ads_txt, logs):
    """Validate PubMatic's seller_id in sellers.json and app-ads.txt."""
    logs.append(f"Validating PubMatic ID: {pubmatic_id}")
    asi_pattern = rf"pubmatic\.com\s*,\s*{re.escape(pubmatic_id)}".lower()
    if not any(re.search(asi_pattern, line) for line in ads_txt):
        logs.append(f"PubMatic ID {pubmatic_id} not found in app-ads.txt.")
        return "Failed"
    logs.append("PubMatic validation successful.")
    return "Successful"

def validate_node(node, sellers_json, ads_txt, logs):
    """Validate an individual sChain node."""
    seller_id = node.get("sid")
    asi = node.get("asi")
    logs.append(f"Validating Node: ASI={asi}, Seller ID={seller_id}")

    seller_match = next((entry for entry in sellers_json if entry.get("seller_id") == seller_id), None)
    if not seller_match:
        logs.append(f"Seller ID {seller_id} not found in sellers.json.")
        return "Failed"

    asi_pattern = rf"{re.escape(asi)}\s*,\s*{re.escape(seller_id)}".lower()
    if not any(re.search(asi_pattern, line) for line in ads_txt):
        logs.append(f"Seller domain {asi} and ID {seller_id} not found in app-ads.txt.")
        return "Failed"

    logs.append(f"Node validated successfully: ASI={asi}, Seller ID={seller_id}")
    return "Successful"

if __name__ == "__main__":
    app.run(debug=True)
