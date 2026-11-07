
import os

from flask import Flask, jsonify
from google.cloud import storage, kms

app = Flask(__name__)

@app.get("/")
def health():
    return jsonify({"status": "running"})

@app.get("/read-secret")
def read_secret():
    # Read encrypted file from Project B
    bucket_name = os.environ["BUCKET"]
    blob = storage.Client().bucket(bucket_name).blob(
        "secret.json.enc"
    )
    encrypted_data = blob.download_as_bytes()

    # Call Project B's KMS key
    key_name = (
        f"projects/{os.environ['PROJECT_B']}"
        f"/locations/{os.environ['REGION']}"
        "/keyRings/shared-secrets"
        "/cryptoKeys/secret-key"
    )

    client = kms.KeyManagementServiceClient()
    response = client.decrypt(
        request={
            "name": key_name,
            "ciphertext": encrypted_data,
        }
    )

    # Demo only: return decrypted contents
    return app.response_class(
        response.plaintext,
        mimetype="application/json",
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
