# PromptZip V44 - choice guide readability polish
# No external packages required. Run: python app.py

from http.server import BaseHTTPRequestHandler, HTTPServer
import json, os, csv, time, re, urllib.parse
from datetime import datetime

PORT = int(os.environ.get('PORT', '8816'))
SITE_URL = os.environ.get('SITE_URL', f'http://127.0.0.1:{PORT}')
FREE_DAILY_LIMIT_ZIP = int(os.environ.get('FREE_DAILY_LIMIT_ZIP', '3'))
FREE_DAILY_LIMIT_CRAFT = int(os.environ.get('FREE_DAILY_LIMIT_CRAFT', '3'))
ENFORCE_FREE_LIMIT = os.environ.get('ENFORCE_FREE_LIMIT', 'false').lower() == 'true'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, 'exports')
os.makedirs(EXPORT_DIR, exist_ok=True)
LEADS_CSV = os.path.join(EXPORT_DIR, 'payment_interest_leads_v44.csv')
ZIP_HISTORY_JSONL = os.path.join(EXPORT_DIR, 'zip_history_v44.jsonl')
CRAFT_HISTORY_JSONL = os.path.join(EXPORT_DIR, 'craft_history_v44.jsonl')
DAILY_USAGE_JSON = os.path.join(EXPORT_DIR, 'daily_usage_v44.json')

PROVIDERS = {
    'openai': {
        'label': 'OpenAI GPT', 'models': ['gpt-4.1-mini', 'gpt-4.1', 'gpt-5-mini', 'gpt-5.5'],
        'input_per_1k': 0.002, 'output_per_1k': 0.008, 'cached_factor': 0.25,
        'thinking_in_output': False, 'tool_call_cost': 0.0005, 'search_cost': 0.005,
    },
    'claude': {
        'label': 'Claude', 'models': ['claude-3.5-haiku', 'claude-3.5-sonnet', 'claude-opus'],
        'input_per_1k': 0.003, 'output_per_1k': 0.015, 'cached_factor': 0.10,
        'thinking_in_output': False, 'tool_call_cost': 0.0007, 'search_cost': 0.010,
    },
    'gemini': {
        'label': 'Gemini', 'models': ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash'],
        'input_per_1k': 0.0015, 'output_per_1k': 0.006, 'cached_factor': 0.20,
        'thinking_in_output': True, 'tool_call_cost': 0.0004, 'search_cost': 0.006,
    }
}

STOPWORDS = ['좀','정말','굉장히','그리고','또한','가능하면','반드시','최대한','약간','이런식으로','해주세요','해줘','작성해줘','만들어줘','부탁해','please','kindly','really','just','also']
FORMAT_TERMS = ['표','table','bullet','bullets','목록','list','json','csv','markdown','보고서','report','요약','summary','헤드라인','headline','CTA','카드','card']
HIGH_VALUE_KO = ['표','요약','분석','정리','비교','원인','해결책','단계','출력','형식','영어','한글','동의어','어법','어휘','품질','비용','절감','보고서','리포트','목록','예시','제약','조건','빈칸','흐름','출제','채점표','내신','간결','혜택','사용 상황','걱정','비교 우위','과장','타깃','핵심 메시지','채널','실행안','영업이익','현금흐름','예산','매일','과제','점검','책임','자동 갱신','첫 문장']
HIGH_VALUE_EN = ['summary','analyze','analysis','compare','cause','solution','action','headline','benefit','CTA','tone','preserve','include','exclude','format','bullet','report','risk','deadline','owner','quality','cost','jargon','recommended actions','revenue risks','churn causes']
COUNT_WORDS = 'one|two|three|four|five|six|seven|eight|nine|ten|first|second|third'


def approx_tokens(text):
    text = text or ''
    korean = len(re.findall(r'[가-힣]', text))
    ascii_words = len(re.findall(r'[A-Za-z0-9_]+', text))
    symbols = len(re.findall(r'[^\w\s가-힣]', text))
    return max(1, int(korean / 2.2 + ascii_words * 1.15 + symbols * 0.35))


def sentence_split(text):
    parts = re.split(r'(?<=[.!?。！？])\s+|\n+', (text or '').strip())
    return [p.strip() for p in parts if p.strip()]


def _clean(s):
    s = re.sub(r'\s+', ' ', (s or '')).strip(' ,.;:。')
    for sw in STOPWORDS:
        s = re.sub(r'\b'+re.escape(sw)+r'\b', '', s, flags=re.I) if re.match(r'[A-Za-z]+$', sw) else s.replace(sw, '')
    return re.sub(r'\s+', ' ', s).strip(' ,.;:。')


def _unique_append(items, value, label='조건'):
    value = _clean(value)
    if not value or len(value) < 2:
        return
    low = value.lower()
    for _, v in items:
        if low == v.lower() or low in v.lower():
            return
    items.append((label, value))


def extract_constraints(text):
    text = text or ''
    slots = []
    add = lambda v, label='조건': _unique_append(slots, v, label)

    for m in re.findall(r'([가-힣A-Za-z/·\- ]{0,18}\d+\s*(?:개|가지|단계|회|문항|페이지|줄|분|초|tokens?|토큰|options?|headlines?|benefits?|actions?|steps?)[가-힣A-Za-z/·\- ]{0,14})', text, flags=re.I):
        add(m, '수량조건')
    for m in re.findall(r'\b((?:'+COUNT_WORDS+r')\s+(?:options?|headlines?|benefits?|bullets?|actions?|steps?|paragraphs?|examples?))\b', text, flags=re.I):
        add(m, '수량조건')

    phrase_patterns = [
        r'실제 출제 경향 중심', r'원문 흐름[을 ]*유지', r'어휘 주요 포인트', r'어법 포인트', r'순서\s*/\s*삽입 포인트',
        r'뜻과 동의어', r'쉬운 단어[^,.。\n]*제외', r'전문 용어[^,.。\n]*(?:줄이고|줄이기|최소화)',
        r'이전 달[^,.。\n]*비교[^,.。\n]*', r'임원 보고용', r'불확실한 항목[^,.。\n]*미확인',
        r'원문에 없는 내용[^,.。\n]*추측하지', r'결정사항', r'담당자', r'마감일', r'리스크', r'준비물',
        r'불만 유형', r'원인 추정', r'해결책\s*\d+\s*가지', r'표로?\s*정리', r'표 포함', r'간결(?:하게)?',
        r'빈칸', r'고등학교 내신', r'채점표', r'핵심 혜택', r'사용 상황', r'구매 전 걱정 해소', r'걱정 해소',
        r'비교 우위', r'과장 광고[^,.。\n]*(?:않게|금지|피해)', r'타깃 고객', r'핵심 메시지', r'채널별 실행안',
        r'예상 리스크', r'성과 지표', r'과장된 표현[^,.。\n]*(?:피해|피해서|금지)', r'영업이익', r'현금흐름', r'예산 대비 차이',
        r'매일 해야 할 과제', r'점검 기준', r'책임 제한', r'자동 갱신 조건', r'첫 문장[^,.。\n]*문제'
    ]
    for pat in phrase_patterns:
        for m in re.findall(pat, text, flags=re.I):
            add(m, '핵심조건')

    en_patterns = [
        r'preserve [^,.\n]+', r'keep the tone [^,.\n]+', r'keep [^,.\n]+ unchanged',
        r'do not [^,.\n]+', r"don't [^,.\n]+", r'without [^,.\n]+', r'no [^,.\n]+',
        r'concise CTA', r'core value proposition', r'premium but friendly', r'customer numbers',
        r'revenue risks', r'churn causes', r'one-paragraph CEO summary', r'English executive summary'
    ]
    for pat in en_patterns:
        for m in re.findall(pat, text, flags=re.I):
            add(m, '핵심조건')

    for m in re.findall(r'\binclude\b([^.!?\n]+)', text, flags=re.I):
        for item in re.split(r',| and ', m):
            add(item, '포함조건')

    for s in sentence_split(text):
        if any(k in s for k in HIGH_VALUE_KO + ['포함','제외','유지']):
            for item in re.split(r',|그리고|및|/|;|\s+-\s+', s):
                item=_clean(item)
                if 2 <= len(item) <= 32 and any(k.lower() in item.lower() for k in HIGH_VALUE_KO + HIGH_VALUE_EN + ['유지','제외','포함']):
                    add(item, '세부조건')

    for kw in FORMAT_TERMS + ['GPT','Claude','Gemini','API','영어','한글','어휘','어법','동의어','비용','절감','headline','benefit','CTA','tone','table','summary','report']:
        if kw.lower() in text.lower():
            add(kw, '핵심어')

    raw = []
    for s in sentence_split(text):
        for item in re.split(r',|;|/| 그리고 | 또한 | and | but | with |\s+-\s+', s):
            c = _clean(item)
            if len(c) >= 3 and c not in raw:
                raw.append(c)
    return slots, raw[:18]


def _task_anchor(text, clauses):
    anchor = clauses[0] if clauses else _clean((text or '')[:140])
    replacements = {'분석해서':'분석:', '정리하고':'정리,', '추정하고':'추정,', '작성해줘':'작성', '만들어줘':'작성', '해줘':'', '간결하게':'간결'}
    for a,b in replacements.items(): anchor = anchor.replace(a,b)
    low = anchor.lower()
    if '고객 문의 데이터' in anchor: return '고객 문의 데이터 분석'
    if '회의록' in anchor: return '회의록 요약'
    if '계약서' in anchor: return '계약서 검토'
    if '영어 지문' in anchor and ('내신' in text or '채점표' in text): return '영어 지문 내신 채점표 작성'
    if 'monthly analytics report' in low: return 'monthly analytics report analysis'
    if 'english executive summary' in low: return 'English executive summary'
    return _clean(anchor)


def _compact_term(v):
    v = _clean(v)
    replacements = [
        (r'해결책\s*(\d+\s*가지).*', r'해결책 \1'),
        (r'원문에 없는 내용.*?추측하지.*', '원문 없는 내용 추측 금지'),
        (r'불확실한 항목.*?미확인.*', '불확실 항목 미확인 표시'),
        (r'실제 출제 경향 중심으로 원문 흐름을 유지.*', '실제 출제 경향 중심, 원문 흐름 유지'),
        (r'어휘는 뜻과 동의어까지 포함.*', '어휘 뜻·동의어 포함'),
        (r'너무 쉬운 단어.*제외.*', '쉬운 단어 제외'),
        (r'전문 용어.*?줄.*', '전문용어 최소화'),
        (r'과장 광고.*', '과장 금지'),
        (r'과장된 표현.*', '과장 표현 금지'),
    ]
    for pat, rep in replacements:
        v = re.sub(pat, rep, v, flags=re.I)
    return _clean(v)


def _slot_values(slots):
    out = []
    for label, v in slots:
        cv = _compact_term(v)
        if cv and cv.lower() not in [x.lower() for x in out]:
            out.append(cv)
    return out


def _coverage_score(original, compressed, required_terms):
    if not required_terms:
        return 1.0
    c = compressed.lower()
    covered = 0
    for term in required_terms:
        t = _compact_term(term).lower()
        if not t:
            covered += 1
            continue
        tokens = [x for x in re.split(r'\s+|/|·|,', t) if len(x) >= 2]
        if t in c or (tokens and sum(1 for x in tokens if x in c) / max(1, len(tokens)) >= 0.5):
            covered += 1
    return covered / max(1, len(required_terms))


def compress_prompt(text):
    slots, clauses = extract_constraints(text)
    values = _slot_values(slots)
    anchor = _task_anchor(text, clauses)
    required = values[:16]
    candidates = []
    if required:
        candidates.append(f"{anchor}: " + '; '.join(required[:12]) + '.')
        candidates.append(f"작업={anchor}; 조건=" + ', '.join(required[:14]) + '.')
        candidates.append(f"{anchor}. 포함: " + ', '.join(required[:10]) + '. 누락 금지.')
    else:
        candidates.append(anchor + '.')
    original_tokens = approx_tokens(text)
    best = None
    for cand in candidates:
        ct = approx_tokens(cand)
        coverage = _coverage_score(text, cand, required)
        # score protects meaning first, then compression.
        score = coverage * 100 - ct * 0.12 + max(0, original_tokens - ct) * 0.08
        if best is None or score > best[0]:
            best = (score, cand, coverage)
    compressed = best[1]
    coverage = best[2]
    if coverage < 0.92:
        compressed = f"{anchor}: " + '; '.join(required[:16]) + '.'
        coverage = _coverage_score(text, compressed, required)
    # avoid expanding short prompts too much
    if approx_tokens(compressed) >= original_tokens and original_tokens < 45:
        compressed = _clean(anchor)
        coverage = max(coverage, 0.95)
    return compressed, slots, required, round(coverage, 3)


def estimate_cost(input_tokens, compressed_tokens, provider, opts):
    p = PROVIDERS.get(provider, PROVIDERS['openai'])
    output_ratio = float(opts.get('output_ratio', 1.7) or 1.7)
    cache_pct = max(0, min(100, float(opts.get('cache_pct', 0) or 0))) / 100
    thinking_tokens = max(0, int(float(opts.get('thinking_tokens', 0) or 0)))
    search_calls = max(0, int(float(opts.get('search_calls', 0) or 0)))
    tool_calls = max(0, int(float(opts.get('tool_calls', 0) or 0)))
    batch = bool(opts.get('batch', False))
    regional = bool(opts.get('regional', False))
    def bill(inp):
        cached = inp * cache_pct
        regular = inp - cached
        out = int(inp * output_ratio + thinking_tokens)
        cost = regular/1000*p['input_per_1k'] + cached/1000*p['input_per_1k']*p['cached_factor'] + out/1000*p['output_per_1k']
        cost += search_calls * p['search_cost'] + tool_calls * p['tool_call_cost']
        if batch: cost *= 0.5
        if regional: cost *= 1.15
        return cost, out
    orig, orig_out = bill(input_tokens)
    comp, comp_out = bill(compressed_tokens)
    return {
        'provider_label': p['label'], 'original_cost': round(orig, 6), 'compressed_cost': round(comp, 6),
        'saving_cost': round(max(0, orig-comp), 6), 'estimated_original_output_tokens': orig_out,
        'estimated_compressed_output_tokens': comp_out, 'batch_discount_applied': batch, 'regional_premium_applied': regional
    }

# PromptCraft: keyword -> refined prompt generator
CRAFT_TASKS = {
    'general': ('전문 AI 프롬프트 설계자', '사용자의 키워드를 바탕으로 원하는 결과물을 안정적으로 얻을 수 있는 고품질 질문을 설계한다.'),
    'research': ('리서치 애널리스트', '주제의 배경, 쟁점, 비교 기준, 근거 확인 방식을 포함해 조사형 질문을 설계한다.'),
    'marketing': ('브랜드 마케팅 전략가', '타깃, 가치제안, 톤, 채널, CTA가 살아 있는 마케팅 질문을 설계한다.'),
    'education': ('교육 콘텐츠 설계자', '학습 목표, 난도, 예시, 평가 기준이 드러나는 교육형 질문을 설계한다.'),
    'business': ('비즈니스 컨설턴트', '목표, 제약, 지표, 리스크, 실행안을 포함한 비즈니스 질문을 설계한다.'),
    'coding': ('시니어 소프트웨어 엔지니어', '요구사항, 입력/출력, 예외처리, 테스트 기준이 있는 개발 질문을 설계한다.'),
}
OUTPUT_BY_TASK = {
    'general': '핵심 답변 → 세부 설명 → 실행 가능한 다음 단계',
    'research': '요약 표 → 쟁점별 분석 → 근거 수준 → 추가 확인 질문',
    'marketing': '타깃 정의 → 핵심 메시지 → 문구 후보 → CTA → 주의할 표현',
    'education': '학습 목표 → 설명 → 예시 → 연습문제 → 평가 기준',
    'business': '문제 정의 → 원인 분석 → 선택지 비교 → 추천안 → 리스크와 KPI',
    'coding': '접근 방식 → 코드 → 설명 → 테스트 케이스 → 개선 포인트',
}
TONE_LABELS = {'professional':'전문적이고 명확하게','friendly':'친절하고 자연스럽게','premium':'프리미엄하고 세련되게','concise':'간결하고 직접적으로','creative':'창의적이고 설득력 있게'}


def split_keywords(s):
    raw = re.split(r',|\n|/|;|\s{2,}', s or '')
    items = []
    for x in raw:
        x = _clean(x)
        if x and x.lower() not in [i.lower() for i in items]:
            items.append(x)
    if not items and s:
        items = [_clean(s)]
    return items[:20]


def craft_prompt(keywords, goal='', audience='', task='general', tone='professional', output_format='', ask_questions=True, detail='balanced'):
    kws = split_keywords(keywords)
    role, task_goal = CRAFT_TASKS.get(task, CRAFT_TASKS['general'])
    tone_text = TONE_LABELS.get(tone, tone)
    goal_text = _clean(goal) or task_goal
    audience_text = _clean(audience) or '일반 사용자'
    output_text = _clean(output_format) or OUTPUT_BY_TASK.get(task, OUTPUT_BY_TASK['general'])
    question_rule = '정보가 부족하면 답변 전에 필요한 확인 질문을 먼저 3개 이내로 제시하라.' if ask_questions else '정보가 부족한 부분은 합리적 가정으로 표시하고 진행하라.'
    if detail == 'compact':
        prompt = f"역할: {role}. 목적: {goal_text}. 키워드: {', '.join(kws)}. 대상: {audience_text}. 톤: {tone_text}. 출력: {output_text}. 조건: 핵심 조건 누락 금지, 추측은 가정으로 표시, {question_rule}"
    elif detail == 'creative':
        prompt = f"당신은 {role}입니다. 다음 키워드({', '.join(kws)})를 바탕으로 {audience_text}이 바로 활용할 수 있는 결과물을 만들어주세요. 목표는 {goal_text}입니다. 답변은 {tone_text} 작성하고, {output_text} 구조로 제시해주세요. 흔한 설명보다 차별화된 관점, 실행 가능한 예시, 주의해야 할 함정까지 포함해주세요. {question_rule}"
    else:
        prompt = f"당신은 {role}입니다.\n\n[입력 키워드]\n- " + "\n- ".join(kws) + f"\n\n[목표]\n{goal_text}\n\n[대상 독자]\n{audience_text}\n\n[작성 톤]\n{tone_text}\n\n[출력 형식]\n{output_text}\n\n[작업 조건]\n1. 키워드의 의도를 임의로 축소하지 말고, 필요한 맥락을 보강하세요.\n2. 애매한 표현은 구체적인 기준과 질문으로 바꾸세요.\n3. 결과물이 바로 사용 가능하도록 표, 목록, 예시를 적절히 포함하세요.\n4. 확실하지 않은 내용은 단정하지 말고 가정 또는 확인 필요로 표시하세요.\n5. {question_rule}"
    score = min(0.99, 0.72 + min(0.14, len(kws)*0.015) + (0.06 if goal else 0) + (0.04 if audience else 0) + (0.03 if output_format else 0))
    return prompt, kws, round(score, 3)


def craft_variants(keywords, goal='', audience='', task='general', tone='professional', output_format='', ask_questions=True):
    variants = []
    for name, detail in [('정밀 질문형','balanced'),('짧은 실전형','compact'),('창의 확장형','creative')]:
        p, kws, score = craft_prompt(keywords, goal, audience, task, tone, output_format, ask_questions, detail)
        variants.append({'name': name, 'prompt': p, 'tokens': approx_tokens(p), 'quality_score': score})
    best = sorted(variants, key=lambda x: (x['quality_score'], -x['tokens']), reverse=True)[0]
    return best, variants, split_keywords(keywords)


def today_key(): return datetime.now().strftime('%Y-%m-%d')

def load_daily_usage():
    if not os.path.exists(DAILY_USAGE_JSON): return {}
    try:
        with open(DAILY_USAGE_JSON, encoding='utf-8') as f: return json.load(f)
    except Exception: return {}

def check_and_increment_usage(ip, product):
    data = load_daily_usage(); day = today_key(); key = f'{day}:{ip}:{product}'
    limit = FREE_DAILY_LIMIT_CRAFT if product == 'craft' else FREE_DAILY_LIMIT_ZIP
    used = int(data.get(key, 0))
    if ENFORCE_FREE_LIMIT and used >= limit: return False, 0, used
    data[key] = used + 1
    with open(DAILY_USAGE_JSON, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
    return True, max(0, limit-data[key]), data[key]


def save_jsonl(path, row):
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')

def load_jsonl(path, limit=50):
    if not os.path.exists(path): return []
    rows=[]
    with open(path, encoding='utf-8') as f:
        for line in f:
            try: rows.append(json.loads(line))
            except Exception: pass
    return list(reversed(rows[-limit:]))

def history_csv_bytes(path):
    rows = load_jsonl(path, 1000)
    if not rows: return 'created_at,type,provider,metric,quality,prompt_preview\n'.encode('utf-8-sig')
    import io
    out=io.StringIO()
    fieldnames=['created_at','type','provider_label','token_saving_pct','quality_score','coverage','prompt_preview','compressed_prompt','crafted_prompt']
    w=csv.DictWriter(out, fieldnames=fieldnames, extrasaction='ignore')
    w.writeheader()
    for r in rows: w.writerow(r)
    return out.getvalue().encode('utf-8-sig')

HTML = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PromptZip | AI 질문 최적화 & 토큰 절감</title>
<link rel="icon" href="/favicon.svg">
<style>
:root{
  --ink:#0b1220;--sub:#42526b;--muted:#667085;--line:#e2e8f0;--soft:#f8fafc;
  --blue:#2563eb;--blue2:#1d4ed8;--violet:#7c3aed;--mint:#10b981;--teal:#14b8a6;--amber:#f59e0b;
  --card:#ffffff;--radius:24px;--shadow:0 22px 58px rgba(15,23,42,.09);--shadow2:0 12px 28px rgba(15,23,42,.07);
}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:var(--ink);background:#f6f8fc;word-break:keep-all;-webkit-font-smoothing:antialiased}body:before{content:"";position:fixed;inset:0;z-index:-2;background:radial-gradient(circle at 8% 0%,rgba(37,99,235,.15),transparent 32%),radial-gradient(circle at 92% 6%,rgba(16,185,129,.12),transparent 32%),linear-gradient(180deg,#fbfdff 0%,#f6f8fc 58%,#ffffff 100%)}body:after{content:"";position:fixed;inset:0;z-index:-1;opacity:.2;background-image:linear-gradient(rgba(15,23,42,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(15,23,42,.055) 1px,transparent 1px);background-size:44px 44px}
p{margin:0;color:var(--sub);line-height:1.78;text-align:justify;text-justify:inter-word}.fine{font-size:13px;color:#718096}.center{text-align:center}.hidden{display:none!important}
.notice{background:#0b1220;color:#dbeafe;text-align:center;padding:10px 16px;font-size:13px;letter-spacing:-.1px}.notice b{color:#fff}.notice span{color:#86efac;font-weight:800}
header{position:sticky;top:0;z-index:40;background:rgba(248,250,252,.82);backdrop-filter:blur(18px);border-bottom:1px solid rgba(226,232,240,.9)}.nav{max-width:1180px;margin:0 auto;padding:15px 22px;display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{display:flex;align-items:center;gap:12px;font-size:22px;font-weight:950;letter-spacing:-.7px}.logo{width:44px;height:44px;border-radius:16px;background:linear-gradient(135deg,#0f172a,#2563eb 56%,#10b981);display:grid;place-items:center;color:#fff;box-shadow:0 16px 32px rgba(37,99,235,.22)}.brand small{display:block;font-size:10.5px;letter-spacing:.9px;text-transform:uppercase;color:#6b7280;margin-top:2px}.nav-actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.nav-actions button{border:1px solid #dce8f7;background:#fff;color:#14335a;border-radius:999px;padding:10px 14px;font-weight:850;cursor:pointer;transition:.18s}.nav-actions button:hover{transform:translateY(-1px);box-shadow:var(--shadow2)}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}.section{padding:42px 0}.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:36px;align-items:center;padding:56px 0 36px}.eyebrow{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.badge{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:900;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8}.badge.green{border-color:#bbf7d0;background:#ecfdf5;color:#047857}.badge.amber{border-color:#fde68a;background:#fffbeb;color:#92400e}.badge.dark{background:#111827;color:#fff;border-color:#111827}
h1{margin:0 0 18px;font-size:56px;line-height:1.03;letter-spacing:-2.9px}.gradient{background:linear-gradient(135deg,#2563eb 0%,#7c3aed 52%,#10b981 100%);-webkit-background-clip:text;background-clip:text;color:transparent}.lead{font-size:18px;max-width:720px;color:#42526b}.cta{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.btn{border:0;border-radius:16px;padding:14px 18px;font-weight:950;cursor:pointer;transition:.18s;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:8px}.btn:hover{transform:translateY(-2px);box-shadow:0 18px 36px rgba(15,23,42,.14)}.btn-primary{background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff}.btn-green{background:linear-gradient(135deg,#10b981,#06b6d4);color:#fff}.btn-amber{background:linear-gradient(135deg,#f59e0b,#fb7185);color:#fff}.btn-ghost{background:#fff;color:#0f172a;border:1px solid #e2e8f0}.btn-soft{background:#edf6ff;color:#17406d;border:1px solid #d9e8fa}
.card,.panel,.preview{background:rgba(255,255,255,.92);border:1px solid rgba(226,232,240,.96);border-radius:var(--radius);box-shadow:var(--shadow)}.preview{padding:24px}.device{background:#0e1729;border-radius:22px;padding:18px;color:#dbeafe;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}.dots{display:flex;gap:7px;margin-bottom:16px}.dots i{width:10px;height:10px;border-radius:50%;display:block;background:#fb7185}.dots i:nth-child(2){background:#f59e0b}.dots i:nth-child(3){background:#10b981}.ba{display:grid;grid-template-columns:1fr 1fr;gap:12px}.code{border-radius:16px;background:#111827;border:1px solid rgba(255,255,255,.08);padding:14px;color:#cbd5e1;font-size:12.5px;line-height:1.6}.code b{display:block;color:#fff;margin-bottom:8px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.stat{background:#fff;border:1px solid #e5eaf3;border-radius:18px;padding:15px;text-align:center}.stat b{display:block;font-size:23px;letter-spacing:-.7px}.stat span{font-size:12.5px;color:#64748b;font-weight:850}
.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:18px}.section-head h2{margin:0;font-size:34px;letter-spacing:-1.2px}.section-head p{max-width:620px;font-size:15px}.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.step{position:relative;overflow:hidden;padding:22px;border-radius:24px;background:#fff;border:1px solid #e5eaf3;box-shadow:var(--shadow2)}.step:before{content:"";position:absolute;inset:0 0 auto;height:4px;background:linear-gradient(90deg,#2563eb,#10b981)}.num{width:34px;height:34px;border-radius:13px;display:grid;place-items:center;background:#eff6ff;color:#1d4ed8;font-weight:950;margin-bottom:12px}.step b{display:block;margin-bottom:8px;font-size:17px}.step p{font-size:13.7px;line-height:1.75}.service-mark{display:inline-flex;align-items:center;border-radius:999px;padding:3px 9px;font-weight:950;white-space:nowrap}.service-mark.zip{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}.service-mark.craft{background:#ecfdf5;color:#047857;border:1px solid #bbf7d0}.choice-lines{display:grid;gap:8px;margin-top:10px}.choice-lines div{display:flex;align-items:center;justify-content:space-between;gap:10px;background:#f8fbff;border:1px solid #e5eaf3;border-radius:14px;padding:9px 10px}.choice-lines em{font-style:normal;color:#64748b;font-size:12.5px;font-weight:800;text-align:right}.flow-note{margin-top:18px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:18px;padding:14px 16px;font-size:14px;line-height:1.7;text-align:justify}
.tool{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}.panel{padding:26px}.panel h3{margin:0 0 8px;font-size:25px;letter-spacing:-.8px}.panel-desc{margin-bottom:18px}.tabs{display:flex;gap:10px;margin:18px 0}.tab{flex:1;border:1px solid #dbe7f5;background:#fff;color:#334155;border-radius:16px;padding:13px 14px;font-weight:950;cursor:pointer}.tab.active{background:#0f172a;color:#fff;border-color:#0f172a}label{display:block;font-size:13.5px;color:#334155;font-weight:900;margin:13px 0 7px}input,select,textarea{width:100%;border:1px solid #d6e2f0;background:#fff;border-radius:16px;padding:13px 14px;font-size:15px;outline:none;transition:.15s}textarea{min-height:170px;resize:vertical;line-height:1.65}input:focus,select:focus,textarea:focus{border-color:#60a5fa;box-shadow:0 0 0 4px rgba(96,165,250,.16)}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.advanced{border:1px solid #e3ebf6;border-radius:18px;padding:15px;margin:15px 0;background:#fbfdff}.advanced summary{cursor:pointer;font-weight:950;color:#12325d}.advanced p{font-size:13px;margin-top:10px}.result-empty{min-height:390px;border:1px dashed #cad7ea;border-radius:22px;display:grid;place-items:center;text-align:center;background:linear-gradient(180deg,#ffffff,#f8fbff);padding:28px}.result-empty b{display:block;font-size:19px;margin-bottom:8px}.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px}.metric{background:#f8fbff;border:1px solid #e5eaf3;border-radius:18px;padding:14px;text-align:center}.metric b{display:block;font-size:25px;color:#334155}.metric span{font-size:12.5px;color:#64748b;font-weight:850}.compressed{background:#0f172a;color:#e5edff;border-radius:18px;padding:18px;line-height:1.72;white-space:pre-wrap;word-break:break-word;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}.kept{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.pill{display:inline-flex;border-radius:999px;padding:7px 10px;background:#eff6ff;color:#1d4ed8;font-size:12.5px;font-weight:850;border:1px solid #bfdbfe}.history-item{background:#f8fbff;border:1px solid #e5eaf3;border-radius:16px;padding:12px;margin-top:9px}
.examples{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.example{padding:20px;border-radius:24px;background:#fff;border:1px solid #e5eaf3;box-shadow:var(--shadow2)}.example h3{margin:0 0 10px}.example .smallbox{background:#f8fafc;border:1px solid #e5eaf3;border-radius:14px;padding:12px;font-size:13px;line-height:1.65;margin-top:10px;color:#475569;text-align:justify}.calc{display:grid;grid-template-columns:1.1fr .9fr;gap:18px}.pricing{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.plan{position:relative;padding:22px;border-radius:26px;background:#fff;border:1px solid #e5eaf3;box-shadow:var(--shadow2)}.plan.highlight{border:2px solid #2563eb;transform:translateY(-4px);box-shadow:0 30px 70px rgba(37,99,235,.18)}.plan.bundle{background:linear-gradient(180deg,#0f172a,#172554);color:#fff;border-color:#0f172a}.plan.bundle p,.plan.bundle li{color:#dbeafe}.plan h3{margin:0 0 7px;font-size:22px}.price{font-size:30px;font-weight:950;letter-spacing:-1px;margin:8px 0 14px}.plan ul{margin:16px 0 0;padding-left:18px;color:#475569;line-height:1.9}.ribbon{position:absolute;right:18px;top:-12px;background:#2563eb;color:#fff;border-radius:999px;padding:7px 11px;font-size:12px;font-weight:950}.leadbox{margin-top:18px}.faq{display:grid;grid-template-columns:1fr 1fr;gap:14px}.faq-item{padding:18px;border-radius:20px;background:#fff;border:1px solid #e5eaf3}.faq-item b{display:block;margin-bottom:8px}.closing{background:linear-gradient(135deg,#0f172a,#1e3a8a 58%,#065f46);color:#fff}.closing p,.closing h2{color:#fff}.footer{padding:32px 0 44px;color:#64748b;text-align:center;font-size:13px}.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#0f172a;color:#fff;padding:12px 16px;border-radius:999px;box-shadow:var(--shadow);display:none;z-index:80}.mobile-only{display:none}
@media(max-width:980px){h1{font-size:42px}.hero,.tool,.calc{grid-template-columns:1fr}.flow,.pricing,.examples,.faq{grid-template-columns:1fr 1fr}.nav{align-items:flex-start}.nav-actions{display:none}.mobile-only{display:inline-flex}}
@media(max-width:640px){.wrap{padding:0 16px}.hero{padding-top:34px}.flow,.pricing,.examples,.faq,.grid2,.metric-grid,.stats,.ba{grid-template-columns:1fr}h1{font-size:34px}.section-head{display:block}.panel{padding:20px}.notice{font-size:12px}.tool{gap:14px}}


/* V44 readability and alignment polish: prevents cramped cards and text overlap. */
body{overflow-x:hidden;line-break:strict;overflow-wrap:break-word;}
.wrap,.nav,.hero,.tool,.flow,.pricing,.examples,.faq,.grid2,.metric-grid,.stats,.ba{min-width:0;}
.card,.panel,.preview,.step,.plan,.example,.faq-item,.metric,.stat,.code,.compressed{min-width:0;overflow-wrap:break-word;}
h1{font-size:clamp(38px,5vw,56px);line-height:1.06;letter-spacing:clamp(-2.7px,-.18vw,-1px);}
.lead{line-height:1.82;letter-spacing:-.1px;}
.section{padding:46px 0;}
.section-head{align-items:flex-start;}
.section-head h2{font-size:clamp(27px,3.2vw,34px);line-height:1.22;}
.section-head p,.lead,.panel-desc,.flow-note,.faq-item p,.example .smallbox,.fine{max-width:100%;text-align:justify;text-justify:inter-word;}
.step p,.choice-lines div,.metric span,.stat span,.badge,.plan li,.notice,.footer,.history-item{text-align:left;text-justify:auto;}
.flow{grid-template-columns:repeat(4,minmax(0,1fr));align-items:stretch;}
.step{display:flex;flex-direction:column;gap:0;min-height:214px;padding:23px 22px 24px;}
.step b{line-height:1.35;}
.step p{line-height:1.72;}
.num{flex:0 0 auto;}
.service-mark{display:inline-flex;vertical-align:baseline;line-height:1.25;margin:0 2px 2px 0;padding:3px 9px;}
.choice-lines{gap:9px;}
.choice-lines div{display:grid;grid-template-columns:minmax(96px,max-content) minmax(0,1fr);align-items:center;}
.choice-lines em{text-align:left;line-height:1.45;min-width:0;}
.tool{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:22px;}
.panel{padding:28px;}
.panel h3{line-height:1.28;}
.tabs{align-items:stretch;}
.tab{min-width:0;line-height:1.35;}
label{line-height:1.35;}
input,select,textarea{min-width:0;line-height:1.55;}
textarea{font-family:inherit;}
.grid2{grid-template-columns:repeat(2,minmax(0,1fr));}
.advanced{overflow:hidden;}
.advanced summary{line-height:1.5;}
.result-empty{min-height:410px;}
.metric-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
.metric{padding:15px 10px;}
.metric b{font-size:clamp(21px,2.4vw,26px);line-height:1.18;white-space:nowrap;}
.metric span{display:block;line-height:1.35;}
.compressed{line-height:1.78;overflow-wrap:anywhere;}
.kept,.eyebrow,.nav-actions,.cta{align-items:center;}
.btn{white-space:normal;text-align:center;line-height:1.35;min-height:46px;}
.examples{grid-template-columns:repeat(3,minmax(0,1fr));}
.example{display:flex;flex-direction:column;}
.example h3{line-height:1.35;}
.calc{grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);}
.pricing{grid-template-columns:repeat(4,minmax(0,1fr));align-items:stretch;}
.plan{display:flex;flex-direction:column;min-height:100%;padding:24px 22px;}
.plan h3{line-height:1.25;}
.price{font-size:clamp(25px,2.6vw,30px);white-space:nowrap;}
.plan ul{line-height:1.85;margin-bottom:18px;}
.plan .btn{margin-top:auto;width:100%;}
.ribbon{max-width:calc(100% - 34px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.faq{grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch;}
.faq-item{min-height:150px;}
.closing .section-head{align-items:center;}
@media(max-width:1120px){.hero,.tool,.calc{grid-template-columns:1fr}.flow,.pricing,.examples,.faq{grid-template-columns:repeat(2,minmax(0,1fr));}.result-empty{min-height:300px}.panel{padding:24px}.plan.highlight{transform:none}}
@media(max-width:760px){.nav{padding:13px 16px}.brand{font-size:20px}.logo{width:40px;height:40px}.wrap{padding:0 16px}.section{padding:34px 0}.hero{padding:34px 0 24px}.flow,.pricing,.examples,.faq,.grid2,.metric-grid,.stats,.ba{grid-template-columns:1fr}.choice-lines div{grid-template-columns:1fr;gap:4px}.choice-lines em{text-align:left}.section-head{display:block}.panel{padding:20px}.tabs{flex-direction:column}.notice{font-size:12px;line-height:1.55}.metric-grid{gap:8px}.closing .section-head{display:block}.btn{width:100%}.cta .btn{width:auto;min-width:160px}}
@media(max-width:430px){h1{font-size:32px}.lead{font-size:16px}.badge{font-size:11.5px;padding:7px 10px}.step{min-height:0}.price{font-size:24px}.cta .btn{width:100%}}


/* V44: turn inline service labels into clear choice cards. */
.choice-selector{display:grid;grid-template-columns:1fr;gap:10px;margin-top:12px;}
.choice-card{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:start;padding:13px 14px;border-radius:18px;border:1px solid #e5eaf3;background:linear-gradient(180deg,#ffffff,#f8fbff);box-shadow:0 10px 22px rgba(15,23,42,.045);}
.choice-card.zip{border-color:#bfdbfe;background:linear-gradient(180deg,#ffffff,#eff6ff);}
.choice-card.craft{border-color:#bbf7d0;background:linear-gradient(180deg,#ffffff,#ecfdf5);}
.choice-card strong{display:block;font-size:14px;line-height:1.35;margin-bottom:3px;color:#0f172a;letter-spacing:-.2px;}
.choice-card small{display:block;color:#64748b;font-size:12.7px;line-height:1.55;font-weight:720;text-align:left;}
.choice-icon{width:38px;height:38px;border-radius:14px;display:grid;place-items:center;font-weight:950;letter-spacing:-.4px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.55);}
.choice-icon.zip{background:#dbeafe;color:#1d4ed8;}
.choice-icon.craft{background:#d1fae5;color:#047857;}
.choice-guide{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0 18px;}
.choice-guide .choice-card{min-height:94px;}
.inline-choice{margin:10px 0 18px;padding:13px 14px;border:1px solid #e5eaf3;border-radius:18px;background:#fbfdff;}
.inline-choice-title{display:block;font-size:13px;font-weight:950;color:#334155;margin-bottom:8px;}
.service-mark{box-shadow:none;}
.step .choice-selector{margin-top:auto;padding-top:8px;}
@media(max-width:760px){.choice-guide{grid-template-columns:1fr}.choice-card{grid-template-columns:auto 1fr}.choice-card small{font-size:12.5px}}

</style>
</head>
<body>
<div class="notice"><b>PromptZip</b>은 긴 프롬프트를 줄이고, <span>PromptCraft</span>는 키워드를 좋은 질문으로 바꿉니다.</div>
<header><div class="nav"><div class="brand"><div class="logo">Z</div><div>PromptZip<small>AI Prompt Optimizer</small></div></div><div class="nav-actions"><button onclick="scrollToId('flow')">사용 흐름</button><button onclick="scrollToId('tool')">무료 체험</button><button onclick="scrollToId('pricing')">요금제</button><button onclick="scrollToId('faq')">FAQ</button></div></div></header>
<main class="wrap">
<section class="hero"><div><div class="eyebrow"><span class="badge">GPT · Claude · Gemini</span><span class="badge green">의미 보존 압축</span><span class="badge amber">질문 고도화</span></div><h1>AI에게 더 좋은 질문을,<br><span class="gradient">더 적은 비용으로.</span></h1><p class="lead"><b>PromptZip</b>은 이미 쓴 긴 프롬프트를 의미가 흐트러지지 않게 줄이고, <b>PromptCraft</b>는 키워드만으로 더 섬세한 질문을 만들어줍니다. 처음 온 고객도 바로 이해하고 써볼 수 있도록 무료 체험 흐름을 단순하게 정리했습니다.</p><div class="cta"><button class="btn btn-primary" onclick="scrollToId('tool')">무료로 시작하기</button><button class="btn btn-ghost" onclick="scrollToId('flow')">어떻게 쓰나요?</button></div></div><div class="preview"><div class="device"><div class="dots"><i></i><i></i><i></i></div><div class="ba"><div class="code"><b>Before</b>고객 문의 데이터를 분석해서 불만 유형과 원인, 해결책 5가지를 표로 정리하고...</div><div class="code"><b>After</b>고객 문의 분석: 불만 유형, 원인, 해결책 5가지, 표 포함, 간결.</div></div><div class="stats"><div class="stat"><b>24%+</b><span>평균 절감 예시</span></div><div class="stat"><b>0.99</b><span>품질 점수 예시</span></div><div class="stat"><b>3 engines</b><span>과금 옵션</span></div></div></div></div></section>
<section class="section" id="flow"><div class="section-head"><h2>헷갈리지 않는 4단계 흐름</h2><p>처음 들어온 고객이 바로 선택할 수 있도록 두 기능을 문장 안에 섞지 않고, 선택 카드로 분리했습니다. 비용을 줄일 때는 PromptZip, 질문을 만들 때는 PromptCraft입니다.</p></div><div class="flow"><div class="step"><div class="num">1</div><b>목적 선택</b><p>먼저 내 상황에 맞는 기능을 고릅니다.</p><div class="choice-selector"><div class="choice-card zip"><span class="choice-icon zip">Zip</span><div><strong>긴 프롬프트를 줄이고 싶다면</strong><small>PromptZip · 의미 보존 압축</small></div></div><div class="choice-card craft"><span class="choice-icon craft">Craft</span><div><strong>키워드로 질문을 만들고 싶다면</strong><small>PromptCraft · 질문 고도화</small></div></div></div></div><div class="step"><div class="num">2</div><b>내용 입력</b><p>프롬프트나 키워드를 붙여넣고, 필요하면 OpenAI·Claude·Gemini 및 고급 과금 옵션을 조정합니다.</p></div><div class="step"><div class="num">3</div><b>결과 확인</b><p>절감률만 보지 않고 품질 점수, 핵심 조건 보존 여부, 예상 비용까지 함께 확인합니다.</p></div><div class="step"><div class="num">4</div><b>복사해서 사용</b><p>압축 프롬프트 또는 고급 질문을 복사해 실제 AI에 넣어 사용합니다.</p></div></div><div class="flow-note">처음 쓰는 고객은 기본값으로 바로 시작하고, 익숙한 사용자는 고급 과금 옵션을 열어 엔진별 조건을 조정하면 됩니다.</div></section>
<section class="section" id="tool"><div class="section-head"><h2>무료 체험</h2><p>왼쪽에서 목적을 선택하고 내용을 입력하세요. 오른쪽 결과창에서 절감률, 품질 점수, 생성된 질문을 바로 확인할 수 있습니다.</p></div><div class="tool"><div class="panel"><h3>1. 목적 선택</h3><div class="inline-choice"><span class="inline-choice-title">어떤 기능을 사용할까요?</span><div class="choice-guide"><div class="choice-card zip"><span class="choice-icon zip">Zip</span><div><strong>이미 긴 프롬프트가 있어요</strong><small>PromptZip으로 의미를 유지하며 압축합니다.</small></div></div><div class="choice-card craft"><span class="choice-icon craft">Craft</span><div><strong>키워드만 가지고 있어요</strong><small>PromptCraft로 더 좋은 질문을 만듭니다.</small></div></div></div></div><div class="tabs"><button class="tab active" id="tabZip" onclick="showMode('zip')">PromptZip</button><button class="tab" id="tabCraft" onclick="showMode('craft')">PromptCraft</button></div><div id="zipMode"><label>AI 엔진</label><select id="provider"><option value="openai">OpenAI GPT</option><option value="claude">Claude</option><option value="gemini">Gemini</option></select><details class="advanced"><summary>고급 과금 옵션 열기</summary><p>엔진별 캐시, thinking/reasoning, 검색, 도구 호출, batch 할인, 지역 프리미엄을 추정값으로 반영합니다.</p><div class="grid2"><div><label>캐시 적용 입력 비율(%)</label><input id="cache_pct" value="0" type="number"></div><div><label>예상 출력 배율</label><input id="output_ratio" value="1.7" type="number" step="0.1"></div><div><label>Thinking/Reasoning 토큰</label><input id="thinking_tokens" value="0" type="number"></div><div><label>검색/그라운딩 호출 수</label><input id="search_calls" value="0" type="number"></div><div><label>도구 호출 수</label><input id="tool_calls" value="0" type="number"></div><div><label>할인/프리미엄</label><select id="extra_flags"><option value="none">없음</option><option value="batch">Batch 할인</option><option value="regional">지역 프리미엄</option><option value="both">둘 다 반영</option></select></div></div></details><label>2. 긴 프롬프트 입력</label><textarea id="prompt_text" placeholder="긴 프롬프트를 붙여넣으세요. 예: 고객 문의 데이터를 분석해서 불만 유형, 원인, 해결책 5가지를 표로 정리해줘."></textarea><button class="btn btn-primary" onclick="optimize()">3. 압축 실행</button></div><div id="craftMode" class="hidden"><label>2. 키워드 입력</label><textarea id="craft_keywords" placeholder="예: 영어 내신, 어법, 순서삽입, 고2 수준, 표로 정리"></textarea><div class="grid2"><div><label>목표</label><input id="craft_goal" placeholder="예: 수업 자료 제작"></div><div><label>대상</label><input id="craft_audience" placeholder="예: 고등학생"></div><div><label>분야</label><select id="craft_task"><option value="general">일반</option><option value="education">교육</option><option value="marketing">마케팅</option><option value="business">비즈니스</option><option value="research">리서치</option><option value="coding">코딩</option></select></div><div><label>톤</label><select id="craft_tone"><option value="professional">전문적</option><option value="friendly">친절한</option><option value="premium">프리미엄</option><option value="concise">간결한</option><option value="creative">창의적</option></select></div></div><label>출력 형식</label><input id="craft_output" placeholder="예: 표 + 예시 + 주의점"><button class="btn btn-green" onclick="craft()">3. 질문 생성</button></div></div><div class="panel"><h3>결과</h3><p class="panel-desc">결과가 나오면 복사해서 실제 AI에 넣어 사용하세요.</p><div id="zipResult"><div class="result-empty"><div><b>아직 실행 전입니다.</b><p>왼쪽에서 목적을 선택하고 내용을 입력한 뒤 실행 버튼을 눌러주세요.</p></div></div></div><div id="craftResult" class="hidden"></div></div></div></section>
<section class="section"><div class="section-head"><h2>예시로 먼저 이해하기</h2><p>고객은 실제 입력 전 Before/After 예시를 보고 서비스의 가치를 빠르게 이해합니다.</p></div><div class="examples"><div class="example"><h3>마케팅 문구</h3><p class="smallbox">원본의 타깃, 혜택, CTA 조건을 유지하면서 짧은 요청으로 정리합니다.</p><div class="kept"><span class="pill">절감</span><span class="pill">CTA 유지</span></div></div><div class="example"><h3>문서 요약</h3><p class="smallbox">회의록, 리포트, 계약서처럼 조건이 많은 요청을 핵심 슬롯으로 재구성합니다.</p><div class="kept"><span class="pill">조건 보존</span><span class="pill">표 출력</span></div></div><div class="example"><h3>질문 생성</h3><p class="smallbox">키워드만 있을 때 역할, 목표, 출력 형식을 포함한 좋은 질문으로 바꿉니다.</p><div class="kept"><span class="pill">역할 부여</span><span class="pill">출력 형식</span></div></div></div></section>
<section class="section"><div class="section-head"><h2>월간 절감액 계산기</h2><p>대략적인 사용량을 넣어 비용 절감 가능성을 간단히 확인할 수 있습니다.</p></div><div class="calc"><div class="panel"><div class="grid2"><div><label>월 프롬프트 수</label><input id="calc_count" type="number" value="300"></div><div><label>평균 입력 토큰</label><input id="calc_tokens" type="number" value="900"></div><div><label>예상 절감률(%)</label><input id="calc_save" type="number" value="24"></div><div><label>1,000토큰당 비용(원)</label><input id="calc_price" type="number" value="3"></div></div><button class="btn btn-amber" onclick="runCalc()">예상 절감액 계산</button></div><div class="panel" id="calcResult"><h2>예상 결과</h2><p>숫자를 입력하고 계산 버튼을 누르면 월 예상 절감액이 표시됩니다.</p></div></div></section>
<section class="section" id="pricing"><div class="section-head"><h2>요금제</h2><p>토큰 절감과 질문 고도화는 서로 다른 가치이므로 별도 상품으로 분리했습니다. 둘 다 필요한 사용자는 Bundle을 선택하면 됩니다.</p></div><div class="pricing"><div class="plan"><h3>Free</h3><p>가볍게 테스트</p><div class="price">₩0</div><ul><li>하루 3회 체험</li><li>기본 압축</li><li>질문 생성 맛보기</li></ul><button class="btn btn-ghost" onclick="scrollToId('tool')">무료 체험</button></div><div class="plan highlight"><div class="ribbon">비용 절감</div><h3>PromptZip Pro</h3><p>긴 프롬프트 압축</p><div class="price">₩9,900</div><ul><li>의미 보존 압축</li><li>엔진별 비용 추정</li><li>고급 과금 옵션</li></ul><button class="btn btn-primary" onclick="openLead('PromptZip Pro')">출시 알림 받기</button></div><div class="plan"><h3>PromptCraft Pro</h3><p>키워드 → 좋은 질문</p><div class="price">₩14,900</div><ul><li>질문 후보 생성</li><li>역할·목표 자동 구성</li><li>출력 형식 설계</li></ul><button class="btn btn-green" onclick="openLead('PromptCraft Pro')">출시 알림 받기</button></div><div class="plan bundle"><div class="ribbon">추천</div><h3>Bundle</h3><p>압축 + 질문 생성</p><div class="price">₩19,900</div><ul><li>PromptZip 포함</li><li>PromptCraft 포함</li><li>가장 높은 활용도</li></ul><button class="btn btn-amber" onclick="openLead('Bundle')">Bundle 알림 받기</button></div></div><div id="leadBox" class="panel leadbox hidden"><h3>출시 알림 등록</h3><p class="panel-desc">이메일을 남기면 공개 테스트 또는 유료 플랜 시작 시 안내할 수 있습니다.</p><div class="grid2"><div><label>이름</label><input id="leadName" placeholder="이름"></div><div><label>이메일</label><input id="leadEmail" placeholder="email@example.com"></div></div><label>관심 플랜</label><input id="leadPlan" readonly><label>메시지</label><textarea id="leadMsg" placeholder="원하는 기능이나 사용 목적을 적어주세요."></textarea><button class="btn btn-primary" onclick="submitLead()">등록하기</button></div></section>
<section class="section" id="faq"><div class="section-head"><h2>자주 묻는 질문</h2><p>고객이 결정을 망설이는 지점을 미리 설명합니다.</p></div><div class="faq"><div class="faq-item"><b>의미가 바뀌지는 않나요?</b><p>핵심 조건 커버리지를 확인하며 압축합니다. 단, 최종 사용 전 압축 결과를 한 번 확인하는 것을 권장합니다.</p></div><div class="faq-item"><b>실제 비용과 완전히 같나요?</b><p>공개 요금 구조를 반영한 추정값입니다. 실제 청구액은 각 AI 제공사의 usage dashboard와 invoice가 기준입니다.</p></div><div class="faq-item"><b>PromptZip과 PromptCraft 차이는?</b><div class="choice-selector"><div class="choice-card zip"><span class="choice-icon zip">Zip</span><div><strong>PromptZip</strong><small>이미 작성한 긴 질문을 의미 보존 방식으로 압축합니다.</small></div></div><div class="choice-card craft"><span class="choice-icon craft">Craft</span><div><strong>PromptCraft</strong><small>키워드만 있을 때 더 섬세한 질문으로 바꿉니다.</small></div></div></div></div><div class="faq-item"><b>고급 옵션은 꼭 써야 하나요?</b><p>아니요. 처음에는 기본값으로 사용하고, 엔진별 과금 구조를 더 정확히 보고 싶을 때만 열면 됩니다.</p></div></div></section>
<section class="section"><div class="panel closing"><div class="section-head"><h2>지금 바로 테스트해보세요</h2><p>먼저 무료로 압축률과 품질 점수를 확인하고, 필요하면 Pro 또는 Bundle 출시 알림을 남기면 됩니다.</p></div><div class="cta"><button class="btn btn-amber" onclick="scrollToId('tool')">무료 체험 시작</button><button class="btn btn-ghost" onclick="scrollToId('pricing')">요금제 보기</button></div></div></section><div class="footer">PromptZip · 실제 청구액은 각 AI 제공사의 청구서를 기준으로 확인해야 합니다.</div></main><div id="toast" class="toast"></div>
<script>
const $=id=>document.getElementById(id);function scrollToId(id){$(id)?.scrollIntoView({behavior:'smooth',block:'start'})}function toast(t){const x=$('toast');x.innerText=t;x.style.display='block';setTimeout(()=>x.style.display='none',1800)}function escapeHtml(s){return String(s||'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]))}
function showMode(m){$('zipMode').classList.toggle('hidden',m!=='zip');$('craftMode').classList.toggle('hidden',m!=='craft');$('zipResult').classList.toggle('hidden',m!=='zip');$('craftResult').classList.toggle('hidden',m!=='craft');$('tabZip').classList.toggle('active',m==='zip');$('tabCraft').classList.toggle('active',m==='craft')}
function opts(){const f=$('extra_flags').value;return{cache_pct:$('cache_pct').value,thinking_tokens:$('thinking_tokens').value,output_ratio:$('output_ratio').value,search_calls:$('search_calls').value,tool_calls:$('tool_calls').value,batch:f==='batch'||f==='both',regional:f==='regional'||f==='both'}}
async function optimize(){const box=$('zipResult');box.innerHTML='<div class="result-empty"><div><b>압축 계산 중</b><p>핵심 조건을 추출하고 의미 보존 여부를 확인하는 중입니다.</p></div></div>';try{const res=await fetch('/api/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt_text:$('prompt_text').value,provider:$('provider').value,options:opts()})});const d=await res.json();if(!d.ok)throw new Error(d.error||'실패');const saved=(d.cost&&d.cost.saving_cost?d.cost.saving_cost:0);box.innerHTML=`<div class="metric-grid"><div class="metric"><b>${d.token_saving_pct}%</b><span>토큰 절감률</span></div><div class="metric"><b>${d.quality_score}</b><span>품질 점수</span></div><div class="metric"><b>$${Number(saved).toFixed(4)}</b><span>예상 절감</span></div></div><label>압축 프롬프트</label><div class="compressed" id="compressedText">${escapeHtml(d.compressed_prompt)}</div><button class="btn btn-green" onclick="copyEl('compressedText')" style="margin-top:14px">4. 복사해서 사용</button><h3>확인 포인트</h3><div class="kept"><span class="pill">커버리지 ${d.coverage}</span><span class="pill">${escapeHtml(d.cost.provider_label)}</span></div><p class="fine" style="margin-top:10px">절감률이 높아도 의미가 바뀌면 좋은 압축이 아닙니다. 품질 점수와 압축 문장을 함께 확인하세요.</p>`}catch(e){box.innerHTML='<div class="result-empty"><div><b>오류</b><p>'+escapeHtml(e.message)+'</p></div></div>'}}
async function craft(){const box=$('craftResult');box.innerHTML='<div class="result-empty"><div><b>질문 설계 중</b><p>키워드를 역할, 목표, 출력 형식이 있는 질문으로 바꾸는 중입니다.</p></div></div>';try{const payload={keywords:$('craft_keywords').value,goal:$('craft_goal').value,audience:$('craft_audience').value,task:$('craft_task').value,tone:$('craft_tone').value,output_format:$('craft_output').value,ask_questions:true};const res=await fetch('/api/craft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await res.json();if(!d.ok)throw new Error(d.error||'실패');box.innerHTML=`<div class="metric-grid"><div class="metric"><b>${d.best.tokens}</b><span>질문 토큰</span></div><div class="metric"><b>${d.best.quality_score}</b><span>정교화 점수</span></div><div class="metric"><b>${d.keyword_count}</b><span>키워드</span></div></div><label>생성된 고급 질문</label><div class="compressed" id="craftText">${escapeHtml(d.best.prompt)}</div><button class="btn btn-green" onclick="copyEl('craftText')" style="margin-top:14px">4. 질문 복사</button><h3>질문 후보</h3>${d.variants.map(v=>`<div class="history-item"><b>${escapeHtml(v.name)}</b> · ${v.tokens} tokens · score ${v.quality_score}</div>`).join('')}`}catch(e){box.innerHTML='<div class="result-empty"><div><b>오류</b><p>'+escapeHtml(e.message)+'</p></div></div>'}}
async function copyEl(id){await navigator.clipboard.writeText($(id)?.innerText||'');toast('복사했습니다')}function openLead(plan){$('leadBox').classList.remove('hidden');$('leadPlan').value=plan;scrollToId('leadBox')}async function submitLead(){const payload={name:$('leadName').value,email:$('leadEmail').value,plan:$('leadPlan').value,message:$('leadMsg').value};if(!payload.email){toast('이메일을 입력해주세요');return}const res=await fetch('/api/lead',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await res.json();if(d.ok){toast('등록되었습니다');$('leadName').value='';$('leadEmail').value='';$('leadMsg').value=''}else toast('등록 실패')}
function runCalc(){const count=Number($('calc_count').value||0), tokens=Number($('calc_tokens').value||0), save=Number($('calc_save').value||0)/100, price=Number($('calc_price').value||0);const saved=Math.round(count*tokens*save);const money=Math.round(saved/1000*price);$('calcResult').innerHTML=`<h2>예상 결과</h2><div class="stats"><div class="stat"><b>₩${money.toLocaleString()}</b><span>월 예상 절감액</span></div><div class="stat"><b>${saved.toLocaleString()}</b><span>절감 토큰</span></div><div class="stat"><b>${save*100}%</b><span>가정 절감률</span></div></div><p style="margin-top:14px">추정값이며 실제 청구액은 각 AI 제공사의 청구서가 기준입니다.</p>`}
</script>
</body>
</html>
'''
ADMIN_HTML = '<!doctype html>\n<html lang=\'ko\'><head><meta charset=\'utf-8\'><meta name=\'viewport\' content=\'width=device-width,initial-scale=1\'><title>PromptZip Admin</title>\n<style>\n*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;background:#f6f8fc;color:#0f172a}.wrap{max-width:980px;margin:0 auto;padding:36px 20px}.panel{background:#fff;border:1px solid #e2e8f0;border-radius:24px;padding:24px;box-shadow:0 18px 45px rgba(15,23,42,.08)}h1{margin:0 0 8px;font-size:34px;letter-spacing:-1px}p{color:#64748b;line-height:1.65}.row{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.btn{border:0;border-radius:14px;padding:12px 15px;font-weight:800;cursor:pointer;background:#2563eb;color:#fff}.btn.secondary{background:#eef6ff;color:#17406d;border:1px solid #d9e8fa}input{width:100%;padding:13px;border:1px solid #d7e2f0;border-radius:14px}.item{border:1px solid #e6edf7;border-radius:16px;padding:13px;margin-top:10px;background:#fbfdff;word-break:break-word}.hidden{display:none}.muted{color:#64748b;font-size:14px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}</style></head>\n<body><div class=\'wrap\'><div class=\'top\'><div><h1>PromptZip 운영자 모드</h1><p>고객 화면에 보일 필요가 없는 히스토리와 관심 등록자 확인은 이 관리자 화면에서만 확인합니다.</p></div><a href=\'/\' class=\'btn secondary\' style=\'text-decoration:none\'>고객 화면으로</a></div>\n<div id=\'login\' class=\'panel\'><h2>관리자 로그인</h2><p class=\'muted\'>데모 비밀번호: admin1234</p><input id=\'pw\' type=\'password\' placeholder=\'관리자 비밀번호\'><div class=\'row\'><button class=\'btn\' onclick=\'login()\'>로그인</button></div><p id=\'loginMsg\' class=\'muted\'></p></div>\n<div id=\'admin\' class=\'panel hidden\'><h2>운영 데이터</h2><p>초기 공개 후에는 압축 실행 기록, 질문 생성 기록, Pro/Bundle 관심 등록자를 확인하면 됩니다.</p><div class=\'row\'><button class=\'btn\' onclick=\'loadHistory("zip")\'>Zip 히스토리</button><button class=\'btn\' onclick=\'loadHistory("craft")\'>Craft 히스토리</button><button class=\'btn\' onclick=\'loadLeads()\'>관심 등록자</button><a class=\'btn secondary\' href=\'/api/export/leads.csv\' style=\'text-decoration:none\'>대기자 CSV</a><a class=\'btn secondary\' href=\'/api/export/zip.csv\' style=\'text-decoration:none\'>Zip CSV</a><a class=\'btn secondary\' href=\'/api/export/craft.csv\' style=\'text-decoration:none\'>Craft CSV</a></div><div id=\'adminResult\'></div></div></div>\n<script>\nfunction esc(s){return String(s||\'\').replace(/[&<>"\']/g,function(c){return {\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]})}\nfunction login(){if(document.getElementById(\'pw\').value===\'admin1234\'){document.getElementById(\'login\').classList.add(\'hidden\');document.getElementById(\'admin\').classList.remove(\'hidden\')}else{document.getElementById(\'loginMsg\').textContent=\'비밀번호가 맞지 않습니다.\'}}\nasync function loadHistory(type){const res=await fetch(type===\'craft\'?\'/api/craft/history\':\'/api/history\');const d=await res.json();document.getElementById(\'adminResult\').innerHTML=(d.items||[]).map(x=>\'<div class="item"><b>\'+esc(x.created_at)+\'</b> · \'+(type===\'craft\'?\'Craft\':\'Zip\')+\'<br>\'+esc(x.prompt_preview||x.keywords_preview||\'\')+\'</div>\').join(\'\')||\'<p>기록이 없습니다.</p>\'}\nasync function loadLeads(){const res=await fetch(\'/api/leads\');const d=await res.json();document.getElementById(\'adminResult\').innerHTML=(d.items||[]).map(x=>\'<div class="item"><b>\'+esc(x.created_at)+\'</b> · \'+esc(x.plan)+\' · \'+esc(x.email)+\'<br>\'+esc(x.message||\'\')+\'</div>\').join(\'\')||\'<p>대기자가 없습니다.</p>\'}\n</script></body></html>'

README = '''# PromptZip V44 + PromptCraft

V44는 새로운 기능을 추가하지 않고, PromptZip/PromptCraft 선택 안내를 문장형에서 카드형 비교 UI로 바꾸어 가독성과 흐름을 개선한 버전입니다.

## 실행

Windows에서 압축을 풀고 `START_HERE_WINDOWS.bat`를 더블클릭하세요.

로컬 주소:

```
http://127.0.0.1:8816
```

정상 확인:

```
http://127.0.0.1:8816/healthz
```

관리자 모드:

```
http://127.0.0.1:8816/admin
```

데모 관리자 비밀번호는 `admin1234`입니다.

## V44 디자인 보정 방향

- 문장 안에 PromptZip / PromptCraft 배지를 끼워 넣던 구조 제거
- 고객이 바로 이해하도록 두 기능을 카드형 선택 안내로 분리
- PromptZip은 파란 Zip 카드, PromptCraft는 민트 Craft 카드로 표시
- 4단계 흐름의 1번 목적 선택 카드 가독성 개선
- 무료 체험 영역의 기능 선택 안내를 더 명확하게 정리
- FAQ에서도 두 기능 차이를 비교 카드로 표시
- 기존 압축, 질문 생성, 엔진별 과금 옵션 기능은 그대로 유지

## 상품 구조

- PromptZip Pro: 월 9,900원
- PromptCraft Pro: 월 14,900원
- Bundle: 월 19,900원

## 배포

Render/Railway 배포를 위해 `PORT` 환경변수를 자동으로 읽습니다. 로컬에서는 기본 8816 포트를 사용합니다.
'''


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type='text/html; charset=utf-8', status=200):
        if isinstance(body, str): body = body.encode('utf-8')
        self.send_response(status); self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def _json(self, obj, status=200): self._send(json.dumps(obj, ensure_ascii=False, indent=2), 'application/json; charset=utf-8', status)
    def _read_json(self):
        length = int(self.headers.get('Content-Length','0') or 0); raw = self.rfile.read(length).decode('utf-8') if length else '{}'; return json.loads(raw or '{}')
    def log_message(self, fmt, *args): return
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/','/index.html'): return self._send(HTML)
        if path == '/admin': return self._send(ADMIN_HTML)
        if path == '/healthz': return self._json({'ok': True, 'service': 'promptzip-v44', 'port': PORT, 'site_url': SITE_URL})
        if path == '/README.md': return self._send(README, 'text/markdown; charset=utf-8')
        if path == '/robots.txt': return self._send('User-agent: *\nAllow: /\nSitemap: '+SITE_URL.rstrip('/')+'/sitemap.xml\n', 'text/plain; charset=utf-8')
        if path == '/sitemap.xml': return self._send('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'+SITE_URL.rstrip()+'/</loc></url></urlset>', 'application/xml; charset=utf-8')
        if path == '/favicon.svg': return self._send('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="18" fill="#0f172a"/><text x="15" y="43" font-size="34" fill="#10b981" font-family="Arial" font-weight="900">Z</text></svg>', 'image/svg+xml; charset=utf-8')
        if path == '/api/history': return self._json({'ok': True, 'items': load_jsonl(ZIP_HISTORY_JSONL, 50)})
        if path == '/api/craft/history': return self._json({'ok': True, 'items': load_jsonl(CRAFT_HISTORY_JSONL, 50)})
        if path == '/api/export/zip.csv': return self._send(history_csv_bytes(ZIP_HISTORY_JSONL), 'text/csv; charset=utf-8')
        if path == '/api/export/craft.csv': return self._send(history_csv_bytes(CRAFT_HISTORY_JSONL), 'text/csv; charset=utf-8')
        if path == '/api/leads':
            rows=[]
            if os.path.exists(LEADS_CSV):
                with open(LEADS_CSV, newline='', encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))[-80:]
            return self._json({'ok': True, 'items': list(reversed(rows))})
        if path == '/api/export/leads.csv':
            if os.path.exists(LEADS_CSV):
                with open(LEADS_CSV, 'rb') as f: return self._send(f.read(), 'text/csv; charset=utf-8')
            return self._send('created_at,name,email,plan,message\n', 'text/csv; charset=utf-8')
        return self._send('Not found', 'text/plain; charset=utf-8', 404)
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == '/api/optimize':
                data = self._read_json(); ok, remaining, used = check_and_increment_usage(self.client_address[0], 'zip')
                if not ok: return self._json({'ok': False, 'error': f'무료 압축 한도({FREE_DAILY_LIMIT_ZIP}회)를 초과했습니다.'}, 429)
                text = data.get('prompt_text',''); provider = data.get('provider','openai'); opts = data.get('options',{}) or {}
                compressed, slots, kept, coverage = compress_prompt(text)
                original_tokens = approx_tokens(text); compressed_tokens = approx_tokens(compressed)
                token_saving_pct = round(max(0, (original_tokens-compressed_tokens)/max(1, original_tokens)*100), 1)
                quality_score = round(min(0.99, 0.86 + coverage*0.12 + min(0.02, len(slots)/100)), 3)
                cost = estimate_cost(original_tokens, compressed_tokens, provider, opts)
                row = {'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'type':'zip', 'provider_label': cost['provider_label'], 'provider': provider, 'prompt_preview': text[:140], 'compressed_prompt': compressed, 'original_tokens': original_tokens, 'compressed_tokens': compressed_tokens, 'token_saving_pct': token_saving_pct, 'quality_score': quality_score, 'coverage': coverage, 'cost': cost}
                save_jsonl(ZIP_HISTORY_JSONL, row)
                return self._json({'ok': True, 'free_remaining': remaining, 'used_today': used, **row})
            if path == '/api/craft':
                data = self._read_json(); ok, remaining, used = check_and_increment_usage(self.client_address[0], 'craft')
                if not ok: return self._json({'ok': False, 'error': f'무료 질문 생성 한도({FREE_DAILY_LIMIT_CRAFT}회)를 초과했습니다.'}, 429)
                best, variants, kws = craft_variants(data.get('keywords',''), data.get('goal',''), data.get('audience',''), data.get('task','general'), data.get('tone','professional'), data.get('output_format',''), bool(data.get('ask_questions', True)))
                row = {'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'type':'craft', 'keywords_preview': data.get('keywords','')[:140], 'crafted_prompt': best['prompt'], 'quality_score': best['quality_score'], 'tokens': best['tokens'], 'keyword_count': len(kws)}
                save_jsonl(CRAFT_HISTORY_JSONL, row)
                return self._json({'ok': True, 'free_remaining': remaining, 'used_today': used, 'best': best, 'variants': variants, 'keywords': kws, 'keyword_count': len(kws), **row})
            if path == '/api/lead':
                data = self._read_json(); exists = os.path.exists(LEADS_CSV)
                with open(LEADS_CSV, 'a', newline='', encoding='utf-8-sig') as f:
                    w=csv.DictWriter(f, fieldnames=['created_at','name','email','plan','message'])
                    if not exists: w.writeheader()
                    w.writerow({'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'name': data.get('name',''), 'email': data.get('email',''), 'plan': data.get('plan',''), 'message': data.get('message','')})
                return self._json({'ok': True})
            return self._json({'ok': False, 'error': 'not found'}, 404)
        except Exception as e:
            return self._json({'ok': False, 'error': str(e)}, 500)

if __name__ == '__main__':
    print('='*52)
    print('PromptZip V44 + PromptCraft')
    print('='*52)
    print(f'Local URL: http://127.0.0.1:{PORT}')
    print('Keep this window open. Press Ctrl+C to stop.')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
