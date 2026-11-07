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