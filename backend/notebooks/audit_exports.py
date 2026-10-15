import re

content = open('frontend/js/app.js', encoding='utf-8').read()

# Find all export IDs
ids = set(re.findall(r'id=["\']([^"\']*export[^"\']*)["\']', content, re.IGNORECASE))
print("--- Export Element IDs in app.js ---")
for i in sorted(ids):
    print(" ", i)

# Find all download / export functions
funcs = set(re.findall(r'function\s+([a-zA-Z0-9_]*(?:export|download)[a-zA-Z0-9_]*)\s*\(', content, re.IGNORECASE))
print("\n--- Export/Download Functions ---")
for f in sorted(funcs):
    print(" ", f)

# Find all click listeners on export IDs
print("\n--- Export Click Handlers ---")
for line_no, line in enumerate(content.splitlines(), 1):
    if any(i in line for i in ids) or 'downloadCSV' in line or 'exportAnalysis' in line:
        print(f"Line {line_no:4d}: {line.strip()[:100]}")
