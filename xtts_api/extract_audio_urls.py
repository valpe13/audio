from pathlib import Path
import re

html_path = Path("xtts_api/reference_audio/natalia_shtin/natalia_page.html")
if not html_path.exists():
    html_path = Path("xtts_api/reference_audio/natalia_shtin/page.html")
out_path = html_path.with_name(html_path.stem + "_audio_urls.txt")

html = html_path.read_text(encoding="utf-8", errors="ignore")
pattern = r"https?://[^\"'<> ]+\.(?:mp3|wav|ogg|m4a)(?:\?[^\"'<> ]*)?"
urls = sorted(set(re.findall(pattern, html, flags=re.IGNORECASE)))
out_path.write_text("\n".join(urls), encoding="utf-8")
print(f"audio urls: {len(urls)}")
for url in urls[:120]:
    print(url)
