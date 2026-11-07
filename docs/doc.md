# GCP Cloud KMS — Cross-Project Hands-On Lab

**Goal:** Build a Python service in Project A that reads encrypted data from Project B and decrypts it using Project B's Cloud KMS key.

**Environment:** Google Cloud Console + Cloud Shell  
**Region:** europe-west2 (London)  
**Runtime:** Python + Cloud Run  
**Security:** IAM + Cloud KMS  
**Audience:** Cloud architects and engineers

---

# 1. Architecture

We will create two projects.

## Project A — Consumer

Contains:

- Cloud Run Python API
- Runtime service account: `project-a-reader`
- Build service account: `project-a-builder`

## Project B — Data Owner

Contains:

- Cloud Storage bucket
- Encrypted JSON file
- Cloud KMS key ring
- Symmetric encryption key

## Data flow

```text
PROJECT A                              PROJECT B
+-----------------------+              +------------------------+
|                       |              |                        |
| Cloud Run             |              | Cloud Storage          |
| Python API            |----READ----->| secret.json.enc        |
|                       |              |                        |
| Service Account       |              +------------------------+
| project-a-reader      |
|                       |              +------------------------+
|                       |              |                        |
|                       |---DECRYPT--->| Cloud KMS              |
|                       |              | shared-secrets         |
|                       |              | secret-key             |
+-----------------------+              +------------------------+
```

Project A must have two permissions:

1. Storage Object Viewer — read the encrypted file.
2. Cloud KMS CryptoKey Decrypter — decrypt the file.

KMS does not replace IAM. IAM authorises access, while KMS performs cryptographic operations.

This is application-level encryption, not Cloud Storage CMEK.

---

# 2. Prerequisites

You need:

- A Google Cloud account
- An active billing account
- Permission to create projects and service accounts
- Permission to configure IAM
- Google Cloud Shell

Open:

https://console.cloud.google.com/

Activate Cloud Shell using the terminal icon.

All commands below run inside Cloud Shell using Bash.

Do not use real production secrets in this lab.

---

# 3. Define Environment Variables

Run:

```bash
export REGION="europe-west2"

export SUFFIX="$(date +%s)"

export PROJECT_A="kms-lab-a-${SUFFIX}"
export PROJECT_B="kms-lab-b-${SUFFIX}"

export BUCKET="${PROJECT_B}-encrypted-data"

export KEY_RING="shared-secrets"
export KEY_NAME="secret-key"

export RUN_SERVICE="kms-reader"

export RUNTIME_SA_NAME="project-a-reader"
export BUILD_SA_NAME="project-a-builder"

export RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_A}.iam.gserviceaccount.com"

export BUILD_SA="${BUILD_SA_NAME}@${PROJECT_A}.iam.gserviceaccount.com"

export OPERATOR_EMAIL="$(gcloud config get-value account)"
```

Verify:

```bash
echo "$PROJECT_A"
echo "$PROJECT_B"
echo "$BUCKET"
echo "$RUNTIME_SA"
echo "$BUILD_SA"
```

The suffix makes the project IDs more likely to be globally unique.

If using existing projects, replace `PROJECT_A` and `PROJECT_B` with their existing IDs and skip the project creation commands.

Keep these variables available throughout the lab.

---

# 4. Create Project A and Project B

## Project A

```bash
gcloud projects create "$PROJECT_A" \
  --name="KMS Lab Consumer"
```

## Project B

```bash
gcloud projects create "$PROJECT_B" \
  --name="KMS Lab Owner"
```

List projects:

```bash
gcloud projects list
```

## Configure Billing

Find your billing account:

```bash
gcloud billing accounts list
```

Set the billing account ID:

```bash
export BILLING_ACCOUNT="YOUR_BILLING_ACCOUNT_ID"
```

Link Project A:

```bash
gcloud billing projects link "$PROJECT_A" \
  --billing-account="$BILLING_ACCOUNT"
```

Link Project B:

```bash
gcloud billing projects link "$PROJECT_B" \
  --billing-account="$BILLING_ACCOUNT"
```

Verify:

```bash
gcloud billing projects describe "$PROJECT_A"

gcloud billing projects describe "$PROJECT_B"
```

Project creation and billing linking require appropriate account permissions.

---

# 5. Enable Required APIs

## Project A

Enable Cloud Run, Cloud Build, IAM, KMS and Artifact Registry:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  cloudkms.googleapis.com \
  --project="$PROJECT_A"
```

## Project B

```bash
gcloud services enable \
  cloudkms.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_B"
```

Verify:

```bash
gcloud services list \
  --enabled \
  --project="$PROJECT_A"

gcloud services list \
  --enabled \
  --project="$PROJECT_B"
```

---

# 6. Create Service Accounts in Project A

We need two service accounts.

## 6.1 Runtime Service Account

This is the identity Cloud Run will use when accessing Project B.

Create:

```bash
gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
  --project="$PROJECT_A" \
  --display-name="Project A KMS Reader" \
  --description="Reads encrypted data from Project B"
```

The identity will look like:

```text
project-a-reader@kms-lab-a-123456.iam.gserviceaccount.com
```

## 6.2 Build Service Account

This account builds the Python application during deployment.

```bash
gcloud iam service-accounts create "$BUILD_SA_NAME" \
  --project="$PROJECT_A" \
  --display-name="Project A Cloud Run Builder"
```

Grant the Cloud Run Builder role:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_A" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/run.builder"
```

## 6.3 Allow Your Account to Deploy with the Runtime Identity

```bash
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project="$PROJECT_A" \
  --member="user:${OPERATOR_EMAIL}" \
  --role="roles/iam.serviceAccountUser"
```

Your operator also needs appropriate Cloud Run deployment permissions.

If they are not already provided, an IAM administrator can grant:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_A" \
  --member="user:${OPERATOR_EMAIL}" \
  --role="roles/run.sourceDeveloper"

gcloud projects add-iam-policy-binding "$PROJECT_A" \
  --member="user:${OPERATOR_EMAIL}" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

Only grant these permissions when required.

## 6.4 Verify Service Accounts

```bash
gcloud iam service-accounts list \
  --project="$PROJECT_A"
```

Expected:

```text
project-a-reader@PROJECT_A.iam.gserviceaccount.com

project-a-builder@PROJECT_A.iam.gserviceaccount.com
```

IMPORTANT:

Do not create or download service account JSON keys.

Cloud Run uses its attached service account automatically.

---

# 7. Create KMS Key in Project B

## 7.1 Create Key Ring

```bash
gcloud kms keyrings create "$KEY_RING" \
  --project="$PROJECT_B" \
  --location="$REGION"
```

## 7.2 Create Encryption Key

```bash
gcloud kms keys create "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --purpose="encryption" \
  --protection-level="software"
```

This creates a symmetric encryption key.

## 7.3 Verify the Key

```bash
gcloud kms keys describe "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING"
```

## 7.4 Store the KMS Resource Name

```bash
export KMS_KEY="projects/${PROJECT_B}/locations/${REGION}/keyRings/${KEY_RING}/cryptoKeys/${KEY_NAME}"

echo "$KMS_KEY"
```

The full resource name will be used by the application.

## 7.5 Grant Your User Encryption Permission

Your Cloud Shell identity needs permission to encrypt the test data.

```bash
gcloud kms keys add-iam-policy-binding "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --member="user:${OPERATOR_EMAIL}" \
  --role="roles/cloudkms.cryptoKeyEncrypter"
```

This grants encryption permission on the specific key.

---

# 8. Create Cloud Storage in Project B

Create a bucket:

```bash
gcloud storage buckets create "gs://${BUCKET}" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --uniform-bucket-level-access \
  --public-access-prevention
```

Verify:

```bash
gcloud storage buckets describe "gs://${BUCKET}"
```

The bucket will contain the encrypted data.

We are not using Cloud Storage-managed encryption with CMEK in this example.

Instead, we encrypt the data explicitly through KMS before uploading it.

---

# 9. Create and Encrypt Sample Data

## 9.1 Create Working Directory

```bash
mkdir -p "$HOME/kms-cross-project-lab"

cd "$HOME/kms-cross-project-lab"
```

## 9.2 Create JSON File

```bash
cat > secret.json <<'JSON'
{
  "customer": "Acme Ltd",
  "contract": "CONFIDENTIAL-123"
}
JSON
```

Verify:

```bash
cat secret.json
```

## 9.3 Encrypt Using Project B's KMS Key

```bash
gcloud kms encrypt \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --key="$KEY_NAME" \
  --plaintext-file="secret.json" \
  --ciphertext-file="secret.json.enc"
```

The generated `secret.json.enc` contains ciphertext.

This direct KMS encryption approach supports small payloads, up to 64 KiB of plaintext.

For larger files, use envelope encryption.

## 9.4 Upload Encrypted Data

```bash
gcloud storage cp \
  secret.json.enc \
  "gs://${BUCKET}/secret.json.enc"
```

Verify:

```bash
gcloud storage ls "gs://${BUCKET}/"
```

Expected:

```text
gs://YOUR_BUCKET/secret.json.enc
```

## 9.5 Delete Local Copies

After verifying the upload:

```bash
rm -f secret.json secret.json.enc
```

The encrypted file remains in Project B.

---

# 10. Grant Cross-Project IAM Permissions

We now configure Project B to trust the specific runtime service account in Project A.

No project-wide Owner or Editor access is required.

## 10.1 Grant Cloud Storage Read Access

```bash
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectViewer"
```

This permits the runtime identity to read objects from this bucket.

## 10.2 Grant KMS Decryption Access

```bash
gcloud kms keys add-iam-policy-binding "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudkms.cryptoKeyDecrypter"
```

The runtime identity now has permission to use Project B's KMS key for decryption.

It does not have permission to administer the key.

## 10.3 Verify Bucket IAM

```bash
gcloud storage buckets get-iam-policy "gs://${BUCKET}" \
  --format="yaml(bindings)"
```

## 10.4 Verify KMS IAM

```bash
gcloud kms keys get-iam-policy "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --format="yaml(bindings)"
```

Expected permissions:

| Project | Identity          | Resource            | Permission            |
| ------- | ----------------- | ------------------- | --------------------- |
| A       | project-a-reader  | B's bucket          | Storage Object Viewer |
| A       | project-a-reader  | B's KMS key         | CryptoKey Decrypter   |
| A       | project-a-builder | A's build resources | Cloud Run Builder     |

Important:

Cross-project IAM works because Project B grants roles directly to a service account belonging to Project A.

Project A does not need a second service account in Project B.

---

# 11. Build Python Application in Project A

We will create a small Flask API.

Endpoints:

- `GET /` — health check
- `GET /read-secret` — download ciphertext and decrypt it

The API will return sample plaintext for testing only.

Do not expose real credentials or customer secrets through an endpoint like this.

## 11.1 Create main.py

```bash
cd "$HOME/kms-cross-project-lab"

cat > main.py <<'PY'
import os

from flask import Flask, jsonify
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import kms, storage

app = Flask(__name__)

BUCKET = os.environ["BUCKET"]
PROJECT_B = os.environ["PROJECT_B"]
REGION = os.environ["REGION"]
KEY_RING = os.environ["KEY_RING"]
KEY_NAME = os.environ["KEY_NAME"]

storage_client = storage.Client()
kms_client = kms.KeyManagementServiceClient()


@app.get("/")
def health():
    return jsonify(
        status="running",
        service="kms-reader"
    )


@app.get("/read-secret")
def read_secret():
    """
    Demo only: read and decrypt data from Project B.
    The endpoint must not return real production secrets.
    """
    try:
        # Download encrypted object
        blob = storage_client.bucket(BUCKET).blob(
            "secret.json.enc"
        )

        ciphertext = blob.download_as_bytes()

        # Reference Project B's KMS key
        key_resource = (
            f"projects/{PROJECT_B}"
            f"/locations/{REGION}"
            f"/keyRings/{KEY_RING}"
            f"/cryptoKeys/{KEY_NAME}"
        )

        # Ask Cloud KMS to decrypt
        result = kms_client.decrypt(
            request={
                "name": key_resource,
                "ciphertext": ciphertext
            }
        )

        # Demo response
        return app.response_class(
            result.plaintext,
            mimetype="application/json"
        )

    except GoogleAPICallError:
        app.logger.exception("Storage/KMS call failed")

        return jsonify(
            error="Storage or KMS request failed"
        ), 502


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080"))
    )
PY
```

## 11.2 Create requirements.txt

```bash
cat > requirements.txt <<'REQ'
Flask>=3.1,<4
gunicorn>=23,<24
google-cloud-storage>=3,<4
google-cloud-kms>=3,<4
REQ
```

## 11.3 Create Procfile

```bash
cat > Procfile <<'PROC'
web: gunicorn --bind :$PORT --workers 1 --threads 4 main:app
PROC
```

## 11.4 Create .gcloudignore

```bash
cat > .gcloudignore <<'IGNORE'
.git
.venv
__pycache__
*.pyc
secret.json
secret.json.enc
IGNORE
```

## 11.5 Validate Python

```bash
python3 -m py_compile main.py
```

Verify the directory:

```bash
ls -la
```

Expected application files:

```text
main.py
requirements.txt
Procfile
.gcloudignore
```

The application uses Application Default Credentials automatically supplied by Cloud Run.

No embedded credentials or JSON service account keys are needed.

---

# 12. Deploy Cloud Run Service

Deploy in Project A using the runtime service account.

```bash
cd "$HOME/kms-cross-project-lab"

gcloud run deploy "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --source=. \
  --build-service-account="projects/${PROJECT_A}/serviceAccounts/${BUILD_SA}" \
  --service-account="$RUNTIME_SA" \
  --set-env-vars="PROJECT_B=${PROJECT_B},BUCKET=${BUCKET},REGION=${REGION},KEY_RING=${KEY_RING},KEY_NAME=${KEY_NAME}" \
  --no-allow-unauthenticated \
  --quiet
```

Cloud Run will:

1. Build the Python application.
2. Store the image in Artifact Registry.
3. Create the Cloud Run service.
4. Attach the runtime service account.
5. Configure the environment variables.
6. Require authenticated callers.

Source deployment may prompt for a repository or additional service activation.

If IAM errors occur, verify the build and deployer permissions.

## 12.1 Get Service URL

```bash
export SERVICE_URL="$(gcloud run services describe "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$SERVICE_URL"
```

## 12.2 Grant Your User Cloud Run Invoker

```bash
gcloud run services add-iam-policy-binding "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --member="user:${OPERATOR_EMAIL}" \
  --role="roles/run.invoker"
```

---

# 13. Test the Application

Use Cloud Run's local authenticated proxy.

## Terminal 1

```bash
gcloud run services proxy "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --port=8080
```

Leave this terminal running.

## Terminal 2

Open another Cloud Shell terminal.

Test the health endpoint:

```bash
curl -i http://localhost:8080/
```

Expected:

```json
{
  "status": "running",
  "service": "kms-reader"
}
```

Test the encrypted file:

```bash
curl -i http://localhost:8080/read-secret
```

Expected JSON body:

```json
{
  "customer": "Acme Ltd",
  "contract": "CONFIDENTIAL-123"
}
```

If successful, you have demonstrated:

- Cloud Run workload identity in Project A
- Cross-project Cloud Storage access
- Cross-project KMS decryption
- IAM-controlled cryptographic access
- A working Python service

---

# 14. Negative Security Test — Revoke KMS Access

Now test what happens when Project B revokes Project A's decryption permission.

## 14.1 Remove Decrypter Role

Run from the original Cloud Shell session:

```bash
gcloud kms keys remove-iam-policy-binding "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudkms.cryptoKeyDecrypter"
```

## 14.2 Retest API

From the second terminal:

```bash
curl -i http://localhost:8080/read-secret
```

After IAM propagation, expect an error such as:

```json
{
  "error": "Storage or KMS request failed"
}
```

HTTP status should be 502 from this sample application.

Inspect Cloud Run logs for a KMS permission error.

The important observation:

Project A can still download encrypted data from Cloud Storage but cannot decrypt it through Project B's KMS key.

## 14.3 Inspect Logs

```bash
gcloud run services logs read "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --limit=30
```

Look for:

```text
PERMISSION_DENIED
```

## 14.4 Restore KMS Permission

```bash
gcloud kms keys add-iam-policy-binding "$KEY_NAME" \
  --project="$PROJECT_B" \
  --location="$REGION" \
  --keyring="$KEY_RING" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudkms.cryptoKeyDecrypter"
```

After permission propagation, retest:

```bash
curl -i http://localhost:8080/read-secret
```

The sample data should be returned again.

Note: revoking KMS permission does not erase plaintext already obtained or cached by a service.

---

# 15. Optional Test — Revoke Storage Access

Remove Storage Object Viewer:

```bash
gcloud storage buckets remove-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectViewer"
```

Retest:

```bash
curl -i http://localhost:8080/read-secret
```

The request should fail because Project A can no longer retrieve the encrypted file.

Restore:

```bash
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectViewer"
```

This demonstrates that both Storage IAM and KMS IAM are necessary.

---

# 16. Troubleshooting

## Project creation fails

Possible causes:

- Missing Resource Manager permissions
- Organisation policy
- Project quota

Use existing projects or request administrator permission.

## Billing fails

Verify:

```bash
gcloud billing accounts list
```

You need permission to link the billing account to the projects.

## KMS encryption fails

Check the user has:

```text
roles/cloudkms.cryptoKeyEncrypter
```

on the encryption key.

## Cloud Run deployment fails

Check:

```bash
gcloud iam service-accounts list \
  --project="$PROJECT_A"
```

Verify the build service account has:

```text
roles/run.builder
```

Verify the deployer has permission to act as the runtime service account.

## Cloud Run returns HTTP 403

Ensure your calling identity has:

```text
roles/run.invoker
```

Use the authenticated Cloud Run proxy rather than opening the service publicly.

## Python API returns HTTP 502

Check:

- Bucket name
- Project B ID
- Encryption key resource name
- Storage IAM
- KMS IAM

Read logs:

```bash
gcloud run services logs read "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --limit=50
```

---

# 17. Cleanup

Cloud resources can incur charges.

Only delete lab resources that you created.

## Delete Cloud Run

```bash
gcloud run services delete "$RUN_SERVICE" \
  --project="$PROJECT_A" \
  --region="$REGION" \
  --quiet
```

## Delete Test Storage

```bash
gcloud storage rm \
  "gs://${BUCKET}/secret.json.enc"

gcloud storage buckets delete \
  "gs://${BUCKET}" \
  --quiet
```

## Delete Service Accounts

```bash
gcloud iam service-accounts delete "$RUNTIME_SA" \
  --project="$PROJECT_A" \
  --quiet

gcloud iam service-accounts delete "$BUILD_SA" \
  --project="$PROJECT_A" \
  --quiet
```

KMS key versions must be scheduled for destruction; deleting a Cloud Run service does not remove KMS keys.

The simplest complete cleanup for fully disposable lab environments is to delete both projects.

**WARNING: destructive commands — do not run against existing or shared projects.**

Review IDs:

```bash
echo "$PROJECT_A"
echo "$PROJECT_B"
```

For disposable lab projects only:

```bash
# Uncomment only after confirming both IDs.

# gcloud projects delete "$PROJECT_A"
# gcloud projects delete "$PROJECT_B"
```

---

# 18. What We Learned

The exercise demonstrates three separate security responsibilities.

## Workload Identity

Cloud Run uses a service account to identify the running workload.

No service-account private key needs to be stored in the application.

## IAM

IAM defines whether Project A can access resources owned by Project B.

Permissions can be granted at individual resource level.

## Cloud KMS

KMS manages encryption keys and performs encryption/decryption.

The application never receives the underlying KMS key material.

It receives plaintext from an authorised decryption operation.

## Cross-Project Security

Projects can remain isolated while explicitly granting selected identities access to individual resources.

This pattern supports separation of duties and centrally managed encryption keys.

---

# 19. Production Considerations

This sample is intentionally small.

For a real system:

1. Use least-privilege IAM bindings.
2. Protect Cloud Run with authenticated invocation.
3. Avoid returning decrypted credentials to API clients.
4. Enable appropriate KMS audit logging.
5. Consider VPC Service Controls for sensitive environments.
6. Use envelope encryption for large files.
7. Rotate keys according to your security policy.
8. Keep decrypted values in memory only as long as required.
9. Use Secret Manager for ordinary application secrets.
10. Avoid logging plaintext or credentials.

KMS is not an authentication mechanism for calling Project B's APIs.

For direct Cloud Run-to-Cloud Run access, use service-to-service authentication with OIDC identity tokens and Cloud Run IAM.

---

# 20. Instructions for Claude Code

The purpose of this Markdown file is to let Claude Code implement and validate the lab.

## Claude Code Tasks

Claude should:

1. Review the architecture and permissions.
2. Check the local GCP authentication context.
3. Validate project IDs and billing settings.
4. Validate all gcloud commands against the installed Google Cloud SDK.
5. Create the Python application files.
6. Run Python syntax checks.
7. Verify the service account and IAM design.
8. Prepare deployment commands.
9. Run deployments only with explicit user approval.
10. Validate the deployed Cloud Run endpoints.
11. Test permission revocation and restoration.
12. Document errors and resolutions.
13. Provide cleanup commands.

Do not automatically modify billing, create cloud resources, change IAM or delete projects without approval.

Never create or download JSON service account keys for this lab.

Never print production secrets or credentials into logs.

## Suggested Claude Code Prompt

Read `GCP_KMS_Cross_Project_Lab.md` completely.

I want to implement the Google Cloud KMS cross-project lab.

Treat the Markdown as the implementation specification.

Start by reviewing the architecture and validating all commands.

Create the necessary Python application files and verify their syntax.

Before making any changes to Google Cloud, show me the proposed actions and ask for approval.

Use dedicated service accounts and least-privilege IAM.

Do not create or download service account JSON keys.

Guide me through Project A and Project B setup, KMS configuration, encryption, Cloud Run deployment and security testing.

After deployment, help me verify the cross-project IAM permissions and demonstrate that revoking KMS access stops decryption.

Finally, prepare cleanup commands, but do not execute them without my approval.

---

# 21. Official Google Cloud Documentation

Cloud KMS:
https://cloud.google.com/kms/docs

Encrypt/decrypt:
https://cloud.google.com/kms/docs/encrypt-decrypt

KMS IAM:
https://cloud.google.com/kms/docs/iam

Cloud Run:
https://cloud.google.com/run/docs

Cloud Run Source Deployment:
https://cloud.google.com/run/docs/deploying-source-code

Cloud Storage IAM:
https://cloud.google.com/storage/docs/access-control/iam

Service Accounts:
https://cloud.google.com/iam/docs/service-account-overview

---

# End of Lab
