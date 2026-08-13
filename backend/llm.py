# Bedrock LLM 래퍼 (default 프로파일, claude-opus-5)
import json
import os
import re

import boto3

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-opus-5")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
PROFILE = os.environ.get("AWS_PROFILE", "default")

_client = None


def client():
    global _client
    if _client is None:
        # 로컬: named profile / EC2: instance role 등 기본 자격증명 체인
        if PROFILE in boto3.Session().available_profiles:
            sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
        else:
            sess = boto3.Session(region_name=REGION)
        _client = sess.client("bedrock-runtime")
    return _client


def chat(system, user, max_tokens=1500):
    r = client().converse(
        modelId=MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens},  # opus-5: temperature 미지원
    )
    # opus-5는 reasoning 블록이 섞여 옴 -> text 블록만 취합
    return "".join(b["text"] for b in r["output"]["message"]["content"] if "text" in b)


def chat_json(system, user, max_tokens=1500):
    """JSON 응답 강제 + 코드펜스 방어 파싱."""
    text = chat(system + "\n\n반드시 유효한 JSON만 출력하세요. 다른 텍스트 금지.", user, max_tokens)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0) if m else text)
