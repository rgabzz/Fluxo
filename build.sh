pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

# Dados de teste (cidade Itaú + usuários). Para desligar, defina SEED_TESTE=False no Render.
if [ "${SEED_TESTE:-True}" != "False" ]; then
  python manage.py seed_teste --force
fi
