# Daily Market Assistant Auto - Streamlit Cloud Fixed

## 수정 사항
Streamlit Cloud에서 발생한 아래 SyntaxError를 제거했습니다.

```text
SyntaxError: invalid syntax
*[f"- {x}" for x in positives] if positives else ["- 없음"],
```

`build_snapshot()` 함수 내부를 명시적 `append()` 방식으로 재작성했습니다.

## 배포 파일
- app.py
- requirements.txt

## Streamlit Cloud 배포
GitHub 저장소에 아래 두 파일을 업로드 또는 교체하세요.

```text
app.py
requirements.txt
```

이후 Streamlit Cloud에서 Reboot 또는 Redeploy를 실행하세요.

## 로컬 실행
```bash
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## 주의
이 앱은 투자 참고용 트레이딩 보조 도구이며, 자동 주문 또는 매수/매도 권유 프로그램이 아닙니다.