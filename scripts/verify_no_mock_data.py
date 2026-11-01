import os

terms = ['dummy', 'fake_case', 'seed_data', 'mock_case']
found = []

for root, dirs, files in os.walk('.'):
    if any(p in root for p in ['.venv', 'node_modules', '.git', 'dist', '.pytest_cache', '__pycache__']):
        continue
    for file in files:
        if file.endswith(('.py', '.ts', '.tsx')) and not file.startswith('transcript'):
            fpath = os.path.join(root, file)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                for t in terms:
                    if t in content:
                        found.append((fpath, t))
            except Exception:
                pass

print(f"Forbidden term occurrences found: {len(found)}")
for f, t in found:
    print(f"  {f}: contains '{t}'")

