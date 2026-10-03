import os,glob,sys
try:
 import psycopg2
except Exception:
 print('psycopg2-binary is required'); sys.exit(2)
dsn=os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
if not dsn: print('DATABASE_URL/POSTGRES_URL is required'); sys.exit(2)
root=os.path.dirname(os.path.dirname(__file__))
files=sorted(glob.glob(os.path.join(root,'migrations','*.sql')))
with psycopg2.connect(dsn) as conn:
    with conn.cursor() as cur:
        for f in files:
            print('APPLY',os.path.basename(f))
            cur.execute(open(f,encoding='utf-8').read())
print('MIGRATIONS_APPLIED:',len(files))
