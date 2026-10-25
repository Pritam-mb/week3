from pathlib import Path
import unicodedata

for p in Path('molt/web').rglob('*'):
    if p.is_file() and p.suffix in ['.js', '.html', '.css']:
        content = p.read_text(encoding='utf-8')
        for idx, line in enumerate(content.splitlines(), start=1):
            for c in line:
                if c in "✓⚠️🔴🟢🟡✅❌\u26a0\ufe0f\u2705\u274c\u2713":
                    print(f"{p}:{idx} Found '{c}' (U+{ord(c):04X}) in: {line.strip()[:100]}")
