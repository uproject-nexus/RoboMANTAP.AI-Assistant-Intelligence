import os,sys
required=['DATABASE_URL','TKA_STUDIO_SECRET']
missing=[x for x in required if not os.getenv(x)]
print('RoboMANTAP production preflight')
if missing:
    print('MISSING:', ', '.join(missing)); sys.exit(2)
print('Environment: PASS')
print('Database URL: present')
print('TKA Studio Secret: present')
print('Run migrations 001..011 before starting the TKA API.')
print('Start: uvicorn tka_api.app:app --host 0.0.0.0 --port $PORT')
