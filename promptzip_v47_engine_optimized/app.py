import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
APP_VERSION = "V47 Engine Optimized Edition"
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
    if engine == "gpt":
        return """GPT 최적화 지침:
- 먼저 역할, 목표, 입력 조건, 출력 형식을 짧고 선명하게 고정한다.
- 모호한 표현은 구체적인 작업 명령으로 바꾼다.
- 답변이 산만해지지 않도록 번호 구조와 표 사용 여부를 명확히 지정한다.
- 필요한 경우에만 예시를 요구하고, 불필요한 배경 설명은 줄인다."""
    if engine == "claude":
        return """Claude 최적화 지침:
- 충분한 배경, 맥락, 의도, 판단 기준을 자연어로 제공한다.
- 요구사항 사이의 우선순위를 명확히 적어 긴 맥락에서도 조건이 누락되지 않게 한다.
- 최종 답변 전에 스스로 조건 충족 여부를 점검하되, 내부 사고 과정은 길게 드러내지 않는다.
- 섬세한 문체, 예외 조건, 품질 기준을 함께 제시한다."""
    if engine == "gemini":
        return """Gemini 최적화 지침:
- 표, 단계별 목록, 비교 구조가 잘 나오도록 섹션을 명확히 분리한다.
- 큰 그림 → 세부 항목 → 실행 순서 순서로 정리하게 한다.
- 여러 대안을 비교할 때 기준 열을 명시하고, 한눈에 읽히는 형태를 요구한다.
- 필요한 경우 웹/문서/이미지 등 추가 자료가 들어와도 확장 가능한 구조로 쓴다."""
    if engine == "genspark":
        return """Genspark AI 최적화 지침:
- 단순 작성 요청보다 리서치 목표, 조사 범위, 비교 기준, 검증 기준을 먼저 제시한다.
- 최신성 확인이 필요한 항목은 별도로 표시하고, 근거가 약한 내용은 가정/추가 확인 사항으로 분리하게 한다.
- 경쟁 서비스, 가격, 기능, 사용자 니즈처럼 조사 가능한 항목은 표로 비교하게 한다.
- 최종 산출물은 요약, 근거 기반 비교, 실행 제안, 다음 확인 질문 순서로 정리하게 한다."""
    return """범용 최적화 지침:
- GPT, Claude, Gemini, Genspark AI 어디에 붙여넣어도 이해되도록 역할, 목표, 조건, 출력 형식을 분리한다.
- 입력 의도와 핵심 조건을 유지하고, 불필요한 반복과 애매한 표현을 제거한다.
- 표와 단계별 설명을 적절히 섞어 바로 실행 가능한 질문으로 만든다."""


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


def craft_prompt(text: str, target_engine: str = "auto") -> Dict[str, object]:
    engine_key = normalize_engine(target_engine)
    engine_label, engine_instruction = engine_guide(engine_key)
    output_language = detect_output_language(text)
    engine_block = engine_specific_block(engine_key, "craft")
    topic = detect_topic(text)
    audience = detect_audience(text)
    keywords = extract_keywords(text)
    materials = infer_materials(text)

    target_line = ", ".join(audience)
    materials_block = ""
    if materials:
        materials_block = "\n- 자료/상품 예시: " + ", ".join(materials)

    keyword_block = "\n".join([f"- {kw}" for kw in keywords]) if keywords else f"- {text}"

    # Genspark AI should receive a research-first output map, while the other engines
    # should receive a production-planning prompt.
    if engine_key == "genspark":
        output_sections = [
            "리서치 목표 한 줄 요약",
            "조사해야 할 시장/사용자/경쟁 서비스 범위",
            "중학 / 고등 / 수능 대상별 수요와 구매 동기",
            "경쟁 서비스 또는 대체재 비교표",
            "판매 가능한 영어 자료 상품군",
            "가격대와 무료 샘플 전략",
            "근거가 확실한 내용과 추가 확인이 필요한 내용 구분",
            "첫 출시 MVP 제안",
            "랜딩페이지 문구와 구매 유도 문구",
            "다음 조사 질문 5개",
        ]
    elif engine_key == "gemini":
        output_sections = [
            "한눈에 보는 사이트 구조 표",
            "대상별 카테고리 맵",
            "상품 유형별 비교표",
            "사용자 이용 흐름 단계",
            "무료/유료 상품 구성",
            "가격 구조",
            "첫 출시 기능과 이후 기능 비교",
            "메인 페이지 섹션 구성",
            "구매 전환 문구",
            "실행 체크리스트",
        ]
    elif engine_key == "claude":
        output_sections = [
            "서비스가 해결할 문제와 핵심 맥락",
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

    prompt = f"""역할: 교육 서비스 기획자이자 웹사이트 수익화 전략가.

목표: {topic}를 첫 출시 버전으로 설계한다. 사용자가 대충 적은 아이디어를 바탕으로 실제 제작자가 바로 이해할 수 있는 사이트 구조, 상품 구조, 이용 흐름, 가격 구조까지 정리한다.

대상 AI: {engine_label}
작성 언어: {output_language}
AI별 작성 지침: {engine_instruction}

{engine_block}

원본 아이디어:
{keyword_block}

대상:
- 핵심 사용자: {target_line}
- 초보 사용자도 어떤 자료를 선택해야 하는지 바로 이해할 수 있어야 한다.{materials_block}

반드시 반영할 조건:
- 최종 답변은 {output_language}로 작성한다.
- 첫 버전에서 바로 구현 가능한 현실적인 구조로 설계한다.
- 중학 / 고등 / 수능처럼 대상이 다르면 카테고리와 상품 설명을 분리한다.
- 사용자가 사이트에 들어오자마자 무엇을 살 수 있고 어떤 도움이 되는지 이해하게 만든다.
- 무료 샘플, 유료 상품, 결제 후 자료 제공 방식까지 포함한다.
- 너무 거창한 플랫폼보다 빠르게 출시하고 반응을 볼 수 있는 MVP 구조를 우선한다.

출력 형식:
{sections_block}

품질 기준:
- 설명은 일반 사용자도 이해할 수 있게 명확하게 쓴다.
- 표와 단계별 구조를 적절히 섞어 정리한다.
- 뻔한 말보다 실제 랜딩페이지와 상품 설계에 바로 쓸 수 있는 문구를 포함한다.
- 마지막에는 오늘 바로 제작해야 할 우선순위 5개를 제시한다."""

    return {
        "mode": "craft",
        "title": "PromptCraft 결과 — 대충 쓴 생각을 고급 질문으로 변환",
        "result": prompt,
        "topic": topic,
        "target_label": engine_label,
        "quality": f"{engine_label}에 맞춘 작성 언어·구조·출력 형식을 반영한 완성형 프롬프트입니다.",
    }


def split_sentences(text: str) -> List[str]:
    chunks = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [c.strip() for c in chunks if c.strip()]


def zip_prompt(text: str, target_engine: str = "auto") -> Dict[str, object]:
    engine_key = normalize_engine(target_engine)
    engine_label, engine_instruction = engine_guide(engine_key)
    output_language = detect_output_language(text)
    engine_block = engine_specific_block(engine_key, "zip")
    sentences = split_sentences(text)
    # Remove repeated or near-identical short fragments.
    compact_sentences = []
    seen = set()
    for sentence in sentences:
        key = re.sub(r"\W+", "", sentence.lower())[:80]
        if key and key not in seen:
            seen.add(key)
            compact_sentences.append(sentence)

    joined = " ".join(compact_sentences)
    # Trim common filler phrases while preserving the user's intent.
    replacements = [
        ("나는 ", ""), ("앞으로는 ", ""), ("가능하다면 ", ""), ("좀 ", ""),
        ("대충 ", ""), ("정말 ", ""), ("너무 ", ""), ("반드시 ", "반드시 "),
        ("해줘", "한다"), ("해주세요", "한다"),
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

    result = f"""역할: 사용자의 요청을 정확히 수행하는 전문 AI 어시스턴트.

목표: 아래 요청의 핵심 목적, 조건, 출력 형식을 유지하면서 불필요한 반복을 제거해 간결하게 수행한다.

대상 AI: {engine_label}
작성 언어: {output_language}
AI별 작성 지침: {engine_instruction}

{engine_block}

요청:
{joined}

출력 조건:
- 최종 답변은 {output_language}로 작성한다.
- 핵심 조건은 빠뜨리지 않는다.
- 결과는 바로 사용할 수 있게 구조화한다.
- 불필요한 반복, 감정 표현, 모호한 지시는 제거한다.
- 선택한 대상 AI의 장점에 맞는 구조를 유지한다."""

    if len(result) >= len(text) * 1.25:
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
  <title>PromptZip | Engine Optimized Edition</title>
  <meta name="description" content="GPT, Claude, Gemini, Genspark AI에 맞춰 대충 쓴 생각을 좋은 AI 질문으로 바꾸고, 긴 프롬프트는 의미를 유지해 압축합니다." />
  __GA_SCRIPT__
  <style>
    :root {
      --bg: #f6f8fc;
      --ink: #121826;
      --muted: #657085;
      --line: #dbe3f0;
      --navy: #13264b;
      --blue: #2f6bff;
      --blue2: #eaf1ff;
      --mint: #e8fff7;
      --mintText: #09745a;
      --yellow: #fff4c7;
      --orange: #ff8b3d;
      --card: #ffffff;
      --shadow: 0 20px 60px rgba(19, 38, 75, .12);
      --radius: 24px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(47,107,255,.14), transparent 34%),
        radial-gradient(circle at top right, rgba(255,139,61,.12), transparent 28%),
        var(--bg);
      color: var(--ink);
      line-height: 1.65;
    }
    a { color: inherit; text-decoration: none; }
    .wrap { width: min(1180px, calc(100% - 32px)); margin: 0 auto; }
    .topbar {
      position: sticky; top: 0; z-index: 10;
      background: rgba(246,248,252,.82);
      backdrop-filter: blur(18px);
      border-bottom: 1px solid rgba(219,227,240,.8);
    }
    .nav { display: flex; align-items: center; justify-content: space-between; height: 72px; }
    .logo { display: flex; align-items: center; gap: 12px; font-weight: 900; letter-spacing: -.03em; }
    .logoMark { width: 38px; height: 38px; border-radius: 13px; background: linear-gradient(135deg, var(--blue), #7d9bff); box-shadow: 0 12px 28px rgba(47,107,255,.25); }
    .navLinks { display: flex; gap: 18px; color: var(--muted); font-weight: 700; font-size: 14px; }
    .hero { padding: 74px 0 38px; }
    .heroGrid { display: grid; grid-template-columns: 1.02fr .98fr; gap: 34px; align-items: center; }
    .eyebrow { display: inline-flex; align-items: center; gap: 8px; padding: 8px 13px; border: 1px solid var(--line); border-radius: 999px; background: #fff; font-size: 13px; color: var(--muted); font-weight: 800; }
    .dot { width: 8px; height: 8px; border-radius: 999px; background: var(--orange); }
    h1 { margin: 22px 0 16px; font-size: clamp(40px, 6vw, 70px); line-height: 1.02; letter-spacing: -.06em; }
    .lead { font-size: 19px; color: #46546d; max-width: 680px; margin: 0 0 26px; }
    .heroActions { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn { border: 0; border-radius: 16px; padding: 14px 18px; font-weight: 900; cursor: pointer; transition: .18s ease; display: inline-flex; align-items: center; justify-content: center; gap: 9px; }
    .btnPrimary { background: var(--navy); color: #fff; box-shadow: 0 14px 32px rgba(19,38,75,.25); }
    .btnPrimary:hover { transform: translateY(-1px); }
    .btnSoft { background: #fff; color: var(--navy); border: 1px solid var(--line); }
    .demoCard { background: rgba(255,255,255,.84); border: 1px solid rgba(219,227,240,.9); border-radius: var(--radius); padding: 22px; box-shadow: var(--shadow); }
    .choiceGrid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 18px 0; }
    .choice { background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 16px; }
    .choice strong { display: block; font-size: 18px; margin-bottom: 4px; }
    .choice p { margin: 0; color: var(--muted); font-size: 14px; }
    .craft { border-color: rgba(47,107,255,.38); background: linear-gradient(180deg, #fff, var(--blue2)); }
    .zip { background: linear-gradient(180deg, #fff, var(--mint)); }
    .section { padding: 46px 0; }
    .panel { background: var(--card); border: 1px solid var(--line); border-radius: 28px; box-shadow: var(--shadow); overflow: hidden; }
    .panelHead { padding: 26px 28px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
    .panelHead h2 { margin: 0; font-size: 28px; letter-spacing: -.04em; }
    .badge { padding: 7px 11px; border-radius: 999px; background: var(--yellow); color: #7a4a00; font-size: 13px; font-weight: 900; }
    .tool { display: grid; grid-template-columns: 1fr 1fr; min-height: 560px; }
    .inputBox, .outputBox { padding: 26px; }
    .inputBox { border-right: 1px solid var(--line); background: #fbfcff; }
    label { display: block; font-weight: 900; margin-bottom: 10px; }
    textarea { width: 100%; min-height: 320px; resize: vertical; border: 1px solid var(--line); border-radius: 18px; padding: 16px; font: inherit; line-height: 1.62; outline: none; background: #fff; }
    textarea:focus { border-color: rgba(47,107,255,.65); box-shadow: 0 0 0 4px rgba(47,107,255,.12); }
    .modeRow { display: flex; gap: 10px; margin: 15px 0; flex-wrap: wrap; }
    .pill { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 9px 12px; cursor: pointer; font-weight: 900; color: var(--muted); }
    .pill.active { color: #fff; background: var(--blue); border-color: var(--blue); }
    .sampleRow { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
    .sample { font-size: 13px; border: 1px dashed #b9c5d8; background: #fff; color: #4b5870; border-radius: 999px; padding: 8px 11px; cursor: pointer; }
    .resultCard { min-height: 424px; border: 1px solid var(--line); border-radius: 18px; background: #0f1c37; color: #edf4ff; padding: 18px; white-space: pre-wrap; overflow: auto; line-height: 1.68; font-size: 14px; }
    .resultTitle { font-weight: 900; font-size: 18px; margin: 0 0 10px; }
    .notice { color: var(--muted); font-size: 14px; margin: 9px 0 14px; }
    .metricGrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 14px 0; }
    .metric { border: 1px solid var(--line); background: #fff; border-radius: 14px; padding: 12px; }
    .metric small { display: block; color: var(--muted); font-weight: 800; }
    .metric b { font-size: 18px; }
    .cards3 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
    .miniCard { background: #fff; border: 1px solid var(--line); border-radius: 22px; padding: 20px; box-shadow: 0 12px 34px rgba(19,38,75,.07); }
    .miniCard h3 { margin: 0 0 8px; font-size: 20px; letter-spacing: -.03em; }
    .miniCard p { margin: 0; color: var(--muted); }
    .pricing { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
    .price { background: #fff; border: 1px solid var(--line); border-radius: 22px; padding: 20px; }
    .price.featured { border-color: rgba(47,107,255,.5); box-shadow: var(--shadow); }
    .price h3 { margin: 0 0 4px; }
    .amount { font-size: 26px; font-weight: 900; margin: 10px 0; }
    .price ul { margin: 12px 0 0; padding-left: 18px; color: var(--muted); }
    .leadForm { display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; margin-top: 18px; }
    input, select { border: 1px solid var(--line); border-radius: 14px; padding: 13px; font: inherit; background: #fff; }
    footer { padding: 40px 0 56px; color: var(--muted); font-size: 13px; }
    .toast { position: fixed; right: 18px; bottom: 18px; background: var(--navy); color: #fff; padding: 13px 16px; border-radius: 14px; box-shadow: var(--shadow); display: none; z-index: 99; }
    @media (max-width: 860px) {
      .heroGrid, .tool { grid-template-columns: 1fr; }
      .inputBox { border-right: 0; border-bottom: 1px solid var(--line); }
      .choiceGrid, .cards3, .pricing, .leadForm { grid-template-columns: 1fr; }
      .navLinks { display: none; }
      .metricGrid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap nav">
      <a class="logo" href="#top"><span class="logoMark"></span><span>PromptZip</span></a>
      <div class="navLinks"><a href="#tool">실행하기</a><a href="#why">차이점</a><a href="#pricing">요금제</a></div>
    </div>
  </div>

  <main id="top">
    <section class="hero">
      <div class="wrap heroGrid">
        <div>
          <span class="eyebrow"><span class="dot"></span> V47 · AI별 프롬프트 언어 최적화</span>
          <h1>대충 적어도,<br>AI가 알아듣는 질문으로.</h1>
          <p class="lead">PromptCraft는 키워드와 아이디어를 GPT, Claude, Gemini, Genspark AI 각각의 사용 방식에 맞춘 완성형 프롬프트로 바꿉니다. 입력 언어도 반영하고, 이미 긴 프롬프트는 PromptZip으로 의미를 유지한 채 압축할 수 있습니다.</p>
          <div class="heroActions">
            <a class="btn btnPrimary" href="#tool">무료로 실행하기</a>
            <a class="btn btnSoft" href="#why">무엇이 바뀌었나요?</a>
          </div>
        </div>
        <div class="demoCard">
          <div class="badge">자동 판단</div>
          <div class="choiceGrid">
            <div class="choice craft"><strong>PromptCraft</strong><p>“사이트 만들고 싶어”처럼 대충 쓴 생각을 역할·목표·조건·출력형식이 있는 질문으로 변환합니다.</p></div>
            <div class="choice zip"><strong>PromptZip</strong><p>이미 긴 프롬프트가 있을 때 중복 표현을 줄이고 핵심 조건 중심으로 재구성합니다.</p></div>
          </div>
          <p class="notice">이제 “만들고 싶어 / 설계해줘 / 기획해줘” 같은 입력은 Craft로 전환되며, GPT·Claude·Gemini·Genspark AI별 프롬프트 언어와 출력 구조를 다르게 반영합니다.</p>
        </div>
      </div>
    </section>

    <section id="tool" class="section">
      <div class="wrap panel">
        <div class="panelHead">
          <h2>프롬프트 변환기</h2>
          <span class="badge">Craft 우선 · AI별 구조 최적화</span>
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
          <div class="miniCard"><h3>1. 실패 입력 방지</h3><p>짧은 아이디어를 억지로 압축해서 같은 말을 반복하는 문제를 줄였습니다.</p></div>
          <div class="miniCard"><h3>2. Craft가 메인</h3><p>일반 사용자가 가장 많이 원하는 “좋은 질문 만들기”를 첫 번째 기능으로 올렸습니다.</p></div>
          <div class="miniCard"><h3>3. Zip은 명확한 상황에만</h3><p>이미 긴 프롬프트가 있을 때만 압축 기능이 자연스럽게 작동합니다.</p></div>
          <div class="miniCard"><h3>4. Genspark AI용</h3><p>리서치 목표, 조사 범위, 비교 기준, 최신성 확인, 최종 산출물이 분리된 질문으로 변환합니다.</p></div>
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
      <p>PromptZip __APP_VERSION__</p>
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
    port = int(os.getenv("PORT", "8817"))
    app.run(host="0.0.0.0", port=port, debug=False)
