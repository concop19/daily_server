import ast, sys
files = ['auth_middleware.py', 'rate_limiter.py', 'app.py', 'weather.py']
ok = True
for f in files:
    try:
        src = open(f, encoding='utf-8').read()
        ast.parse(src)
        lines = src.count('\n') + 1
        print(f'OK  {f}  ({lines} lines)')
    except SyntaxError as e:
        print(f'ERR {f}: line {e.lineno} — {e.msg}')
        ok = False
    except FileNotFoundError:
        print(f'MISSING {f}')
        ok = False
print('PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
