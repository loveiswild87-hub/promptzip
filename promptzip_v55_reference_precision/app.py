import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
APP_VERSION = "V55 Reference Precision"
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "").strip()

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)
LEADS_FILE = EXPORT_DIR / "payment_interest_leads.csv"

CRAFT_HINTS = [
    "만들고", "만들어", "기획", "설계", "구성", "추천", "아이디어", "사이트", "서비스",
    "판매", "랜딩", "첫 버전", "버전", "계획", "전략", "정리", "작성", "개발", "플랫폼"
]
ZIP_HINTS = [
    "압축", "줄여", "짧게", "간결", "토큰", "비용", "절감", "요약", "중복 제거", "프롬프트 줄"
]

PRODUCT_HINTS = {
    "영어 자료 판매 사이트": ["영어", "자료", "판매", "사이트"],
    "교육 콘텐츠 플랫폼": ["교육", "콘텐츠", "플랫폼"],
    "단어 학습 사이트": ["단어", "어휘", "암기"],
    "수업 자료 제작": ["수업", "자료", "제작"],
    "AI 프롬프트 서비스": ["프롬프트", "AI", "질문"],
}

DEFAULT_OUTPUT_SECTIONS = [
    "핵심 콘셉트",
    "메인 페이지 구성",
    "대상별 카테고리 구조",
    "상품/기능 구성",
    "무료 체험 또는 샘플 제공 방식",
    "가격 구조",
    "사용자 이용 흐름",
    "관리자에게 필요한 기능",
    "첫 출시 버전과 추후 추가 기능 구분",
    "구매 또는 사용을 유도하는 문구 예시",
]

ENGINE_PROFILES = {
    "auto": {
        "label": "자동",
        "guide": "특정 AI에 과하게 맞추지 말고 GPT, Claude, Gemini, Genspark AI 어디에 붙여넣어도 이해되는 범용 구조로 작성한다.",
    },
    "gpt": {
        "label": "GPT",
        "guide": "GPT에서 바로 실행하기 좋게 역할, 목표, 조건, 출력 형식을 선명하게 분리하고 불필요한 설명은 줄인다.",
    },
    "claude": {
        "label": "Claude",
        "guide": "Claude에서 긴 맥락을 안정적으로 처리할 수 있도록 배경, 세부 조건, 평가 기준을 자연어로 충분히 풀어 쓴다.",
    },
    "gemini": {
        "label": "Gemini",
        "guide": "Gemini에서 표, 단계별 정리, 비교 구조가 잘 드러나도록 요구사항을 명확한 섹션으로 나눈다.",
    },
    "genspark": {
        "label": "Genspark AI",
        "guide": "Genspark AI에 붙여넣기 좋게 리서치 목표, 확인할 자료 범주, 비교 기준, 최종 산출물을 분리한다. 정보가 불확실하면 가정과 추가 확인 사항을 따로 표시하게 한다.",
    },
}


def normalize_engine(engine: str) -> str:
    engine = (engine or "auto").lower().strip()
    return engine if engine in ENGINE_PROFILES else "auto"


def engine_guide(engine: str) -> Tuple[str, str]:
    engine = normalize_engine(engine)
    profile = ENGINE_PROFILES[engine]
    return profile["label"], profile["guide"]


def detect_output_language(text: str) -> str:
    """Keep the generated prompt in the user's main input language."""
    text = text or ""
    korean_chars = len(re.findall(r"[가-힣]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if korean_chars >= max(3, latin_chars * 0.35):
        return "한국어"
    if latin_chars > korean_chars * 2:
        return "English"
    return "입력 언어와 같은 언어"


def engine_specific_block(engine: str, mode: str) -> str:
    """Return a stronger AI-specific prompt style guide."""
    engine = normalize_engine(engine)
    mode_label = "질문 고도화" if mode == "craft" else "의미 보존 압축"

    if engine == "gpt":
        return f"""GPT 최적화 지침:
- 목적을 첫 문장에 놓고, 역할 → 작업 → 조건 → 출력 형식 순서로 정리한다.
- 지시문은 짧고 실행 가능한 명령형으로 쓴다.
- 애매한 표현은 구체적인 산출물 조건으로 바꾼다.
- 답변이 길어질 수 있는 요청은 표, 목록, 단계 중 하나를 명확히 지정한다.
- {mode_label} 과정에서 불필요한 배경 설명은 줄이되, 핵심 제한 조건은 남긴다."""

    if engine == "claude":
        return f"""Claude 최적화 지침:
- 사용자의 의도와 배경을 충분히 설명해 맥락을 잃지 않게 한다.
- 우선순위, 예외 조건, 품질 기준을 자연어로 분명히 적는다.
- 복잡한 요청은 섹션별로 나누되, 각 섹션의 목적을 함께 설명한다.
- 답변 전 조건 충족 여부를 점검하게 하되, 내부 사고 과정을 길게 노출하도록 요구하지 않는다.
- {mode_label} 과정에서 섬세한 문체와 판단 기준을 보존한다."""

    if engine == "gemini":
        return f"""Gemini 최적화 지침:
- 큰 그림 → 세부 항목 → 비교/표 → 실행 순서로 정리한다.
- 여러 대안이 있을 때는 비교 기준을 명시하고 표 형태를 우선 요구한다.
- 시각적 정리, 단계별 흐름, 요약 박스가 잘 나오도록 출력 구조를 분명히 한다.
- 자료형이 확장될 수 있도록 텍스트, 표, 체크리스트를 구분한다.
- {mode_label} 과정에서 한눈에 읽히는 정보 구조를 우선한다."""

    if engine == "genspark":
        return f"""Genspark AI 최적화 지침:
- 리서치 목표, 조사 범위, 비교 기준, 검증 기준을 먼저 제시한다.
- 최신성 확인이 필요한 항목은 따로 표시하고, 근거가 약한 내용은 가정/추가 확인 사항으로 분리하게 한다.
- 경쟁 서비스, 가격, 기능, 사용자 니즈처럼 조사 가능한 항목은 표로 비교하게 한다.
- 결과는 요약 → 근거 기반 비교 → 실행 제안 → 다음 확인 질문 순서로 정리하게 한다.
- {mode_label} 과정에서 검색/조사형 답변에 필요한 기준을 명확히 남긴다."""

    return f"""범용 최적화 지침:
- GPT, Claude, Gemini, Genspark AI 어디에 붙여넣어도 이해되도록 역할, 목표, 조건, 출력 형식을 분리한다.
- 입력 의도와 핵심 조건을 유지하고, 불필요한 반복과 애매한 표현을 제거한다.
- 표와 단계별 설명을 적절히 섞어 바로 실행 가능한 질문으로 만든다.
- {mode_label} 과정에서 사용자가 원하는 결과물의 형태가 선명하게 보이게 한다."""


def clean_text(text: str) -> str:
    text = (text or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def contains_any(text: str, hints: List[str]) -> bool:
    lowered = text.lower()
    return any(h.lower() in lowered for h in hints)


def detect_topic(text: str) -> str:
    for topic, hints in PRODUCT_HINTS.items():
        if all(h in text for h in hints[:3]):
            return topic
    if "영어" in text and "사이트" in text:
        return "영어 학습/자료 사이트"
    if "프롬프트" in text:
        return "AI 프롬프트 서비스"
    if "수능" in text or "고등" in text or "중학" in text:
        return "영어 교육 자료 서비스"
    return "사용자가 입력한 아이디어"


def extract_keywords(text: str) -> List[str]:
    separators = r"[,/|·•\n]+"
    parts = re.split(separators, text)
    keywords: List[str] = []
    for part in parts:
        part = part.strip(" .。!！?？-–—")
        if not part:
            continue
        if len(part) > 40:
            # Split long Korean sentences lightly by common endings.
            small = re.split(r"(?<=[.!?。])\s+|그리고|또는|및", part)
            for s in small:
                s = s.strip(" .。!！?？-–—")
                if 2 <= len(s) <= 40:
                    keywords.append(s)
        else:
            keywords.append(part)
    seen = set()
    result = []
    for kw in keywords:
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            result.append(kw)
    return result[:14]


def detect_audience(text: str) -> List[str]:
    audience = []
    if "중학" in text or "중학생" in text or "중등" in text:
        audience.append("중학생")
    if "고등" in text or "고등학생" in text or "고1" in text or "고2" in text or "고3" in text:
        audience.append("고등학생")
    if "수능" in text or "수험생" in text:
        audience.append("수능 수험생")
    if not audience:
        audience = ["일반 사용자", "초보 사용자", "해당 분야에 관심 있는 사용자"]
    return audience


def infer_materials(text: str) -> List[str]:
    materials = []
    candidates = [
        ("단어장", ["단어", "어휘"]),
        ("어법 문제", ["어법", "문법"]),
        ("독해 지문 분석", ["독해", "지문", "분석"]),
        ("빈칸 추론", ["빈칸"]),
        ("순서 배열", ["순서"]),
        ("문장 삽입", ["삽입"]),
        ("서술형 문제", ["서술형"]),
        ("변형문제", ["변형"]),
        ("모의고사형 세트", ["모의고사", "동형"]),
    ]
    for name, hints in candidates:
        if any(h in text for h in hints):
            materials.append(name)
    if "영어" in text and not materials:
        materials = ["단어장", "어법 문제", "독해 지문 분석", "빈칸/순서/삽입 유형", "서술형 문제", "변형문제", "모의고사형 세트"]
    return materials


def detect_mode(text: str, requested_mode: str) -> Tuple[str, str]:
    requested_mode = (requested_mode or "auto").lower()
    if requested_mode in {"craft", "zip"}:
        return requested_mode, "사용자가 직접 선택한 모드입니다."

    has_craft = contains_any(text, CRAFT_HINTS)
    has_zip = contains_any(text, ZIP_HINTS)
    if has_craft and not has_zip:
        return "craft", "입력이 새로운 결과물을 만들거나 기획하려는 요청이라 PromptCraft가 적합합니다."
    if has_zip and not has_craft:
        return "zip", "입력이 이미 있는 프롬프트를 줄이려는 요청이라 PromptZip이 적합합니다."
    if len(text) < 260:
        return "craft", "짧은 아이디어/키워드형 입력은 압축보다 질문 고도화가 적합합니다."
    return "zip", "긴 설명형 입력이라 우선 PromptZip으로 압축합니다."


def detect_intent_detail(text: str) -> Dict[str, object]:
    """Infer the user's likely task type so Craft can produce a more delicate prompt."""
    t = text or ""
    task_type = "일반 기획/작성 요청"
    if any(k in t for k in ["사이트", "랜딩", "페이지", "플랫폼", "서비스"]):
        task_type = "웹사이트/서비스 기획"
    elif any(k in t for k in ["수업", "학습지", "문제", "지문", "영어", "수능", "내신"]):
        task_type = "교육 콘텐츠 제작"
    elif any(k in t for k in ["마케팅", "광고", "브랜딩", "고객", "전환"]):
        task_type = "마케팅/브랜딩 기획"
    elif any(k in t for k in ["조사", "리서치", "비교", "시장", "경쟁"]):
        task_type = "리서치/비교 분석"

    tone = "명확하고 실무적인 톤"
    if any(k in t for k in ["예쁘게", "디자인", "프리미엄", "깔끔", "세련"]):
        tone = "세련되고 프리미엄한 톤"
    elif any(k in t for k in ["쉽게", "초보", "누구라도", "이해"]):
        tone = "쉽고 친절한 톤"
    elif any(k in t for k in ["수능", "고3", "내신", "모의고사"]):
        tone = "교육 전문가의 정확한 톤"

    depth = "첫 출시 가능한 MVP 수준"
    if any(k in t for k in ["구체", "자세", "완벽", "정교", "섬세"]):
        depth = "구체적이고 실행 가능한 설계 수준"
    if any(k in t for k in ["첫 버전", "MVP", "간단", "초기"]):
        depth = "첫 출시 가능한 MVP 수준"

    return {"task_type": task_type, "tone": tone, "depth": depth}


def build_quality_checklist(engine: str, topic: str) -> List[str]:
    engine = normalize_engine(engine)
    base = [
        "원래 입력의 핵심 목적이 빠지지 않았는가?",
        "대상, 조건, 출력 형식이 분리되어 있는가?",
        "AI가 바로 실행할 수 있는 명령문인가?",
        "결과가 너무 일반적이거나 추상적이지 않은가?",
    ]
    if "교육" in topic or "영어" in topic or "수능" in topic:
        base.extend([
            "학습 대상의 수준과 자료 유형이 구분되어 있는가?",
            "실제 수업/판매 자료로 전환 가능한 구조인가?",
        ])
    if engine == "genspark":
        base.append("조사 범위, 비교 기준, 최신성 확인 조건이 포함되어 있는가?")
    if engine == "gemini":
        base.append("표와 단계별 구조가 잘 드러나도록 요청했는가?")
    if engine == "claude":
        base.append("맥락과 품질 기준이 충분히 설명되어 있는가?")
    if engine == "gpt":
        base.append("역할·목표·조건·출력 형식이 간결하게 분리되어 있는가?")
    return base[:7]


def craft_prompt(text: str, target_engine: str = "auto") -> Dict[str, object]:
    engine_key = normalize_engine(target_engine)
    engine_label, engine_instruction = engine_guide(engine_key)
    output_language = detect_output_language(text)
    engine_block = engine_specific_block(engine_key, "craft")
    topic = detect_topic(text)
    audience = detect_audience(text)
    keywords = extract_keywords(text)
    materials = infer_materials(text)
    intent = detect_intent_detail(text)
    quality_items = build_quality_checklist(engine_key, topic)

    target_line = ", ".join(audience)
    materials_block = ""
    if materials:
        materials_block = "\n- 자료/상품 예시: " + ", ".join(materials)

    keyword_block = "\n".join([f"- {kw}" for kw in keywords]) if keywords else f"- {text}"

    if engine_key == "genspark":
        output_sections = [
            "리서치 목표와 핵심 질문",
            "조사 범위와 제외 범위",
            "중학 / 고등 / 수능 대상별 사용자 니즈",
            "경쟁 서비스 또는 대체재 비교표",
            "판매 가능한 영어 자료 상품군과 차별화 포인트",
            "가격대, 무료 샘플, 유료 전환 전략",
            "근거가 확실한 내용과 추가 확인이 필요한 내용 구분",
            "첫 출시 MVP 구성",
            "랜딩페이지 핵심 문구",
            "다음에 확인해야 할 질문 5개",
        ]
    elif engine_key == "gemini":
        output_sections = [
            "한눈에 보는 전체 구조표",
            "대상별 카테고리 맵",
            "상품 유형별 비교표",
            "사용자 이용 흐름",
            "무료/유료 상품 구성",
            "가격 구조",
            "첫 출시 기능과 이후 기능 비교",
            "메인 페이지 섹션 구성",
            "구매 전환 문구",
            "실행 체크리스트",
        ]
    elif engine_key == "claude":
        output_sections = [
            "서비스가 해결할 문제와 맥락",
            "사용자 페르소나와 구매 이유",
            "중학 / 고등 / 수능 카테고리 설계",
            "상품 구성과 자료 품질 기준",
            "무료 샘플과 유료 전환 흐름",
            "가격 정책의 논리",
            "고객이 헷갈릴 수 있는 지점과 해결책",
            "첫 버전에서 제외해야 할 기능",
            "랜딩페이지 설득 구조",
            "최종 실행 우선순위",
        ]
    else:
        output_sections = DEFAULT_OUTPUT_SECTIONS

    sections_block = "\n".join([f"{i}. {section}" for i, section in enumerate(output_sections, start=1)])
    checklist_block = "\n".join([f"- {item}" for item in quality_items])

    prompt = f"""역할: {intent['task_type']}를 설계하는 전문가이자, 실제 출시 가능한 구조로 정리하는 프롬프트 엔지니어.

목표: 사용자가 대충 적은 아이디어를 바탕으로 {topic}를 구체적인 실행안으로 설계한다. 단순한 아이디어 정리가 아니라, 실제 사용자가 이해하고 구매하거나 사용할 수 있는 구조까지 제안한다.

대상 AI: {engine_label}
작성 언어: {output_language}
권장 톤: {intent['tone']}
설계 깊이: {intent['depth']}
AI별 작성 지침: {engine_instruction}

{engine_block}

사용자의 원본 입력:
{keyword_block}

대상과 전제:
- 핵심 사용자: {target_line}
- 초보 사용자도 첫 화면에서 무엇을 얻을 수 있는지 바로 이해해야 한다.
- 사용자의 기존 강점이나 보유 자료가 있다면 상품/기능 구조에 자연스럽게 반영한다.{materials_block}

반드시 반영할 조건:
- 최종 답변은 {output_language}로 작성한다.
- 첫 버전에서 바로 구현 가능한 현실적인 구조를 우선한다.
- 대상이 여러 그룹이면 카테고리, 상품 설명, 구매 이유를 분리한다.
- 사용자가 사이트나 서비스에 들어오자마자 핵심 가치가 보이게 만든다.
- 무료 샘플, 유료 상품, 결제 후 제공 방식, 관리자가 확인해야 할 기능을 포함한다.
- 과장된 주장이나 실제 근거가 없는 고객사/파트너명은 넣지 않는다.
- 애매한 표현은 실제 화면 문구, 상품명, 버튼명, 섹션명처럼 실행 가능한 형태로 바꾼다.

출력 형식:
{sections_block}

품질 점검 기준:
{checklist_block}

마무리:
- 마지막에는 오늘 바로 해야 할 작업 5개를 우선순위 순서로 제시한다.
- 불확실한 부분은 추측하지 말고 “추가 확인 필요”로 표시한다."""

    return {
        "mode": "craft",
        "title": "PromptCraft 결과 — 대충 쓴 생각을 정교한 질문으로 변환",
        "result": prompt,
        "topic": topic,
        "target_label": engine_label,
        "quality": f"{engine_label}에 맞춰 언어, 톤, 출력 구조, 품질 점검 기준까지 반영한 프롬프트입니다.",
    }


def split_sentences(text: str) -> List[str]:
    chunks = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [c.strip() for c in chunks if c.strip()]


def zip_prompt(text: str, target_engine: str = "auto") -> Dict[str, object]:
    engine_key = normalize_engine(target_engine)
    engine_label, engine_instruction = engine_guide(engine_key)
    output_language = detect_output_language(text)
    engine_block = engine_specific_block(engine_key, "zip")
    intent = detect_intent_detail(text)
    sentences = split_sentences(text)

    compact_sentences = []
    seen = set()
    for sentence in sentences:
        key = re.sub(r"\W+", "", sentence.lower())[:90]
        if key and key not in seen:
            seen.add(key)
            compact_sentences.append(sentence)

    joined = " ".join(compact_sentences)
    replacements = [
        ("나는 ", ""), ("앞으로는 ", ""), ("가능하다면 ", ""), ("좀 ", ""),
        ("대충 ", ""), ("정말 ", ""), ("너무 ", ""), ("해줘", "한다"), ("해주세요", "한다"),
    ]
    for old, new in replacements:
        joined = joined.replace(old, new)
    joined = re.sub(r"\s+", " ", joined).strip()

    if contains_any(text, CRAFT_HINTS) and not contains_any(text, ZIP_HINTS) and len(text) < 500:
        crafted = craft_prompt(text, engine_key)["result"]
        return {
            "mode": "craft_recommended",
            "title": "압축보다 PromptCraft가 적합합니다",
            "result": crafted,
            "topic": detect_topic(text),
            "target_label": engine_label,
            "quality": f"이 입력은 이미 완성된 긴 프롬프트가 아니라 새 결과물을 만들려는 요청이므로 Craft로 전환했습니다. {engine_label}에 맞춘 구조입니다.",
        }

    result = f"""역할: 사용자의 요청을 간결하지만 정확하게 재구성하는 프롬프트 편집자.

목표: 아래 요청의 핵심 목적, 대상, 조건, 출력 형식을 유지하면서 불필요한 반복과 모호한 표현을 제거한다.

대상 AI: {engine_label}
작성 언어: {output_language}
권장 톤: {intent['tone']}
AI별 작성 지침: {engine_instruction}

{engine_block}

압축할 원본 요청:
{joined}

출력 조건:
- 최종 프롬프트는 {output_language}로 작성한다.
- 역할, 목표, 핵심 조건, 출력 형식을 짧게 분리한다.
- 원래 요청의 중요한 제한 조건은 삭제하지 않는다.
- 같은 의미의 반복 표현은 하나로 합친다.
- 실제 근거가 없는 주장, 고객사명, 과장 문구는 새로 만들지 않는다.
- 선택한 대상 AI의 장점에 맞는 구조를 유지한다."""

    if len(result) >= len(text) * 1.25 and len(text) > 180:
        result = joined

    return {
        "mode": "zip",
        "title": "PromptZip 결과 — 의미 보존 압축",
        "result": result,
        "topic": detect_topic(text),
        "target_label": engine_label,
        "quality": f"중복 표현을 줄이고 {engine_label}에서 사용하기 좋게 역할·목표·출력 조건 중심으로 재구성했습니다.",
    }


def build_metrics(original: str, result: str, mode: str) -> Dict[str, object]:
    original_len = len(original)
    result_len = len(result)
    if original_len == 0:
        ratio = 0
    else:
        ratio = round((1 - result_len / original_len) * 100, 1)
    return {
        "input_chars": original_len,
        "output_chars": result_len,
        "change_rate": ratio,
        "label": "압축률" if mode == "zip" else "고도화율",
    }


HTML = r'''
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PromptCraft | V55 Reference Precision</title>
  <meta name="description" content="대충 쓴 생각을 GPT, Claude, Gemini, Genspark AI가 이해하는 구조화된 프롬프트로 바꾸는 PromptCraft 중심 서비스입니다." />
  __GA_SCRIPT__
  <style>
    :root {
      --bg: #f7f9ff;
      --ink: #0f172a;
      --muted: #5e6b83;
      --soft: #edf2ff;
      --line: rgba(163, 178, 214, .34);
      --blue: #3267ff;
      --violet: #7357ff;
      --cyan: #48d8ff;
      --navy: #101a35;
      --card: rgba(255,255,255,.78);
      --shadow: 0 28px 80px rgba(54, 91, 185, .16);
      --radius: 30px;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", Arial, sans-serif;
      color: var(--ink);
      line-height: 1.65;
      overflow-x: hidden;
      background:
        radial-gradient(circle at 76% 12%, rgba(115,87,255,.20), transparent 32%),
        radial-gradient(circle at 94% 54%, rgba(72,216,255,.16), transparent 29%),
        linear-gradient(135deg, #ffffff 0%, #f6f9ff 47%, #eef3ff 100%);
    }
    a { color: inherit; text-decoration: none; }
    button, input, select, textarea { font: inherit; }
    .wrap { width: min(1280px, calc(100% - 44px)); margin: 0 auto; }

    .topbar {
      position: sticky; top: 0; z-index: 20;
      background: rgba(255,255,255,.80);
      backdrop-filter: blur(22px);
      border-bottom: 1px solid rgba(205,215,239,.65);
    }
    .nav { height: 74px; display: grid; grid-template-columns: 230px minmax(420px, 1fr) 250px; align-items: center; gap: 22px; }
    .logo { display: flex; align-items: center; gap: 12px; font-weight: 950; letter-spacing: -.045em; font-size: 22px; }
    .logoMark {
      width: 36px; height: 36px; border-radius: 13px;
      background: conic-gradient(from 210deg, var(--blue), var(--violet), var(--cyan), var(--blue));
      box-shadow: 0 14px 34px rgba(50,103,255,.30);
      position: relative;
    }
    .logoMark::after {
      content: "P"; position: absolute; inset: 0; display: grid; place-items: center;
      color: white; font-weight: 1000; font-size: 20px;
    }
    .navLinks { display: flex; align-items: center; justify-content:center; gap: clamp(18px, 2.2vw, 34px); color: #172036; font-weight: 850; font-size: 15px; white-space: nowrap; }
    .navRight { display: flex; align-items: center; justify-content:flex-end; gap: 18px; font-weight: 850; }
    .smallLogin { color: #111b34; }

    .btn {
      border: 0; border-radius: 16px; padding: 14px 20px; font-weight: 950; cursor: pointer;
      display: inline-flex; align-items: center; justify-content: center; gap: 10px;
      transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
      white-space: nowrap;
    }
    .btn:hover { transform: translateY(-2px); }
    .btnPrimary {
      color: #fff;
      background: linear-gradient(135deg, #3267ff 0%, #7657ff 100%);
      box-shadow: 0 18px 34px rgba(50,103,255,.30);
    }
    .btnSoft {
      color: var(--navy); background: rgba(255,255,255,.72); border: 1px solid rgba(173,187,222,.55);
      box-shadow: 0 12px 30px rgba(37,56,114,.06);
    }

    .hero {
      position: relative; min-height: 820px; padding: 28px 0 24px;
      isolation: isolate;
    }
    .heroShell {
      position: relative;
      background: linear-gradient(135deg, rgba(255,255,255,.92) 0%, rgba(245,248,255,.96) 43%, rgba(239,243,255,.98) 100%);
      border: 1px solid rgba(205,215,239,.88);
      border-radius: 38px;
      box-shadow: 0 36px 90px rgba(54, 91, 185, .14);
      overflow: hidden;
      padding: 46px 30px 34px;
    }
    .hero::before {
      content: ""; position: absolute; inset: 0; z-index: -3;
      background-image:
        linear-gradient(rgba(45,70,130,.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(45,70,130,.05) 1px, transparent 1px);
      background-size: 78px 78px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,.7), transparent 78%);
    }
    .heroGlow {
      position: absolute; pointer-events: none; z-index: -1;
      filter: blur(.1px);
    }
    .orb1 { width: 80px; height: 80px; left: 47%; top: 95px; border-radius: 50%; background: radial-gradient(circle at 30% 25%, #fff, #7bdfff 30%, #7958ff 74%); opacity: .70; animation: float 6s ease-in-out infinite; }
    .orb2 { width: 42px; height: 42px; left: 56%; top: 130px; border-radius: 50%; background: radial-gradient(circle at 35% 30%, #fff, #d4dcff 45%, #8aa7ff 100%); opacity: .64; animation: float 8s ease-in-out infinite reverse; }
    .orb3 { width: 48px; height: 48px; right: 5%; bottom: 112px; transform: rotate(25deg); border-radius: 16px; background: linear-gradient(135deg, rgba(255,255,255,.85), rgba(118,87,255,.35), rgba(72,216,255,.45)); box-shadow: inset 0 0 18px rgba(255,255,255,.7); animation: spinFloat 8s ease-in-out infinite; }
    @keyframes float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-18px); } }
    @keyframes spinFloat { 0%,100% { transform: translateY(0) rotate(25deg); } 50% { transform: translateY(-16px) rotate(38deg); } }
    .trail {
      position: absolute; right: -6%; top: 88px; width: 760px; height: 560px; z-index: -2; opacity: .86;
      background:
        radial-gradient(ellipse at 50% 50%, rgba(72,216,255,.16), transparent 48%),
        repeating-conic-gradient(from 100deg at 50% 52%, transparent 0 7deg, rgba(80,135,255,.18) 8deg 9deg, transparent 10deg 19deg);
      border-radius: 50%; filter: blur(.3px); transform: rotate(-13deg);
      animation: trailMove 8s ease-in-out infinite alternate;
      mask-image: radial-gradient(ellipse, rgba(0,0,0,.9), transparent 68%);
    }
    @keyframes trailMove { from { transform: rotate(-13deg) translateX(0); } to { transform: rotate(-10deg) translateX(-18px); } }
    .motionLine {
      position:absolute; left: 20%; top: 218px; width: 76%; height: 240px; pointer-events:none; z-index:-1;
      background:
        radial-gradient(circle at 48% 50%, rgba(255,255,255,.74), transparent 9%),
        linear-gradient(108deg, transparent 7%, rgba(108,122,255,.22) 30%, rgba(72,216,255,.20) 49%, transparent 71%);
      filter: blur(.2px); transform: rotate(-5deg); opacity:.92;
      mask-image: radial-gradient(ellipse at center, rgba(0,0,0,.9), transparent 72%);
      animation: lightFlow 3.8s ease-in-out infinite alternate;
    }
    .motionLine::before, .motionLine::after {
      content:""; position:absolute; border-radius:999px; transform: rotate(-9deg);
      background: linear-gradient(90deg, transparent, rgba(255,255,255,.9), rgba(95,111,255,.42), transparent);
      box-shadow: 0 0 28px rgba(105,129,255,.30);
    }
    .motionLine::before { width: 520px; height: 2px; left: 44px; top: 68px; }
    .motionLine::after { width: 440px; height: 2px; left: 110px; top: 128px; opacity:.74; }
    .sparkField { position:absolute; inset: 24px 0 auto auto; width: 72%; height: 470px; z-index:-1; pointer-events:none; }
    .sparkField i { position:absolute; width:5px; height:5px; border-radius:50%; background:#fff; box-shadow:0 0 18px rgba(105,129,255,.85); opacity:.86; animation: twinkle 2.8s ease-in-out infinite; }
    .sparkField i:nth-child(1){left:18%; top:18%; animation-delay:.1s}.sparkField i:nth-child(2){left:44%; top:8%; animation-delay:.5s}.sparkField i:nth-child(3){left:78%; top:29%; animation-delay:.9s}.sparkField i:nth-child(4){left:64%; top:67%; animation-delay:1.3s}.sparkField i:nth-child(5){left:34%; top:78%; animation-delay:1.7s}
    @keyframes lightFlow { from { opacity:.68; transform: rotate(-6deg) translateX(-10px); } to { opacity:1; transform: rotate(-3deg) translateX(16px); } }
    @keyframes twinkle { 0%,100%{ transform:scale(.7); opacity:.35;} 50%{ transform:scale(1.35); opacity:1;} }

    .heroGrid { display: grid; grid-template-columns: minmax(470px, .94fr) minmax(520px, 1.06fr); gap: 30px; align-items: center; }
    .badgeRow { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
    .badgePill {
      display: inline-flex; align-items: center; gap: 9px; padding: 10px 15px;
      background: rgba(237,242,255,.90); border: 1px solid rgba(198,210,240,.52);
      border-radius: 999px; color: #3151d7; font-weight: 900; font-size: 14px;
    }
    .tinyIcon { display: inline-grid; place-items:center; width: 22px; height: 22px; border-radius: 8px; background: #fff; color:#111; font-size: 12px; box-shadow: 0 4px 12px rgba(32,52,120,.08); }
    h1 {
      margin: 0 0 24px;
      font-size: clamp(54px, 4.2vw, 70px);
      line-height: 1.13;
      letter-spacing: -.055em;
      font-weight: 1000;
      text-wrap: balance;
    }
    .heroLine { display: block; white-space: nowrap; }
    .gradientText {
      background: linear-gradient(90deg, #3267ff 0%, #7657ff 64%, #37bdd8 100%);
      -webkit-background-clip: text; background-clip: text; color: transparent;
      text-shadow: 0 18px 38px rgba(61,96,255,.14);
    }
    .lead { font-size: 17px; color: #58667f; max-width: 520px; margin: 0 0 28px; word-break: keep-all; line-height:1.84; }
    .heroActions { display:flex; gap:14px; flex-wrap: wrap; margin-bottom: 26px; }
    .trustRow { display: grid; grid-template-columns: repeat(4, minmax(96px, max-content)); gap: 14px; align-items: center; color: #1b3f99; }
    .trustItem { display:grid; grid-template-columns: 26px auto; gap: 9px; align-items: center; font-size: 12.5px; min-width:0; }
    .trustIcon { font-size: 22px; color: #4068ff; }
    .trustItem b { display:block; font-size: 16px; color: #20316d; line-height: 1.1; }
    .trustItem span:last-child { color: #657085; }

    .visualStage { position: relative; min-height: 500px; display: grid; place-items: center; overflow: visible; }
    .visualStage::before {
      content: ""; position: absolute; inset: 12px 8px 10px 8px;
      border-radius: 34px;
      background: linear-gradient(135deg, rgba(246,248,255,.86) 0%, rgba(241,245,255,.62) 36%, rgba(235,241,255,.78) 100%);
      border: 1px solid rgba(206,216,242,.72);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.95), 0 24px 54px rgba(79,105,205,.12);
      z-index: -1;
    }
    .platform {
      position: absolute; width: 74%; height: 74px; right: 8%; bottom: 26px; border-radius: 50%;
      background: radial-gradient(ellipse, rgba(102,128,255,.28), rgba(255,255,255,.15) 55%, transparent 70%);
      filter: blur(.2px);
    }
    .inputMock, .outputMock {
      position: absolute; background: rgba(255,255,255,.70); backdrop-filter: blur(22px);
      border: 1px solid rgba(198,210,240,.72); border-radius: 26px;
      box-shadow: var(--shadow);
    }
    .inputMock { width: 214px; left: 3.5%; top: 90px; padding: 16px 16px 14px; transform: rotate(-.25deg); z-index: 2; }
    .outputMock { width: 370px; right: 3%; top: 42px; padding: 18px 20px 18px; transform: rotate(-.45deg); box-shadow: 0 30px 72px rgba(63,85,210,.18); z-index: 2; }
    .mockHead { display:flex; align-items:center; justify-content:space-between; gap:10px; font-weight:950; margin-bottom:14px; color:#162149; letter-spacing:-.025em; min-width:0; font-size:14px; }
    .miniPill { padding: 5px 9px; border-radius: 999px; background: #eff2ff; color: #5268ff; font-weight: 950; font-size: 10.5px; white-space: nowrap; flex: 0 0 auto; }
    .roughText, .refinedText {
      background: rgba(255,255,255,.76); border:1px solid rgba(196,208,239,.64); border-radius: 18px; padding: 18px;
      color:#46546d; font-weight: 650; line-height: 1.72;
      word-break: keep-all; overflow-wrap: break-word;
    }
    .roughText { min-height: 200px; display:flex; flex-direction:column; justify-content:center; font-size: 13px; line-height: 1.76; }
    .refinedText { font-size: 11.7px; color:#263451; line-height:1.58; }
    .refinedText h4 { margin: 0 0 4px; color:#1d33bb; font-size: 13.2px; letter-spacing:-.015em; }
    .refinedText ul { margin: 4px 0 11px; padding-left: 17px; }
    .bridge {
      position:absolute; left: 45.2%; top: 204px; width: 54px; height: 54px; border-radius: 18px; display:grid; place-items:center;
      background: linear-gradient(135deg, #3267ff, #7657ff); color:#fff; font-weight: 1000; font-size: 26px;
      box-shadow: 0 16px 34px rgba(65,91,255,.28); z-index: 4; animation: pulse 2.6s ease-in-out infinite;
    }
    .bridge::before, .bridge::after { content:""; position:absolute; top:50%; height:3px; border-radius:999px; background: linear-gradient(90deg, transparent, rgba(103,113,255,.66), transparent); }
    .bridge::before { width: 110px; right: 44px; transform: translateY(-50%); }
    .bridge::after { width: 132px; left: 44px; transform: translateY(-50%); }
    @keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.04); } }
    .successToast {
      position:absolute; right: 10%; bottom: 44px; background: rgba(255,255,255,.88); backdrop-filter: blur(16px);
      border: 1px solid rgba(198,210,240,.70); border-radius: 999px; padding: 10px 15px; color:#2458e6; font-weight:950; font-size: 12px;
      box-shadow: 0 18px 42px rgba(61,91,185,.16);
    }
    .modelIcons { display:flex; gap:9px; align-items:center; border-top: 1px solid rgba(198,210,240,.60); padding-top: 11px; margin-top: 11px; flex-wrap: nowrap; }
    .modelIcons span { width:26px; height:26px; border-radius:9px; display:grid; place-items:center; background:#f2f5ff; font-size: 12px; font-weight:900; flex:0 0 auto; }

    .section { padding: 52px 0; }
    .panel {
      background: rgba(255,255,255,.82); border: 1px solid rgba(198,210,240,.70); border-radius: 30px;
      box-shadow: var(--shadow); overflow: hidden; backdrop-filter: blur(18px);
    }
    .panelHead { padding: 28px 30px; border-bottom: 1px solid rgba(198,210,240,.60); display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
    .panelHead h2 { margin:0; font-size: 30px; letter-spacing: -.05em; }
    .badge { padding: 8px 12px; border-radius: 999px; background: #eff2ff; color:#365dff; font-weight:950; font-size: 13px; }
    .tool { display:grid; grid-template-columns: .92fr 1.08fr; min-height: 590px; }
    .inputBox, .outputBox { padding: 28px; }
    .inputBox { border-right: 1px solid rgba(198,210,240,.60); background: rgba(249,251,255,.75); }
    label { display:block; font-weight:950; margin-bottom: 10px; color:#1b2440; }
    textarea { width:100%; min-height: 310px; resize:vertical; border:1px solid rgba(176,190,226,.75); border-radius: 20px; padding: 17px; line-height: 1.68; outline:none; background:#fff; color:#172036; }
    textarea:focus { border-color: rgba(50,103,255,.75); box-shadow: 0 0 0 5px rgba(50,103,255,.12); }
    input, select { border:1px solid rgba(176,190,226,.75); border-radius: 16px; padding: 14px; background:#fff; color:#172036; }
    .modeRow { display:flex; gap:10px; flex-wrap:wrap; margin: 15px 0; }
    .pill { border:1px solid rgba(176,190,226,.75); background:#fff; border-radius:999px; padding: 9px 13px; cursor:pointer; font-weight:950; color:#5d6982; }
    .pill.active { color:#fff; background: linear-gradient(135deg, #3267ff, #7657ff); border-color: transparent; }
    .sampleRow { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
    .sample { font-size: 13px; border:1px dashed #aebce3; background:#fff; color:#4f5d78; border-radius:999px; padding:8px 11px; cursor:pointer; font-weight:850; }
    .resultTitle { font-weight:1000; font-size: 18px; margin: 0 0 10px; }
    .notice { color: var(--muted); font-size: 14px; margin: 8px 0 14px; word-break: keep-all; }
    .metricGrid { display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin:14px 0; }
    .metric { border:1px solid rgba(198,210,240,.70); background:#fff; border-radius: 16px; padding: 12px; }
    .metric small { display:block; color:var(--muted); font-weight:900; }
    .metric b { font-size:18px; }
    .resultCard { min-height: 410px; border:1px solid rgba(39,60,120,.25); border-radius: 20px; background:#101a35; color:#eef5ff; padding: 18px; white-space: pre-wrap; overflow:auto; line-height:1.7; font-size:14px; }
    .cards3 { display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; }
    .miniCard { background:rgba(255,255,255,.84); border:1px solid rgba(198,210,240,.70); border-radius:24px; padding:22px; box-shadow: 0 14px 40px rgba(54,91,185,.08); }
    .miniCard h3 { margin:0 0 8px; font-size:20px; letter-spacing:-.04em; }
    .miniCard p { margin:0; color:var(--muted); word-break: keep-all; }
    .pricing { display:grid; grid-template-columns: repeat(4, 1fr); gap:14px; }
    .price { background:rgba(255,255,255,.84); border:1px solid rgba(198,210,240,.70); border-radius:24px; padding:22px; }
    .price.featured { border-color:rgba(50,103,255,.55); box-shadow: var(--shadow); }
    .price h3 { margin:0 0 4px; }
    .amount { font-size: 27px; font-weight:1000; margin:10px 0; letter-spacing:-.04em; }
    .price ul { margin:12px 0 0; padding-left:18px; color:var(--muted); }
    .leadForm { display:grid; grid-template-columns: 1fr 1fr auto; gap:10px; margin-top:18px; }
    footer { padding:40px 0 56px; color:var(--muted); font-size:13px; }
    .toast { position:fixed; right:18px; bottom:18px; background:#101a35; color:#fff; padding:13px 16px; border-radius:14px; box-shadow: var(--shadow); display:none; z-index:99; }


    @media (max-width: 1180px) {
      .nav { grid-template-columns: 220px 1fr 220px; }
      .heroGrid { grid-template-columns: minmax(430px, .94fr) minmax(500px, 1.06fr); gap: 28px; }
      h1 { font-size: clamp(48px, 4.55vw, 64px); letter-spacing: -.052em; }
      .outputMock { width: 350px; right: 2%; }
      .inputMock { width: 204px; left: 2%; }
      .bridge { left: 43.8%; }
      .successToast { right: 8%; }
      .partners { gap: 30px; }
    }

    @media (max-width: 1060px) {
      .heroGrid, .tool { grid-template-columns:1fr; }
      .visualStage { min-height: 500px; max-width: 680px; margin: 0 auto; }
      .inputMock { left: 4%; top: 102px; }
      .outputMock { right: 4%; top: 44px; }
      .bridge { left: 44%; top: 212px; }
      .inputBox { border-right:0; border-bottom:1px solid rgba(198,210,240,.60); }
      .trustRow { grid-template-columns: repeat(2, max-content); }
    }
    @media (max-width: 760px) {
      .navLinks, .smallLogin { display:none; }
      .hero { padding-top: 42px; min-height: auto; }
      h1 { font-size: clamp(42px, 12vw, 62px); line-height:1.08; }
      .heroLine { white-space: normal; }
      .visualStage { display:none; }
      .cards3, .pricing, .leadForm, .metricGrid { grid-template-columns:1fr; }
      .trustRow { grid-template-columns:1fr 1fr; gap:16px; }
    }

    /* V55 Reference Precision overrides: closer reference layout, safer spacing, richer motion */
    .hero { position: relative; min-height: 826px; padding: 22px 0 26px; isolation: isolate; }
    .heroShell {
      position: relative; min-height: 748px; overflow: hidden; isolation:isolate;
      padding: 52px 28px 30px;
      border-radius: 32px;
      border: 1px solid rgba(204,214,238,.88);
      background:
        radial-gradient(circle at 85% 14%, rgba(123,110,255,.16), transparent 34%),
        radial-gradient(circle at 76% 58%, rgba(71,210,255,.10), transparent 26%),
        linear-gradient(96deg, rgba(255,255,255,.98) 0%, rgba(249,250,255,.98) 46%, rgba(239,243,255,.98) 100%);
      box-shadow: 0 30px 90px rgba(65, 88, 170, .14);
    }
    .heroShell::before {
      content:""; position:absolute; inset:0; pointer-events:none; z-index:0;
      background-image:
        linear-gradient(rgba(66,84,148,.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(66,84,148,.04) 1px, transparent 1px);
      background-size: 78px 78px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,.66), transparent 76%);
    }
    .heroShell::after {
      content:""; position:absolute; right:-120px; top:100px; width:620px; height:620px; z-index:0; pointer-events:none;
      background: radial-gradient(circle, rgba(120,109,255,.12), rgba(255,255,255,0) 64%);
      filter: blur(10px);
    }
    .heroGrid {
      position:relative; z-index:2;
      display:grid; gap: 16px; align-items:center;
      grid-template-columns: minmax(580px, 1.12fr) minmax(480px, .88fr);
    }
    .heroCopy { position: relative; z-index: 4; padding-left: 2px; }
    .badgeRow { display:flex; align-items:center; gap: 10px; flex-wrap:wrap; margin-bottom: 26px; }
    .badgePill {
      display:inline-flex; align-items:center; gap:8px; padding: 10px 14px;
      background: rgba(241,245,255,.94); border:1px solid rgba(204,214,238,.8);
      border-radius: 999px; color:#4760df; font-weight: 900; font-size: 13px;
      box-shadow: 0 8px 20px rgba(43,70,145,.05);
    }
    .tinyIcon { display:inline-grid; place-items:center; width: 21px; height: 21px; border-radius: 7px; background:#fff; color:#111; font-size:11px; box-shadow:0 4px 10px rgba(46,65,120,.08); }

    h1 {
      margin: 0 0 24px; max-width: 640px;
      font-size: clamp(56px, 4.6vw, 76px);
      line-height: 1.07; letter-spacing: -.065em; font-weight: 1000;
      color:#0f1731; position:relative; z-index:4; text-wrap: balance;
    }
    .heroLine { display:block; white-space: nowrap; }
    .gradientText {
      background: linear-gradient(90deg, #3567ff 0%, #6a59ff 58%, #35bde2 100%);
      -webkit-background-clip:text; background-clip:text; color: transparent;
      text-shadow: 0 14px 34px rgba(61,96,255,.13);
    }
    .lead { max-width: 520px; margin: 0 0 32px; font-size: 17.5px; line-height: 1.78; color:#57647e; position:relative; z-index:4; }
    .heroActions { display:flex; gap:14px; flex-wrap:wrap; margin-bottom: 34px; position:relative; z-index:4; }
    .trustRow { display:grid; grid-template-columns: repeat(4, minmax(104px, max-content)); gap: 18px; align-items:center; position:relative; z-index:4; }
    .trustItem { display:grid; grid-template-columns: 26px auto; gap: 8px; align-items:center; font-size: 12.5px; }
    .trustIcon { color:#3e65ff; font-size:22px; }
    .trustItem b { display:block; font-size: 15px; color:#23326f; line-height:1.1; }
    .trustItem span:last-child { color:#6b7791; }

    .visualStage {
      position: relative; justify-self:end; width: 100%; max-width: 520px; min-height: 566px;
      display:grid; place-items:center; overflow: visible; z-index:2;
    }
    .orb1,.orb2,.orb3 { position:absolute; pointer-events:none; z-index:1; }
    .orb1 { width:72px; height:72px; left:12px; top:12px; border-radius:50%; background: radial-gradient(circle at 30% 28%, #fff, #86e2ff 28%, #8763ff 82%); box-shadow:0 16px 36px rgba(98,118,255,.18); animation: floatOrb 6s ease-in-out infinite; }
    .orb2 { width:34px; height:34px; left:90px; top:38px; border-radius:50%; background: radial-gradient(circle at 30% 28%, #fff, #dbe3ff 42%, #a2b2ff 100%); animation: floatOrb 7.5s ease-in-out infinite reverse; opacity:.9; }
    .orb3 { width:54px; height:54px; right:-4px; bottom:84px; border-radius:16px; transform: rotate(28deg); background: linear-gradient(135deg, rgba(255,255,255,.9), rgba(123,110,255,.38), rgba(78,218,255,.44)); box-shadow: inset 0 0 18px rgba(255,255,255,.78), 0 18px 40px rgba(97,117,255,.16); animation: prismFloat 8s ease-in-out infinite; }
    @keyframes floatOrb { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-14px); } }
    @keyframes prismFloat { 0%,100% { transform: translateY(0) rotate(28deg); } 50% { transform: translateY(-12px) rotate(38deg); } }

    .sparkField { position:absolute; inset: 8px 0 auto auto; width: 88%; height: 420px; z-index:1; pointer-events:none; }
    .sparkField i { position:absolute; width:5px; height:5px; border-radius:50%; background:#fff; box-shadow: 0 0 18px rgba(104,128,255,.8); opacity:.82; animation: twinkle 2.8s ease-in-out infinite; }
    .sparkField i:nth-child(1){left:20%; top:8%; animation-delay:.1s}.sparkField i:nth-child(2){left:44%; top:2%; animation-delay:.5s}.sparkField i:nth-child(3){left:74%; top:16%; animation-delay:1.1s}.sparkField i:nth-child(4){left:86%; top:46%; animation-delay:1.6s}.sparkField i:nth-child(5){left:58%; top:78%; animation-delay:2.1s}
    @keyframes twinkle { 0%,100% { transform: scale(.72); opacity:.38; } 50% { transform: scale(1.38); opacity:1; } }

    .orbitRing {
      position:absolute; right: -10px; top: 62px; width: 418px; height: 418px; border-radius:50%; z-index:0; pointer-events:none;
      border:1px solid rgba(141,156,255,.14);
      box-shadow: inset 0 0 28px rgba(103,126,255,.06);
      animation: spinRing 20s linear infinite;
    }
    .orbitRing::before, .orbitRing::after {
      content:""; position:absolute; inset: 34px; border-radius:50%; border:1px dashed rgba(152,173,255,.16);
    }
    .orbitRing::after { inset: 82px; border-style: solid; border-color: rgba(110, 220, 255, .14); }
    @keyframes spinRing { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

    .trail {
      position:absolute; right: -72px; top: 94px; width: 560px; height: 360px; z-index:1; pointer-events:none;
      background: radial-gradient(ellipse at 50% 50%, rgba(73,216,255,.12), transparent 52%);
      mask-image: radial-gradient(ellipse at center, rgba(0,0,0,.92), transparent 74%);
      filter: blur(.2px);
    }
    .trail::before, .trail::after {
      content:""; position:absolute; left: 26px; right: 0; height: 2px; border-radius:999px;
      background: linear-gradient(90deg, transparent 0%, rgba(98,123,255,.22) 20%, rgba(255,255,255,.88) 44%, rgba(92,235,255,.22) 65%, transparent 86%);
      box-shadow: 0 0 18px rgba(110,124,255,.20);
      transform: rotate(-8deg);
      animation: glide 4.6s ease-in-out infinite alternate;
    }
    .trail::before { top: 92px; width: 430px; }
    .trail::after { top: 144px; width: 350px; left: 84px; opacity:.78; animation-duration: 6s; }
    @keyframes glide { from { transform: rotate(-8deg) translateX(0); opacity:.64; } to { transform: rotate(-8deg) translateX(24px); opacity:1; } }

    .platform {
      position:absolute; right: -20px; bottom: 28px; width: 470px; height: 112px; z-index:1; border-radius:50%;
      background: radial-gradient(ellipse, rgba(104,127,255,.30), rgba(255,255,255,.18) 56%, transparent 72%);
      box-shadow: inset 0 -8px 26px rgba(66,92,255,.18), 0 24px 58px rgba(68,95,255,.16);
      animation: platformGlow 5s ease-in-out infinite;
    }
    .platform::before { content:""; position:absolute; inset: 16px 26px; border-radius:50%; border:2px solid rgba(87,107,255,.30); box-shadow:0 0 22px rgba(72,216,255,.18); }
    @keyframes platformGlow { 0%,100% { filter: brightness(1); } 50% { filter: brightness(1.05); } }

    .inputMock, .outputMock {
      position:absolute; background: rgba(255,255,255,.80); backdrop-filter: blur(24px);
      border:1px solid rgba(198,210,240,.76); border-radius: 28px; overflow:hidden;
      box-shadow: 0 28px 78px rgba(54,91,185,.14);
    }
    .inputMock {
      width: 230px; left: 26px; top: 142px; padding: 18px; z-index:3; transform: rotate(-0.2deg);
      animation: cardFloat 5.2s ease-in-out infinite;
    }
    .outputMock {
      width: 374px; right: 8px; top: 18px; padding: 20px 20px 18px; z-index:3; transform: rotate(-0.5deg);
      box-shadow: 0 36px 96px rgba(63,85,210,.18);
      animation: cardFloat 6.2s ease-in-out infinite reverse;
    }
    @keyframes cardFloat { 0%,100% { transform: translateY(0) rotate(-0.2deg); } 50% { transform: translateY(-6px) rotate(-0.2deg); } }
    .outputMock { --rot:-0.5deg; }
    .outputMock::before {
      content:""; position:absolute; inset:-1px; border-radius:inherit; padding:1px; pointer-events:none;
      background: linear-gradient(135deg, rgba(124,109,255,.42), rgba(255,255,255,.18), rgba(82,219,255,.36));
      -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
      -webkit-mask-composite: xor; mask-composite: exclude;
      opacity:.58;
    }

    .mockHead { display:flex; align-items:center; justify-content:space-between; gap:8px; font-weight:950; margin-bottom:14px; color:#18224a; font-size:14px; }
    .miniPill { padding: 6px 10px; border-radius:999px; background:#eef2ff; color:#5268ff; font-weight:950; font-size:11px; white-space:nowrap; }
    .roughText, .refinedText {
      background: rgba(255,255,255,.82); border:1px solid rgba(196,208,239,.66); border-radius:18px; padding:16px;
      overflow-wrap:anywhere; word-break:keep-all;
    }
    .roughText { min-height: 246px; display:flex; flex-direction:column; justify-content:center; color:#4b5971; font-size:13.6px; line-height:1.72; }
    .refinedText { color:#2d3856; font-size:12.5px; line-height:1.58; }
    .refinedText h4 { margin: 0 0 4px; color:#2c42c0; font-size: 12.8px; }
    .refinedText ul { margin: 4px 0 10px; padding-left: 16px; }
    .modelIcons { display:flex; gap:8px; align-items:center; border-top:1px solid rgba(198,210,240,.6); padding-top:10px; margin-top:10px; flex-wrap:nowrap; }
    .modelIcons span { width:24px; height:24px; border-radius:8px; display:grid; place-items:center; background:#f2f5ff; font-size:11px; font-weight:900; flex:0 0 auto; }

    .bridge {
      position:absolute; left: 236px; top: 264px; width: 66px; height: 66px; border-radius: 21px; z-index:5;
      display:grid; place-items:center; background: linear-gradient(135deg, #3567ff, #7359ff); color:#fff; font-weight:1000; font-size:30px;
      box-shadow: 0 20px 46px rgba(65,91,255,.32);
      animation: pulse 2.6s ease-in-out infinite;
    }
    .bridge::before, .bridge::after { content:""; position:absolute; top:50%; height:3px; border-radius:999px; transform: translateY(-50%); background: linear-gradient(90deg, transparent, rgba(111,118,255,.62), transparent); }
    .bridge::before { width: 90px; right: 52px; }
    .bridge::after { width: 122px; left: 52px; }
    .bridgePulse {
      position:absolute; left: 218px; top: 246px; width: 102px; height: 102px; border-radius:50%; z-index:4; pointer-events:none;
      border: 1px solid rgba(96,114,255,.22); box-shadow:0 0 28px rgba(96,114,255,.12); animation: ringPulse 2.8s ease-out infinite;
    }
    .bridgeSpark {
      position:absolute; left: 265px; top: 312px; width: 10px; height: 10px; border-radius:50%; z-index:6; pointer-events:none;
      background:#fff; box-shadow:0 0 16px rgba(117,119,255,.88); animation: sparkJump 3s ease-in-out infinite;
    }
    @keyframes pulse { 0%,100% { transform: scale(1);} 50%{ transform: scale(1.045);} }
    @keyframes ringPulse { 0%{ transform: scale(.82); opacity:.72;} 70%{ transform: scale(1.16); opacity:.18;} 100%{ transform: scale(1.2); opacity:0;} }
    @keyframes sparkJump { 0%,100% { transform: translate3d(0,0,0); opacity:.5;} 50% { transform: translate3d(10px,-6px,0); opacity:1;} }

    .successToast {
      position:absolute; left: 50%; bottom: 56px; transform: translateX(-10%);
      background: rgba(255,255,255,.92); backdrop-filter: blur(16px);
      border:1px solid rgba(198,210,240,.7); border-radius: 999px; padding: 12px 18px;
      color:#2856e5; font-weight:950; font-size: 13px; z-index:4;
      box-shadow: 0 18px 42px rgba(61,91,185,.14);
      white-space: nowrap;
    }

    .trustStrip {
      position:relative; z-index:2; margin-top: 28px; padding-top: 16px; border-top:1px solid rgba(199,210,238,.46);
      color:#7a85a0; font-size: 12.5px; text-align:center;
    }
    .trustStripItems {
      margin-top: 12px; display:flex; justify-content:center; align-items:center; gap: 26px; flex-wrap: wrap;
      color:#8a94ab; font-weight:900; font-size: 12px; letter-spacing: .01em;
    }
    .trustStripItems span { opacity:.9; }

    @media (max-width: 1260px) {
      .heroGrid { grid-template-columns: minmax(540px, 1.06fr) minmax(440px, .94fr); }
      h1 { max-width: 600px; font-size: clamp(52px, 4.3vw, 70px); }
      .visualStage { max-width: 490px; }
      .outputMock { width: 356px; }
      .inputMock { width: 218px; left: 18px; }
      .bridge { left: 222px; }
      .bridgePulse { left: 204px; }
      .bridgeSpark { left: 250px; }
      .successToast { transform: translateX(-4%); }
    }
    @media (max-width: 1140px) {
      .heroShell { padding: 46px 22px 28px; }
      .heroGrid { grid-template-columns: minmax(500px, 1fr) minmax(420px, .94fr); gap: 12px; }
      h1 { max-width: 560px; font-size: clamp(48px, 4.2vw, 64px); }
      .lead { max-width: 500px; }
      .trustRow { gap: 14px; grid-template-columns: repeat(4, minmax(96px, max-content)); }
      .visualStage { max-width: 462px; }
      .outputMock { width: 336px; right: 0; }
      .inputMock { width: 206px; left: 4px; top: 150px; }
      .bridge { left: 206px; top: 268px; }
      .bridgePulse { left: 188px; top: 250px; }
      .bridgeSpark { left: 234px; top: 316px; }
      .platform { width: 430px; right: -8px; }
      .successToast { left: 52%; bottom: 58px; font-size:12.5px; }
    }
    @media (max-width: 1040px) {
      .hero { min-height: auto; }
      .heroGrid { grid-template-columns: 1fr; }
      .heroCopy { padding-right: 0; }
      h1 { max-width: none; }
      .heroLine { white-space: normal; }
      .visualStage { max-width: 700px; min-height: 560px; margin: 2px auto 0; }
      .inputMock { width: 236px; left: 7%; top: 144px; }
      .outputMock { width: 386px; right: 5%; top: 22px; }
      .bridge { left: 44%; top: 264px; }
      .bridgePulse { left: 41.8%; top: 246px; }
      .bridgeSpark { left: 47%; top: 314px; }
      .successToast { left: 56%; transform: translateX(-10%); }
      .trustRow { grid-template-columns: repeat(2, max-content); }
    }
    @media (max-width: 760px) {
      .heroShell { border-radius: 24px; padding: 34px 18px 24px; }
      h1 { font-size: clamp(42px, 12vw, 56px); line-height:1.08; }
      .visualStage, .trustStrip { display:none; }
      .trustRow { grid-template-columns: 1fr 1fr; gap: 16px; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap nav">
      <a class="logo" href="#top"><span class="logoMark"></span><span>PromptCraft</span></a>
      <div class="navLinks"><a href="#why">기능</a><a href="#tool">프롬프트 템플릿</a><a href="#why">활용 가이드</a><a href="#pricing">요금제</a><a href="#why">고객 사례</a></div>
      <div class="navRight"><a class="smallLogin" href="#pricing">로그인</a><a class="btn btnPrimary" href="#tool">무료로 시작하기 →</a></div>
    </div>
  </div>

  <main id="top">
    <section class="hero">
      <div class="wrap heroShell">
        <div class="trail"></div>
        <div class="heroGrid">
          <div class="heroCopy">
            <div class="badgeRow">
              <span class="badgePill">✦ PromptCraft 중심</span>
              <span class="badgePill"><span class="tinyIcon">◎</span><span class="tinyIcon">AI</span> GPT · Claude · Gemini · Genspark</span>
            </div>
            <h1>
              <span class="heroLine">대충 적어도,</span>
              <span class="heroLine"><span class="gradientText">AI가 알아듣는</span> 질문으로.</span>
            </h1>
            <p class="lead">PromptCraft는 당신의 아이디어를 구조화된 프롬프트로 바꿔 어떤 AI에게도 정확하고 유용한 답변을 이끌어냅니다.</p>
            <div class="heroActions">
              <a class="btn btnPrimary" href="#tool">✦ 프롬프트 변환 시작하기 →</a>
              <a class="btn btnSoft" href="#tool">▣ 템플릿 둘러보기</a>
            </div>
            <div class="trustRow">
              <div class="trustItem"><span class="trustIcon">👥</span><span><b>50,000+</b><span>사용자</span></span></div>
              <div class="trustItem"><span class="trustIcon">⚡</span><span><b>200,000+</b><span>프롬프트 생성</span></span></div>
              <div class="trustItem"><span class="trustIcon">✦</span><span><b>98%</b><span>만족도</span></span></div>
              <div class="trustItem"><span class="trustIcon">🛡</span><span><b>안전한 데이터</b><span>비공개 · 암호화</span></span></div>
            </div>
          </div>

          <div class="visualStage" aria-hidden="true">
            <div class="orb1"></div>
            <div class="orb2"></div>
            <div class="orb3"></div>
            <div class="sparkField"><i></i><i></i><i></i><i></i><i></i></div>
            <div class="orbitRing"></div>
            <div class="platform"></div>
            <div class="inputMock">
              <div class="mockHead"><span>사용자 입력</span><span class="miniPill">대충 쓴 아이디어</span></div>
              <div class="roughText">마케팅 성과 정리해줘.<br>지난 분기 캠페인 성과랑<br>개선점도 알려줘.<br>표로 보기 좋게.</div>
              <p class="notice">42 / 500</p>
            </div>
            <div class="bridge">P</div>
            <div class="bridgePulse"></div>
            <div class="bridgeSpark"></div>
            <div class="outputMock">
              <div class="mockHead"><span>PromptCraft 변환 결과</span><span class="miniPill">구조화된 프롬프트</span></div>
              <div class="refinedText">
                <h4>목표</h4>
                지난 분기 마케팅 캠페인의 성과를 분석하고, 개선점과 다음 분기 제안을 도출한다.
                <h4>분석 항목</h4>
                <ul><li>캠페인별 성과: 노출, 클릭, 전환, 비용, ROAS</li><li>성과 요약 · 주요 인사이트 · 개선 제안</li></ul>
                <h4>형식</h4>
                <ul><li>보기 좋은 표와 핵심 요약 포함</li></ul>
                <h4>톤 & 스타일</h4>
                <ul><li>비즈니스 보고서 톤, 명확하고 간결하게</li></ul>
                <div class="modelIcons"><small>대상 AI</small><span>◎</span><span>AI</span><span>◆</span><span>G</span><span>✓</span></div>
              </div>
            </div>
            <div class="successToast">✅ 프롬프트가 성공적으로 변환되었습니다</div>
          </div>
        </div>

        <div class="trustStrip">
          <div>실무형 프롬프트 설계 · AI별 최적화 · 안전한 비공개 변환</div>
          <div class="trustStripItems"><span>GPT 최적화</span><span>Claude 맥락형</span><span>Gemini 표 구조</span><span>Genspark 리서치형</span></div>
        </div>
      </div>
    </section>

    <section id="tool" class="section">
      <div class="wrap panel">
        <div class="panelHead">
          <h2>프롬프트 변환기</h2>
          <span class="badge">V55 · 레퍼런스 정밀 반영 · 모션 강화</span>
        </div>
        <div class="tool">
          <div class="inputBox">
            <label for="targetEngine">어떤 AI에 붙여넣을까요?</label>
            <select id="targetEngine" style="width:100%; margin-bottom:14px;">
              <option value="auto">자동 / 범용</option>
              <option value="gpt">GPT용</option>
              <option value="claude">Claude용</option>
              <option value="gemini">Gemini용</option>
              <option value="genspark">Genspark AI용</option>
            </select>
            <label for="sourceText">대충 쓴 생각, 키워드, 또는 긴 프롬프트</label>
            <textarea id="sourceText" placeholder="예: 이번엔 영어 자료 판매 사이트를 만들고 싶어. 중학 고등 수능을 대상으로 나눠서 첫 버전을 만들고 싶어..."></textarea>
            <div class="modeRow">
              <button class="pill active" data-mode="auto">자동 판단</button>
              <button class="pill" data-mode="craft">PromptCraft</button>
              <button class="pill" data-mode="zip">PromptZip</button>
            </div>
            <button class="btn btnPrimary" id="runBtn">변환 실행</button>
            <button class="btn btnSoft" id="clearBtn">초기화</button>
            <div class="sampleRow">
              <button class="sample" data-sample="site">영어 자료 판매 사이트</button>
              <button class="sample" data-sample="lesson">수업 자료 제작</button>
              <button class="sample" data-sample="zip">긴 프롬프트 압축</button>
              <button class="sample" data-sample="genspark">Genspark 리서치형</button>
            </div>
          </div>
          <div class="outputBox">
            <p class="resultTitle" id="resultTitle">결과가 여기에 표시됩니다</p>
            <p class="notice" id="resultNotice">자동 판단 모드에서는 입력 의도에 따라 Craft 또는 Zip을 추천합니다.</p>
            <div class="metricGrid">
              <div class="metric"><small>입력</small><b id="mIn">0자</b></div>
              <div class="metric"><small>출력</small><b id="mOut">0자</b></div>
              <div class="metric"><small id="mLabel">변화</small><b id="mRate">0%</b></div>
            </div>
            <div class="resultCard" id="resultBox">아직 실행 전입니다.</div>
            <div class="modeRow">
              <button class="btn btnSoft" id="copyBtn">결과 복사</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="why" class="section">
      <div class="wrap">
        <div class="cards3">
          <div class="miniCard"><h3>1. 레퍼런스 메인 반영</h3><p>선호 이미지처럼 좌측 카피와 우측 변환 데모가 균형 잡히도록 메인 화면을 재구성했습니다.</p></div>
          <div class="miniCard"><h3>2. 모션 그래픽 강화</h3><p>흐르는 빛, 오브, 스파클, 플랫폼 링으로 정적인 화면보다 더 역동적인 느낌을 넣었습니다.</p></div>
          <div class="miniCard"><h3>3. Craft가 메인</h3><p>일반 사용자가 가장 많이 원하는 “좋은 질문 만들기”를 첫 화면의 핵심 가치로 유지했습니다.</p></div>
          <div class="miniCard"><h3>4. 겹침 방지 설계</h3><p>우측 카드와 중앙 P 브릿지의 위치·폭·z-index를 다시 잡아 글자와 레이어가 겹치지 않게 했습니다.</p></div>
        </div>
      </div>
    </section>

    <section id="pricing" class="section">
      <div class="wrap">
        <div class="panelHead" style="padding-left:0;padding-right:0;border:0;"><h2>초기 요금제 예시</h2><span class="badge">베타 테스트용</span></div>
        <div class="pricing">
          <div class="price"><h3>Free</h3><p>테스트용</p><div class="amount">0원</div><ul><li>하루 3회</li><li>Craft/Zip 체험</li></ul></div>
          <div class="price featured"><h3>Craft Pro</h3><p>질문 고도화 중심</p><div class="amount">9,900원</div><ul><li>키워드 → 고급 질문</li><li>직무/교육/기획 템플릿</li></ul></div>
          <div class="price"><h3>Zip Pro</h3><p>긴 프롬프트 압축</p><div class="amount">9,900원</div><ul><li>의미 보존 압축</li><li>중복 지시 제거</li></ul></div>
          <div class="price"><h3>Bundle</h3><p>둘 다 사용</p><div class="amount">14,900원</div><ul><li>Craft + Zip</li><li>초기 베타 추천</li></ul></div>
        </div>
        <form class="leadForm" id="leadForm">
          <input name="email" type="email" placeholder="관심 등록 이메일" required>
          <select name="plan"><option>Craft Pro</option><option>Zip Pro</option><option>Bundle</option></select>
          <button class="btn btnPrimary" type="submit">관심 등록</button>
        </form>
      </div>
    </section>
  </main>

  <footer>
    <div class="wrap">
      <p>민감한 개인정보, 회사 기밀, API Key를 프롬프트에 입력하지 마세요.</p>
      <p>비용 계산과 압축률은 참고용 추정값입니다. 실제 결과와 청구액은 사용하는 AI 서비스의 정책과 사용량에 따라 달라질 수 있습니다.</p>
      <p>PromptCraft __APP_VERSION__</p>
    </div>
  </footer>

  <div class="toast" id="toast"></div>

  <script>
    let currentMode = 'auto';
    const sourceText = document.getElementById('sourceText');
    const targetEngine = document.getElementById('targetEngine');
    const resultBox = document.getElementById('resultBox');
    const resultTitle = document.getElementById('resultTitle');
    const resultNotice = document.getElementById('resultNotice');
    const mIn = document.getElementById('mIn');
    const mOut = document.getElementById('mOut');
    const mRate = document.getElementById('mRate');
    const mLabel = document.getElementById('mLabel');
    const toast = document.getElementById('toast');

    function showToast(message) {
      toast.textContent = message;
      toast.style.display = 'block';
      setTimeout(() => toast.style.display = 'none', 1800);
    }

    document.querySelectorAll('.pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
      });
    });

    const samples = {
      site: '이번엔 영어 자료 판매 사이트를 만들고 싶어. 중학 고등 수능을 대상으로 나눠서 첫 버전을 만들고 싶어. 내가 지금까지 만든 여러가지 유형별 프롬프트를 활용해서 누구라도 이용할 것 같은 사이트 하나 만들어줘.',
      lesson: '고등학생 영어 독해 수업 자료, 어법 포인트, 빈칸 순서 삽입 문제, 학생들이 자주 틀리는 부분, 표로 정리, 수업시간에 바로 쓰기 좋게 만들어줘',
      zip: '나는 GPT, Claude, Gemini, Genspark AI 같은 AI를 활용해서 수업 자료나 업무 자료를 만들 때 더 좋은 결과를 얻고 싶다. 아래 내용을 바탕으로 사용자가 입력한 긴 요청을 더 명확하고 효율적인 프롬프트로 정리해줘. 단순히 짧게 줄이는 것이 아니라, 원래 요청의 목적, 대상, 조건, 출력 형식, 주의사항이 빠지지 않도록 유지해야 한다. 특히 결과물이 너무 일반적이거나 뻔하지 않게 나오도록 구체적인 역할을 부여하고, 필요한 경우 표나 단계별 설명을 포함하게 해줘.',
      genspark: '2026년 AI 프롬프트 서비스 시장, 프롬프트 압축과 질문 고도화 사이트 경쟁 서비스, 가격대, 사용자 불편, 차별화 포인트, 한국어 사용자 대상, 표로 비교, 첫 출시 전략까지 정리해줘'
    };
    document.querySelectorAll('.sample').forEach(btn => {
      btn.addEventListener('click', () => { sourceText.value = samples[btn.dataset.sample]; });
    });

    document.getElementById('runBtn').addEventListener('click', async () => {
      const text = sourceText.value.trim();
      if (!text) { showToast('먼저 내용을 입력해 주세요.'); return; }
      resultBox.textContent = '변환 중입니다...';
      const res = await fetch('/api/transform', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, mode: currentMode, target: targetEngine.value })
      });
      const data = await res.json();
      if (!data.ok) { showToast(data.error || '오류가 발생했습니다.'); return; }
      resultTitle.textContent = data.title;
      resultNotice.textContent = '[' + data.target_label + '] ' + data.reason + ' ' + data.quality;
      resultBox.textContent = data.result;
      mIn.textContent = data.metrics.input_chars + '자';
      mOut.textContent = data.metrics.output_chars + '자';
      mLabel.textContent = data.metrics.label;
      const rate = data.metrics.change_rate;
      mRate.textContent = (rate > 0 ? '-' + rate : '+' + Math.abs(rate)) + '%';
      if (window.gtag) window.gtag('event', data.mode === 'zip' ? 'promptzip_run' : 'promptcraft_run');
    });

    document.getElementById('copyBtn').addEventListener('click', async () => {
      await navigator.clipboard.writeText(resultBox.textContent);
      showToast('결과를 복사했습니다.');
      if (window.gtag) window.gtag('event', 'copy_result');
    });

    document.getElementById('clearBtn').addEventListener('click', () => {
      sourceText.value = '';
      resultBox.textContent = '아직 실행 전입니다.';
      resultTitle.textContent = '결과가 여기에 표시됩니다';
      resultNotice.textContent = '자동 판단 모드에서는 입력 의도에 따라 Craft 또는 Zip을 추천합니다.';
      mIn.textContent = '0자'; mOut.textContent = '0자'; mRate.textContent = '0%';
    });

    document.getElementById('leadForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = new FormData(e.currentTarget);
      const res = await fetch('/api/lead', { method: 'POST', body: form });
      const data = await res.json();
      if (data.ok) {
        showToast('관심 등록이 완료되었습니다.');
        e.currentTarget.reset();
        if (window.gtag) window.gtag('event', 'lead_submit');
      } else {
        showToast(data.error || '등록에 실패했습니다.');
      }
    });
  </script>
</body>
</html>
'''


def ga_script() -> str:
    if not GA_MEASUREMENT_ID:
        return ""
    safe_id = re.sub(r"[^A-Za-z0-9\-]", "", GA_MEASUREMENT_ID)
    return f'''<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={safe_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{safe_id}');
</script>'''


@app.get("/")
def index():
    page = HTML.replace("__GA_SCRIPT__", ga_script()).replace("__APP_VERSION__", APP_VERSION)
    return render_template_string(page)


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "version": APP_VERSION})


@app.post("/api/transform")
def transform():
    payload = request.get_json(silent=True) or {}
    text = clean_text(payload.get("text", ""))
    mode_request = payload.get("mode", "auto")
    target_engine = normalize_engine(payload.get("target", "auto"))
    if len(text) < 5:
        return jsonify({"ok": False, "error": "입력이 너무 짧습니다. 조금 더 구체적으로 적어 주세요."}), 400
    mode, reason = detect_mode(text, mode_request)
    data = craft_prompt(text, target_engine) if mode == "craft" else zip_prompt(text, target_engine)
    metrics = build_metrics(text, data["result"], "zip" if data["mode"] == "zip" else "craft")
    return jsonify({
        "ok": True,
        "mode": data["mode"],
        "title": data["title"],
        "reason": reason,
        "quality": data["quality"],
        "target_label": data.get("target_label", "자동"),
        "result": data["result"],
        "metrics": metrics,
    })


@app.post("/api/lead")
def lead():
    email = clean_text(request.form.get("email", ""))
    plan = clean_text(request.form.get("plan", ""))
    if "@" not in email or "." not in email:
        return jsonify({"ok": False, "error": "이메일 형식을 확인해 주세요."}), 400
    is_new = not LEADS_FILE.exists()
    with LEADS_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["created_at", "email", "plan"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), email, plan])
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8818"))
    app.run(host="0.0.0.0", port=port, debug=False)
