import json
import boto3
import base64
import logging
import os
from botocore.config import Config
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
bedrock_client = boto3.client(
    'bedrock-runtime',
    region_name='us-east-1',
    config=Config(read_timeout=600, connect_timeout=10)
)

S3_BUCKET     = os.environ["S3_BUCKET"]
BEDROCK_MODEL = "us.anthropic.claude-sonnet-4-6"

def parse_s3_uri(s3_uri):
    s3_uri = s3_uri.replace("s3://", "")
    parts  = s3_uri.split("/", 1)
    return parts[0], parts[1]

def read_from_s3(s3_path):
    if s3_path.startswith("s3://"):
        bucket, key = parse_s3_uri(s3_path)
    else:
        bucket = S3_BUCKET
        key    = s3_path
    logger.info(f"Reading from s3://{bucket}/{key}")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response['Body'].read()

def compare_documents(cur_b64, prev_b64, metadata):
    doc_id        = metadata.get('doc_id',        'N/A')
    doc_name      = metadata.get('doc_name',      'N/A')
    doc_version   = metadata.get('doc_version',   'N/A')
    prev_version  = metadata.get('prev_version',  'N/A')
    approved_by   = metadata.get('approved_by',   'N/A')
    approval_date = metadata.get('approval_date', 'N/A')
    today         = datetime.utcnow().strftime("%d-%b-%Y")

    comparison_prompt = f"""You are an expert GxP Document Analyst specializing in Veeva Vault Quality Management Systems and regulatory compliance (FDA, EMA, ISO 22716).

Document Information:
- Document ID:       {doc_id}
- Document Name:     {doc_name}
- Current Version:   {doc_version}
- Previous Version:  {prev_version}
- Approved By:       {approved_by}
- Approval Date:     {approval_date}
- Comparison Date:   {today}

The FIRST document provided is the PREVIOUS version.
The SECOND document provided is the CURRENT version.

═══════════════════════════════════════════════════════
INTERNAL STEP — DO THIS BEFORE WRITING ANY OUTPUT
═══════════════════════════════════════════════════════
1. Read BOTH documents completely from start to finish.
2. List every single change internally.
3. Number them sequentially: 1, 2, 3...
4. Count by category: Additions, Deletions, Modifications, Relocations.
5. VERIFY: Additions + Deletions + Modifications + Relocations = TOTAL.
6. The TOTAL must equal the last change number in Section 3.
7. Only start writing output AFTER this count is verified.
═══════════════════════════════════════════════════════
COMPARISON RULES
═══════════════════════════════════════════════════════
- Report ALL changes: Additions, Deletions, Modifications, Relocations
- DELETION: Any content in previous version missing from current = DELETIO
- MODIFICATION: Any content that changed wording, values, or meaning = MODIFICATION
- RELOCATION: Same content moved to different section = RELOCATION
- ADDITION: Any new content in current not in previous = ADDITION
- Risk: CRITICAL (regulatory/audit impact), SAFETY (personnel/process safety), PROCEDURAL (admin/workflow)
- IGNORE: font styles, page numbers, headers/footers, whitespace

═══════════════════════════════════════════════════════
OUTPUT FORMAT — FOLLOW THIS EXACTLY
═══════════════════════════════════════════════════════

# GxP Change Control Summary
## Document Comparison Report

---
### DOCUMENT IDENTIFICATION

| Field | Details |
|---|---|
| **Document ID** | {doc_id} |
| **Document Name** | {doc_name} |
| **Current Version** | {doc_version} |
| **Previous Version** | {prev_version} |
| **Approved By** | {approved_by} |
| **Approval Date** | {approval_date} |
| **Comparison Date** | {today} |

##  EXECUTIVE SUMMARY TABLE

| Change Category | Count | Risk Level |
|---|---|---|
| **Additions** | [count] | [CRITICAL / SAFETY / PROCEDURAL / N/A] |
| **Deletions** | [count] | [CRITICAL / SAFETY / PROCEDURAL / N/A] |
| **Modifications** | [count] | [CRITICAL / SAFETY / PROCEDURAL / N/A] |
| **Relocations** | [count] | [CRITICAL / SAFETY / PROCEDURAL / N/A] |
| **TOTAL CHANGES** | **[verified total]** | |

---

### 🔴 CRITICAL CHANGES

[Only include this section if there are CRITICAL changes]
---

**Change [N]**
| Field | Details |
|---|---|
| **Section** | [section number and full name] |
| **Change Type** | CRITICAL |
| **Modified Status** | [Added / Deleted / Modified / Relocated] |
| **Previous** | [exact previous text — use N/A if Addition] |
| **Current** | [exact current text — use N/A if Deletion] |
| **Impact** | [Specific action required: who must do what, what compliance requirement is affected, what risk exists if not actioned. Use **bold** for key phrases.] |

---

[Repeat for each CRITICAL change]

---

### 🟠 SAFETY CHANGES

[Only include this section if there are SAFETY changes]

---
**Change [N]**


| Field | Details |
|---|---|
| **Section** | [section number and full name] |
| **Change Type** | SAFETY |
| **Modified Status** | [Added / Deleted / Modified / Relocated] |
| **Previous** | [exact previous text — N/A if Addition] |
| **Current** | [exact current text — N/A if Deletion] |
| **Impact** | [Specific safety action required. Use **bold** for key risk phrases.] |

---

### 🟡 PROCEDURAL CHANGES

[Only include this section if there are PROCEDURAL changes]

---

**Change [N]**
| Field | Details |
|---|---|
| **Section** | [section number and full name] |
| **Change Type** | PROCEDURAL |
| **Modified Status** | [Added / Deleted / Modified / Relocated] |
| **Previous** | [exact previous text — N/A if Addition] |
| **Current** | [exact current text — N/A if Deletion] |
| **Impact** | [What must be updated: training materials, cross-references, checklists, etc.] |

---

### 🟢 ADDITIONS

[Only include if there are Additions]
---

**Change [N]**
| Field | Details |
|---|---|
| **Section** | [section number and full name] |
| **Change Type** | [CRITICAL / SAFETY / PROCEDURAL] |
| **Modified Status** | Added |
| **Previous** | N/A |
| **Current** | [exact new content added] |
| **Impact** | [What operators/QA must know about this addition] |

---
### 🔴 DELETIONS
[Only include if there are standalone Deletions not already covered above]
---
**Change [N]**
| Field | Details |
|---|---|
| **Section** | [section number and full name] |
| **Change Type** | [CRITICAL / SAFETY / PROCEDURAL] |
| **Modified Status** | Deleted |
| **Previous** | [exact deleted content] |
| **Current** | N/A |
| **Impact** | [Compliance or operational consequence of this deletion. Use **bold** for key flags.] |

---
*Report generated for GxP Change Control purposes. All changes must be reviewed and acknowledged by the document owner and relevant stakeholders before implementation. Training impact assessment and effectiveness checks are recommended for all CRITICAL and PROCEDURAL changes identified above.*

═══════════════════════════════════════════════════════
FINAL SELF-CHECK — DO NOT PRINT THIS IN OUTPUT
═══════════════════════════════════════════════════════
Before submitting verify:
[ ] TOTAL in Section 1 = last Change number in Section 3
[ ] Every change has a complete table (Section, Change Type, Modified Status, Previous, Current, Impact)
[ ] Previous = N/A only for Additions
[ ] Current = N/A only for Deletions
[ ] All sections reviewed appear in Section 4
[ ] Compliance flags are real GxP issues with recommended actions
[ ] No category header included if it has zero changes"""

    response = bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16000,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type":       "base64",
                            "media_type": "application/pdf",
                            "data":       prev_b64
                        },
                        "title": f"Previous Version {prev_version}"
                    },
                    {
                        "type": "document",
                        "source": {
                            "type":       "base64",
                            "media_type": "application/pdf",
                            "data":       cur_b64
                        },
                        "title": f"Current Version {doc_version}"
                    },
                    {
                        "type": "text",
                        "text": comparison_prompt
                    }
                ]
            }]
        })
    )

    result = json.loads(response['body'].read())
    for block in result['content']:
        if block.get('type') == 'text':
            return block['text']
    raise ValueError("No text block found in Claude response")


def parse_params(event):
    parameters = event.get("parameters", [])
    if parameters:
        return {p["name"]: p["value"] for p in parameters}
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        return {p["name"]: p["value"] for p in props}
    except (KeyError, TypeError):
        return {}

def build_response(event, body_dict, status_code=200):
    if event.get("function"):
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup"),
                "function":    event.get("function"),
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": json.dumps(body_dict)
                        }
                    }
                }
            }
        }
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup":    event.get("actionGroup"),
            "apiPath":        event.get("apiPath"),
            "httpMethod":     event.get("httpMethod"),
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body_dict)
                }
            }
        }
    }

def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")
    try:
        params = parse_params(event)

        current_pdf_path  = params.get("current_pdf_path")
        previous_pdf_path = params.get("previous_pdf_path")
        metadata_path     = params.get("metadata_path")

        logger.info(f"current_pdf_path:  {current_pdf_path}")
        logger.info(f"previous_pdf_path: {previous_pdf_path}")
        logger.info(f"metadata_path:     {metadata_path}")

        if not current_pdf_path or not previous_pdf_path or not metadata_path:
            raise ValueError("current_pdf_path, previous_pdf_path, metadata_path are required")

        metadata_bytes = read_from_s3(metadata_path)
        metadata       = json.loads(metadata_bytes)
        logger.info(f"Metadata: {metadata}")

        doc_id        = metadata.get("doc_id")
        doc_name      = metadata.get("doc_name")
        doc_version   = metadata.get("doc_version")
        prev_version  = metadata.get("prev_version")
        approved_by   = metadata.get("approved_by")
        approval_date = metadata.get("approval_date")

        logger.info("Reading current PDF from S3...")
        cur_bytes = read_from_s3(current_pdf_path)
        logger.info(f"Current PDF size: {len(cur_bytes)} bytes")

        logger.info("Reading previous PDF from S3...")
        prev_bytes = read_from_s3(previous_pdf_path)
        logger.info(f"Previous PDF size: {len(prev_bytes)} bytes")

        cur_b64  = base64.standard_b64encode(cur_bytes).decode("utf-8")
        prev_b64 = base64.standard_b64encode(prev_bytes).decode("utf-8")
        logger.info("Both PDFs converted to base64")

        logger.info("Calling Claude for GxP comparison...")
        summary = compare_documents(cur_b64, prev_b64, metadata)
        if isinstance(summary, bytes):
            summary = summary.decode('utf-8', errors='replace')
        else:
            summary = summary.encode('utf-8', errors='replace').decode('utf-8')
        logger.info(f"Summary generated: {len(summary)} characters")

        logger.info("Saving summary files to S3...")
        today = datetime.utcnow().strftime("%d-%b-%Y")

        summary_key = f"summaries/{doc_id}/summary.txt"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=summary_key,
            Body=summary.encode('utf-8', errors='replace'),
            ContentType='text/plain; charset=utf-8'
        )
        summary_s3_path = f"s3://{S3_BUCKET}/{summary_key}"
        logger.info(f"summary.txt saved: {summary_s3_path}")

        summary_json = {
            "doc_id":        doc_id,
            "doc_name":      doc_name,
            "doc_version":   doc_version,
            "prev_version":  prev_version,
            "approved_by":   approved_by,
            "approval_date": approval_date,
            "generated_at":  today
        }
        json_key = f"summaries/{doc_id}/summary.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=json_key,
            Body=json.dumps(summary_json, indent=2).encode('utf-8'),
            ContentType='application/json'
        )
        summary_json_path = f"s3://{S3_BUCKET}/{json_key}"
        logger.info(f"summary.json saved: {summary_json_path}")

        return build_response(event, {
            "status":            "success",
            "doc_id":            doc_id,
            "doc_name":          doc_name,
            "doc_version":       doc_version,
            "prev_version":      prev_version,
            "approved_by":       approved_by,
            "approval_date":     approval_date,
            "summary_s3_path":   summary_s3_path,
            "summary_json_path": summary_json_path
        })

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return build_response(event, {"error": str(e)}, status_code=500)
