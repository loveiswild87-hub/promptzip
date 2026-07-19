# PromptZip V46 — Genspark AI Edition

This version keeps PromptCraft as the main feature and adds target-AI formatting.

- PromptCraft is the main feature.
- User input is automatically classified as Craft or Zip.
- Target AI selector added: Auto, GPT, Claude, Gemini, Genspark AI.
- Genspark AI mode creates research-style prompts with goals, comparison criteria, verification points, and final output format.
- PromptZip remains as a secondary feature for compressing already-long prompts.

## Local Run

```bash
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:8817
```

## Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

Optional Environment Variable:

```text
GA_MEASUREMENT_ID=G-XXXXXXXXXX
```


## V47 추가 사항
- GPT / Claude / Gemini / Genspark AI별 프롬프트 구조 강화
- 입력 언어 감지 후 한국어/영어/입력 언어 유지 지시 추가
- Genspark AI용 리서치·근거 확인·비교표 구조 강화
- Gemini용 표·비교·단계 구조 강화
- Claude용 맥락·조건·품질 기준 구조 강화
- GPT용 간결한 역할·목표·출력형식 구조 강화
